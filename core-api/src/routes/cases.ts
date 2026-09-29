import { Router, type Request, type Response } from "express";
import multer from "multer";
import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";
import exifr from "exifr";
import sharp from "sharp";
import { appendAuditLog } from "../utils/audit";
import { validateStatusTransition } from "../services/decisionEngine";
import { requireRole, type AuthenticatedRequest } from "../middleware/auth";
import { prisma } from "../db";
import {
  ALLOWED_EXTENSIONS,
  MAX_FILE_BYTES,
  safeUnlink,
} from "../media/validateUpload";
import { validateAndPreprocessImage } from "../media/preprocessImage";
import {
  accessModeForAuthorRole,
  canAccessCase,
  canDeleteCase,
  canReviewCase,
} from "../utils/caseAccess";
import { verdictFromRisk, writeCaseVerdict } from "../utils/verdicts";
import { autoAssignReviewer } from "../utils/autoAssign";
import {
  ensurePublicMediaUrl,
  parseExplanationMeta,
} from "../utils/evidenceAssets";
import {
  createVerificationJob,
  scheduleVerificationPipeline,
  stageProgress,
  updateJobStage,
} from "../services/verificationPipeline";
import { notifyCaseEvent } from "../utils/notify";
import reportsRouter from "./reports";

const router = Router();

const CASE_DELETE_ROLES = ["Administrator", "User"] as const;

/** Permanently remove a case and every row that references it (FKs are RESTRICT). */
async function hardDeleteCase(caseId: string): Promise<void> {
  const media = await prisma.mediaAsset.findMany({
    where: { caseId },
    select: { id: true, storageUrl: true },
  });
  const mediaIds = media.map((m) => m.id);
  const sessions = await prisma.streamSession.findMany({
    where: { caseId },
    select: { id: true },
  });
  const sessionIds = sessions.map((s) => s.id);

  await prisma.$transaction(async (tx) => {
    if (sessionIds.length > 0) {
      await tx.rollingScore.deleteMany({ where: { sessionId: { in: sessionIds } } });
      await tx.streamQualityLog.deleteMany({ where: { sessionId: { in: sessionIds } } });
      await tx.streamFrame.deleteMany({ where: { sessionId: { in: sessionIds } } });
      await tx.streamSession.deleteMany({ where: { caseId } });
    }

    if (mediaIds.length > 0) {
      const forgery = await tx.forgeryResult.findMany({
        where: { mediaId: { in: mediaIds } },
        select: { id: true },
      });
      const forgeryIds = forgery.map((f) => f.id);
      if (forgeryIds.length > 0) {
        await tx.evidenceVisual.deleteMany({ where: { forgeryResultId: { in: forgeryIds } } });
        await tx.forgeryResult.deleteMany({ where: { id: { in: forgeryIds } } });
      }
      await tx.sourceMetadata.deleteMany({ where: { mediaId: { in: mediaIds } } });
      await tx.mediaFingerprint.deleteMany({ where: { mediaId: { in: mediaIds } } });
    }

    await tx.verdict.deleteMany({ where: { caseId } });
    await tx.verificationJob.deleteMany({ where: { caseId } });
    await tx.report.deleteMany({ where: { caseId } });
    await tx.mediaAsset.deleteMany({ where: { caseId } });
    await tx.auditLog.deleteMany({ where: { caseId } });
    await tx.case.delete({ where: { id: caseId } });
  });

  for (const m of media) {
    if (m.storageUrl?.startsWith("/uploads/")) {
      const filePath = path.join(process.cwd(), m.storageUrl.replace(/^\//, ""));
      try {
        if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
      } catch {
        /* best-effort cleanup */
      }
    }
  }
}

// Ensure uploads directory exists
const uploadDir = path.join(process.cwd(), "uploads");
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

// Multer storage config
const storage = multer.diskStorage({
  destination: (_req, _file, cb) => {
    cb(null, uploadDir);
  },
  filename: (_req, file, cb) => {
    const uniqueSuffix = Date.now() + "-" + Math.round(Math.random() * 1e9);
    const ext = path.extname(file.originalname);
    cb(null, file.fieldname + "-" + uniqueSuffix + ext);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: MAX_FILE_BYTES },
  fileFilter: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ALLOWED_EXTENSIONS.has(ext)) {
      return cb(null, true);
    }
    cb(
      new Error(
        "Invalid file type. Only images are accepted: .jpg, .jpeg, .png, .webp"
      )
    );
  },
});

/**
 * Compute Difference Hash (dHash) for an image buffer using Sharp.
 * Resizes to 9x8 grayscale, compares adjacent pixel intensities.
 */
async function computeDHash(imageBuffer: Buffer): Promise<string | null> {
  try {
    const { data } = await sharp(imageBuffer)
      .resize(9, 8, { fit: "fill" })
      .grayscale()
      .raw()
      .toBuffer({ resolveWithObject: true });

    let binaryHash = "";
    for (let row = 0; row < 8; row++) {
      for (let col = 0; col < 8; col++) {
        const left = data[row * 9 + col]!;
        const right = data[row * 9 + col + 1]!;
        binaryHash += left > right ? "1" : "0";
      }
    }
    let hexHash = "";
    for (let i = 0; i < 64; i += 4) {
      hexHash += parseInt(binaryHash.substring(i, i + 4), 2).toString(16);
    }
    return hexHash;
  } catch (err) {
    return null;
  }
}

/**
 * Compute Hamming distance between two 16-character hex dHashes
 */
function getHammingDistance(hash1: string, hash2: string): number {
  if (!hash1 || !hash2 || hash1.length !== hash2.length) return 64;
  let distance = 0;
  for (let i = 0; i < hash1.length; i++) {
    const val1 = parseInt(hash1[i]!, 16);
    const val2 = parseInt(hash2[i]!, 16);
    let xor = val1 ^ val2;
    while (xor > 0) {
      distance += xor & 1;
      xor >>= 1;
    }
  }
  return distance;
}

/**
 * Source Integrity Score computation based on EXIF fields.
 *
 * §6.5 note: social platforms often strip EXIF — treat absence as
 * "Inconclusive", not "Suspicious". Only flag editing software as tampered.
 */
function analyzeSourceIntegrity(exifData: any) {
  if (!exifData || Object.keys(exifData).length === 0) {
    return {
      integrityScore: 0.50,
      deviceFingerprint: "Unknown — Metadata Not Present",
      softwareFlag: "No EXIF metadata found (inconclusive — common on web/social images)",
      isTampered: false, // absence of EXIF is inconclusive, not evidence of tampering
    };
  }

  const software = (exifData.Software || "").toString().toLowerCase();
  const model = exifData.Model || exifData.Make || "Standard Digital Camera";
  let score = 0.95;
  let softwareFlag = "Original Camera Capture";
  let isTampered = false;

  const editingTools = ["photoshop", "gimp", "canva", "adobe", "lightroom", "paint.net", "snapseed", "facetune"];
  for (const tool of editingTools) {
    if (software.includes(tool)) {
      score = 0.35;
      softwareFlag = `Post-processing Software Detected (${exifData.Software})`;
      isTampered = true;
      break;
    }
  }

  return {
    integrityScore: score,
    deviceFingerprint: model,
    softwareFlag,
    isTampered,
  };
}

// Memory Fallback Store if DB connection fails or DB is empty
let memoryCases = [
  { id: "CAS-142", subject: "Deepfake Detection - Politician Speech", title: "Deepfake Detection - Politician Speech", status: "Flagged", date: "2026-08-12", createdAt: new Date("2026-08-12"), confidence: "98%" },
  { id: "CAS-141", subject: "Audio Verification - Ransom Call", title: "Audio Verification - Ransom Call", status: "Verified", date: "2026-08-11", createdAt: new Date("2026-08-11"), confidence: "99%" },
  { id: "CAS-140", subject: "Image Authentication - Passport", title: "Image Authentication - Passport", status: "Analyzing", date: "2026-08-11", createdAt: new Date("2026-08-11"), confidence: "..." },
  { id: "CAS-139", subject: "CCTV Footage Enhancing", title: "CCTV Footage Enhancing", status: "Verified", date: "2026-08-10", createdAt: new Date("2026-08-10"), confidence: "94%" },
  { id: "CAS-138", subject: "Splice Detection - Interview", title: "Splice Detection - Interview", status: "Flagged", date: "2026-08-09", createdAt: new Date("2026-08-09"), confidence: "87%" },
];

/**
 * Nested forensic reports (6.10) — must be registered before bare GET /:id
 * so Express does not treat "reports" as a case id segment incorrectly.
 * Path: /api/cases/:id/reports
 */
router.use("/:id/reports", reportsRouter);

/**
 * GET /api/cases
 * Fetch cases. Query:
 *   scope=all|mine|assigned  (default all for admin, mine for user, assigned for reviewer if omitted with role)
 *   status=...
 */
router.get("/", async (req: AuthenticatedRequest, res: Response) => {
  try {
    const role = req.user?.role;
    const userId = req.user?.userId;
    const scopeParam = typeof req.query.scope === "string" ? req.query.scope : undefined;
    const statusFilter = typeof req.query.status === "string" ? req.query.status : undefined;

    let scope = scopeParam;
    if (!scope) {
      if (role === "User") scope = "mine";
      else if (role === "Reviewer") scope = "assigned";
      else scope = "all";
    }
    // Public users cannot escalate to all/assigned via query string
    if (role === "User") scope = "mine";
    // Reviewers cannot use scope=all
    if (role === "Reviewer" && scope === "all") scope = "assigned";

    const where: any = {};
    if (scope === "mine" && userId) where.createdBy = userId;
    if (scope === "assigned" && userId) {
      // Assigned to me OR unassigned Flagged (pickup / pre-auto-assign queue)
      where.OR = [
        { assignedTo: userId },
        { status: "Flagged", assignedTo: null },
      ];
    }
    if (statusFilter) where.status = statusFilter;

    const dbCases = await prisma.case.findMany({
      where,
      orderBy: { createdAt: "desc" },
      include: {
        mediaAssets: {
          include: {
            fingerprints: true,
            sourceMetadata: true,
          },
        },
        author: { select: { id: true, name: true, email: true } },
        assignedReviewer: { select: { id: true, name: true, email: true } },
      },
    });

    const formatted = dbCases.map((c) => {
      const asset = c.mediaAssets[0];
      const sha256 =
        asset?.fingerprints[0]?.sha256 ||
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
      const trustPct =
        typeof c.trustScore === "number" ? `${Math.round(c.trustScore * 100)}%` : null;
      return {
        id: c.id,
        title: c.title,
        subject: c.title,
        status: c.status,
        date: c.createdAt.toISOString().split("T")[0],
        confidence:
          trustPct ??
          (c.status === "Flagged" ? "98%" : c.status === "Verified" ? "99%" : "..."),
        trustScore: c.trustScore,
        riskLevel: c.riskLevel,
        createdBy: c.createdBy,
        assignedTo: c.assignedTo,
        authorName: c.author?.name ?? null,
        reviewerName: c.assignedReviewer?.name ?? null,
        sha256,
        mediaUrl: asset ? asset.storageUrl : undefined,
        metadata: asset?.sourceMetadata?.exifJson || null,
      };
    });

    // Only fall back to demo cases when the DB truly has nothing for "all"
    if (formatted.length === 0 && scope === "all") {
      return res.json({ success: true, data: memoryCases });
    }

    return res.json({ success: true, data: formatted });
  } catch (error) {
    console.error("Prisma error in GET /api/cases:", error);
    // Never hide scoped (mine/assigned) failures behind demo data — that
    // made public users think cases "vanished" after refresh.
    const scopeHint = typeof req.query.scope === "string" ? req.query.scope : req.user?.role;
    if (scopeHint === "mine" || scopeHint === "assigned" || req.user?.role === "User" || req.user?.role === "Reviewer") {
      return res.status(500).json({ success: false, data: [], message: "Failed to load your cases." });
    }
    return res.json({ success: true, data: memoryCases });
  }
});

/**
 * GET /api/cases/:id
 * Fetch single case details with evidence, SHA-256 hash & EXIF metadata.
 * Enforces role ownership (6.3).
 */
router.get("/:id", async (req: AuthenticatedRequest, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const dbCase = await prisma.case.findUnique({
      where: { id: caseId },
      include: {
        author: { select: { id: true, name: true, email: true, role: { select: { name: true } } } },
        assignedReviewer: { select: { id: true, name: true, email: true } },
        verdicts: { orderBy: { decidedAt: "desc" }, take: 5 },
        jobs: { orderBy: { updatedAt: "desc" }, take: 1 },
        mediaAssets: {
          include: {
            fingerprints: true,
            sourceMetadata: true,
            forgeryResults: {
              include: { evidenceVisuals: true },
              orderBy: { createdAt: "desc" },
            },
          },
        },
      },
    });

    if (!dbCase) {
      return res.status(404).json({ success: false, message: "Case not found" });
    }

    if (
      !canAccessCase(req.user, {
        id: dbCase.id,
        createdBy: dbCase.createdBy,
        assignedTo: dbCase.assignedTo,
        status: dbCase.status,
      })
    ) {
      return res.status(403).json({
        success: false,
        message: "You do not have access to this case.",
      });
    }

    const asset = dbCase.mediaAssets[0];
    const sha256 =
      asset?.fingerprints[0]?.sha256 ||
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

    const exifJson = asset?.sourceMetadata?.exifJson || null;
    const integrityAnalysis = analyzeSourceIntegrity(exifJson);

    const forgeryResult = asset?.forgeryResults?.[0];
    const rawOutput = (forgeryResult?.rawOutputJson as any) || null;
    const deepfakeScore = rawOutput?.deepfake?.probability_fake ?? null;
    const tamperingScore = rawOutput?.tampering?.probability_tampered ?? null;
    const syntheticScore = rawOutput?.synthetic?.probability_synthetic ?? null;
    const visual = forgeryResult?.evidenceVisuals?.[0];
    const meta = parseExplanationMeta(visual?.explanationText);
    const overlayStored =
      meta?.overlayUrl || visual?.heatmapUrl || null;
    const heatmapStored = meta?.heatmapUrl || null;
    const overlayUrl = ensurePublicMediaUrl(overlayStored, dbCase.id);
    const rawHeatmapUrl = ensurePublicMediaUrl(heatmapStored, dbCase.id);
    // Persist rewritten public URL if we just migrated an absolute path
    if (overlayUrl && visual?.id && overlayUrl !== visual.heatmapUrl && overlayUrl.startsWith("/uploads/")) {
      try {
        await prisma.evidenceVisual.update({
          where: { id: visual.id },
          data: {
            heatmapUrl: overlayUrl,
            explanationText: JSON.stringify({
              ...(meta || {}),
              overlayUrl,
              heatmapUrl: rawHeatmapUrl || meta?.heatmapUrl || null,
              method: meta?.method || "gradcam",
              targetLayer: meta?.targetLayer,
              summary: meta?.summary || visual.explanationText,
            }),
          },
        });
      } catch {
        /* best-effort rewrite */
      }
    }

    const accessMode = accessModeForAuthorRole(dbCase.author?.role?.name);
    const latestVerdict = dbCase.verdicts[0] || null;
    const latestJob = dbCase.jobs[0] || null;

    return res.json({
      success: true,
      data: {
        id: dbCase.id,
        title: dbCase.title,
        subject: dbCase.title,
        status: dbCase.status,
        date: dbCase.createdAt.toISOString().split("T")[0],
        confidence:
          typeof dbCase.trustScore === "number"
            ? `${Math.round(dbCase.trustScore * 100)}%`
            : dbCase.status === "Flagged"
              ? "98%"
              : dbCase.status === "Verified"
                ? "99%"
                : "...",
        trustScore: dbCase.trustScore,
        riskLevel: dbCase.riskLevel,
        decision: {
          trustScore: dbCase.trustScore,
          riskLevel: dbCase.riskLevel,
          riskBand: dbCase.riskLevel, // Low | Medium | High (6.8)
          legacyRiskLevel:
            dbCase.riskLevel === "Low"
              ? "Authentic"
              : dbCase.riskLevel === "Medium"
                ? "Uncertain"
                : dbCase.riskLevel === "High"
                  ? "High-Risk"
                  : dbCase.riskLevel,
          ruleTrace: latestVerdict?.ruleTraceJson || null,
          finalVerdict: latestVerdict?.finalVerdict || null,
        },
        verificationJob: latestJob
          ? {
              id: latestJob.id,
              status: latestJob.status,
              stage: latestJob.stage,
              errorLog: latestJob.errorLog,
              progress: stageProgress(latestJob.stage, latestJob.status),
              updatedAt: latestJob.updatedAt,
            }
          : null,
        createdBy: dbCase.createdBy,
        assignedTo: dbCase.assignedTo,
        authorName: dbCase.author?.name ?? null,
        reviewerName: dbCase.assignedReviewer?.name ?? null,
        accessMode,
        latestVerdict: latestVerdict
          ? {
              finalVerdict: latestVerdict.finalVerdict,
              confidence: latestVerdict.confidence,
              decidedAt: latestVerdict.decidedAt,
              ruleTrace: latestVerdict.ruleTraceJson,
            }
          : null,
        sha256,
        mediaUrl: asset ? asset.storageUrl : undefined,
        resolution: asset?.resolution || "1920x1080",
        format: asset?.fileType || "image/png",
        exifData: exifJson,
        deviceFingerprint:
          asset?.sourceMetadata?.deviceFingerprint || integrityAnalysis.deviceFingerprint,
        integrityScore:
          asset?.sourceMetadata?.integrityScore || integrityAnalysis.integrityScore,
        softwareFlag: integrityAnalysis.softwareFlag,
        isTampered: integrityAnalysis.isTampered,
        forgery: forgeryResult
          ? {
              modelName: forgeryResult.modelName,
              confidenceScore: forgeryResult.confidenceScore,
              manipulationType: forgeryResult.manipulationType,
              deepfakeScore,
              tamperingScore,
              syntheticScore,
              heatmapUrl: overlayUrl,
              overlayUrl,
              rawHeatmapUrl,
              explanationText:
                meta?.summary ||
                visual?.explanationText ||
                null,
              explanationMethod: meta?.method || null,
              targetLayer: meta?.targetLayer || null,
              faceDetected: rawOutput?.face_detected ?? null,
            }
          : null,
      },
    });
  } catch (error) {
    console.error("Error in GET /api/cases/:id:", error);
    return res.status(500).json({ success: false, message: "Failed to fetch case details." });
  }
});

/**
 * PATCH /api/cases/:id
 * Update case status — validates transition + RBAC; writes Verdict on decide (6.3).
 */
router.patch("/:id", async (req: AuthenticatedRequest, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const { status, assignedTo, comment } = req.body;
    const userId = req.user?.userId || "USR-UNKNOWN";
    const role = req.user?.role;

    if (!status && !assignedTo) {
      return res.status(400).json({ success: false, message: "status or assignedTo is required." });
    }

    const currentCase = await prisma.case.findUnique({
      where: { id: caseId },
      select: {
        id: true,
        status: true,
        createdBy: true,
        assignedTo: true,
        trustScore: true,
        riskLevel: true,
      },
    });
    if (!currentCase) {
      return res.status(404).json({ success: false, message: "Case not found." });
    }

    if (
      !canAccessCase(req.user, {
        id: currentCase.id,
        createdBy: currentCase.createdBy,
        assignedTo: currentCase.assignedTo,
        status: currentCase.status,
      })
    ) {
      return res.status(403).json({ success: false, message: "You do not have access to this case." });
    }

    // Public User cannot change workflow status (view + upload only)
    if (status && role === "User") {
      return res.status(403).json({
        success: false,
        message: "Public users cannot change case status. Reviewers or admins handle decisions.",
      });
    }

    if (status === "Archived" && role !== "Administrator") {
      return res.status(403).json({
        success: false,
        message: "Only administrators can archive cases.",
      });
    }

    if (
      status &&
      (status === "Verified" || status === "Flagged") &&
      !canReviewCase(req.user)
    ) {
      return res.status(403).json({
        success: false,
        message: "Only reviewers or administrators can approve/reject cases.",
      });
    }

    if (assignedTo && role !== "Administrator") {
      return res.status(403).json({
        success: false,
        message: "Only administrators can assign reviewers.",
      });
    }

    if (status) {
      const validation = await validateStatusTransition(currentCase.status, status);
      if (!validation.valid) {
        return res.status(400).json({
          success: false,
          message:
            validation.error ||
            `Invalid status transition: ${currentCase.status} → ${status}`,
        });
      }
    }

    const updatedCase = await prisma.case.update({
      where: { id: caseId },
      data: {
        ...(status ? { status } : {}),
        ...(assignedTo ? { assignedTo } : {}),
        ...(status === "Archived"
          ? { closedAt: new Date() }
          : status
            ? { closedAt: null }
            : {}),
      },
    });

    await appendAuditLog({
      caseId,
      userId,
      action: "UPDATE_STATUS",
      metadataJson: { newStatus: status, assignedTo, comment: comment || null },
    });

    // Human decision → Verdict row
    if (status === "Verified" || status === "Flagged") {
      const mapped = verdictFromRisk(
        status === "Verified" ? "Low" : currentCase.riskLevel || "High",
        status
      );
      await writeCaseVerdict({
        caseId,
        finalVerdict: mapped.finalVerdict,
        confidence:
          typeof currentCase.trustScore === "number"
            ? currentCase.trustScore
            : mapped.confidence,
        ruleTrace: {
          source: "human_review",
          actor: userId,
          role,
          fromStatus: currentCase.status,
          toStatus: status,
          comment: comment || null,
        },
      });
    }

    // Manual Flag without assignee → auto-queue
    if (status === "Flagged" && !updatedCase.assignedTo) {
      await autoAssignReviewer({ caseId, triggeredByUserId: userId });
    }

    const refreshed = await prisma.case.findUnique({ where: { id: caseId } });
    return res.json({ success: true, message: "Case updated.", data: refreshed || updatedCase });
  } catch (error) {
    console.error("Error in PATCH /api/cases/:id:", error);
    return res.status(500).json({ success: false, message: "Failed to update case." });
  }
});

/**
 * POST /api/cases/bulk-delete
 * Permanently delete one or more cases. Administrator + User only.
 */
router.post(
  "/bulk-delete",
  requireRole([...CASE_DELETE_ROLES]),
  async (req: AuthenticatedRequest, res: Response) => {
    try {
      const ids = Array.isArray(req.body?.ids)
        ? (req.body.ids as unknown[]).filter((id): id is string => typeof id === "string" && id.length > 0)
        : [];

      if (ids.length === 0) {
        return res.status(400).json({ success: false, message: "ids array is required." });
      }

      const deleted: string[] = [];
      const failed: { id: string; reason: string }[] = [];

      for (const caseId of ids) {
        try {
          const existing = await prisma.case.findUnique({
            where: { id: caseId },
            select: { id: true, createdBy: true },
          });
          if (!existing) {
            failed.push({ id: caseId, reason: "Case not found" });
            continue;
          }
          if (!canDeleteCase(req.user, existing)) {
            failed.push({ id: caseId, reason: "Not allowed to delete this case" });
            continue;
          }
          await hardDeleteCase(caseId);
          deleted.push(caseId);
        } catch (err: any) {
          console.error(`Failed to delete case ${caseId}:`, err);
          failed.push({ id: caseId, reason: err?.message || "Delete failed" });
        }
      }

      return res.json({
        success: failed.length === 0,
        message:
          deleted.length === 1
            ? "Case deleted."
            : `${deleted.length} case(s) deleted${failed.length ? `, ${failed.length} failed` : ""}.`,
        data: { deleted, failed },
      });
    } catch (error) {
      console.error("Error in POST /api/cases/bulk-delete:", error);
      return res.status(500).json({ success: false, message: "Failed to delete cases." });
    }
  }
);

/**
 * DELETE /api/cases/:id
 * Permanently delete a case and related rows. Administrator + User only.
 */
router.delete(
  "/:id",
  requireRole([...CASE_DELETE_ROLES]),
  async (req: AuthenticatedRequest, res: Response) => {
    try {
      const caseId = req.params.id as string;

      const existing = await prisma.case.findUnique({
        where: { id: caseId },
        select: { id: true, createdBy: true },
      });
      if (!existing) {
        return res.status(404).json({ success: false, message: "Case not found." });
      }
      if (!canDeleteCase(req.user, existing)) {
        return res.status(403).json({
          success: false,
          message: "You can only delete your own cases.",
        });
      }

      await hardDeleteCase(caseId);
      return res.json({ success: true, message: "Case deleted successfully." });
    } catch (error) {
      console.error("Error in DELETE /api/cases/:id:", error);
      return res.status(500).json({ success: false, message: "Failed to delete case." });
    }
  }
);

/**
 * POST /api/cases/:id/assign
 * Assign a reviewer to a case (Administrator only).
 */
router.post(
  "/:id/assign",
  requireRole("Administrator"),
  async (req: AuthenticatedRequest, res: Response) => {
    try {
      const caseId = req.params.id as string;
      const { reviewerId } = req.body;
      const userId = req.user?.userId || "USR-UNKNOWN";

      if (!reviewerId) {
        return res.status(400).json({ success: false, message: "reviewerId is required." });
      }

      const reviewer = await prisma.user.findFirst({
        where: { id: reviewerId, role: { name: "Reviewer" } },
        select: { id: true, name: true },
      });
      if (!reviewer) {
        return res.status(400).json({
          success: false,
          message: "reviewerId must be an active Reviewer account.",
        });
      }

      const updatedCase = await prisma.case.update({
        where: { id: caseId },
        data: { assignedTo: reviewerId },
      });

      await appendAuditLog({
        caseId,
        userId,
        action: "ASSIGN_REVIEWER",
        metadataJson: { reviewerId },
      });

      try {
        await prisma.notification.create({
          data: {
            userId: reviewerId,
            type: "CASE_ASSIGNED",
            message: `You were assigned case ${caseId} by an administrator.`,
          },
        });
      } catch {
        /* ignore */
      }

      return res.json({ success: true, message: "Case assigned.", data: updatedCase });
    } catch (error) {
      console.error("Error in POST /api/cases/:id/assign:", error);
      return res.status(500).json({ success: false, message: "Failed to assign case." });
    }
  }
);

/**
 * POST /api/cases/upload
 * Module 6.2: validate (magic bytes + quality) → preprocess → create case + hashes/EXIF.
 */
router.post("/upload", (req: Request, res: Response, next) => {
  upload.single("media")(req, res, (err: unknown) => {
    if (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Upload rejected by file filter.";
      return res.status(400).json({
        success: false,
        message,
        validation: { status: "REJECTED", reason: message },
      });
    }
    return next();
  });
}, async (req: Request, res: Response) => {
  try {
    const { title, subject } = req.body;
    const file = req.file;
    const authUser = (req as AuthenticatedRequest).user;
    const userId = authUser?.userId;
    const role = authUser?.role || "User";
    const accessMode = role === "User" ? "public" : "organizational";

    if (!userId) {
      safeUnlink(file?.path);
      return res.status(401).json({
        success: false,
        message: "Unauthenticated — sign in again before uploading.",
      });
    }

    if (!file) {
      return res.status(400).json({
        success: false,
        message: "No image file provided. Field name must be `media`.",
        validation: { status: "REJECTED", reason: "Missing file" },
      });
    }

    // --- 6.2 validate + preprocess (PENDING conceptually until this passes) ---
    const pipeline = await validateAndPreprocessImage({
      absolutePath: file.path,
      originalName: file.originalname,
      declaredMime: file.mimetype,
      uploadDir,
    });

    if (!pipeline.ok) {
      safeUnlink(file.path);
      return res.status(400).json({
        success: false,
        message: pipeline.validation.reason,
        validation: {
          status: "REJECTED",
          code: pipeline.validation.code,
          reason: pipeline.validation.reason,
          detectedFormat: pipeline.validation.detectedFormat,
        },
        accessMode,
      });
    }

    // Drop the raw multer file; analysis uses the processed JPEG
    safeUnlink(file.path);

    const { validation, preprocess } = pipeline;
    const fileBuffer = preprocess.buffer; // AI path
    const originalBuffer = preprocess.originalBuffer; // hash + EXIF
    const analysisMime = preprocess.mime;
    const analysisName = path.basename(preprocess.processedPath);
    const storageUrl = preprocess.storageUrl;

    const caseTitle = title || subject || file.originalname || "Untitled Case";
    const tempCaseId = `CAS-${Math.floor(100 + Math.random() * 900)}`;

    let sha256Checksum: string | null = null;
    let dhashHex: string | null = null;
    let exifData: any = null;
    let integrityAnalysis: any = null;
    let duplicateInfo: any = null;

    try {
      sha256Checksum = crypto.createHash("sha256").update(originalBuffer).digest("hex");
      dhashHex = await computeDHash(originalBuffer);

      try {
        exifData = await exifr.parse(originalBuffer);
      } catch {
        exifData = null;
      }

      integrityAnalysis = analyzeSourceIntegrity(exifData);

      try {
        const existingFingerprint = await prisma.mediaFingerprint.findFirst({
          where: {
            OR: [
              { sha256: sha256Checksum },
              dhashHex ? { dhash: dhashHex } : {},
            ].filter((cond) => Object.keys(cond).length > 0),
          },
          include: {
            mediaRef: {
              include: {
                caseRef: true,
                sourceMetadata: true,
                forgeryResults: true,
              },
            },
          },
        });

        const existingCase = existingFingerprint?.mediaRef?.caseRef;
        const ownsExisting =
          !!userId && !!existingCase && existingCase.createdBy === userId;

        if (existingFingerprint && ownsExisting && existingCase) {
          const isExact = existingFingerprint.sha256 === sha256Checksum;
          safeUnlink(preprocess.processedPath);

          return res.status(200).json({
            success: true,
            isDuplicate: true,
            matchType: isExact ? "EXACT_SHA256" : "NEAR_DUPLICATE_DHASH",
            similarityScore: isExact ? 1.0 : 0.94,
            message: isExact
              ? `Exact duplicate — opening your existing Case ${existingCase.id}`
              : `Near-duplicate — opening your existing Case ${existingCase.id}`,
            accessMode,
            validation: {
              status: "VALIDATED",
              width: validation.width,
              height: validation.height,
              format: validation.detectedFormat,
              preprocessed: preprocess.changed,
            },
            data: {
              id: existingCase.id,
              title: existingCase.title,
              subject: existingCase.title,
              status: existingCase.status,
              date: existingCase.createdAt.toISOString().split("T")[0],
              sha256: existingFingerprint.sha256,
              mediaUrl: existingFingerprint.mediaRef?.storageUrl,
              createdBy: existingCase.createdBy,
              exifData: existingFingerprint.mediaRef?.sourceMetadata?.exifJson ?? null,
              deviceFingerprint:
                existingFingerprint.mediaRef?.sourceMetadata?.deviceFingerprint ?? null,
              integrityScore:
                existingFingerprint.mediaRef?.sourceMetadata?.integrityScore ?? null,
            },
          });
        }

        if (existingFingerprint && !ownsExisting) {
          duplicateInfo = {
            isDuplicate: true,
            matchType:
              existingFingerprint.sha256 === sha256Checksum
                ? "EXACT_SHA256"
                : "NEAR_DUPLICATE_DHASH",
            note: "Image matches prior evidence in the system; your own case is still created.",
          };
        }
      } catch (dupErr) {
        console.warn("Duplicate check lookup error:", dupErr);
      }
    } catch (procErr) {
      console.warn("File processing error (SHA/dHash/EXIF):", procErr);
    }

    const newCaseItem: any = {
      id: tempCaseId,
      title: caseTitle,
      subject: caseTitle,
      status: duplicateInfo?.isDuplicate ? "Flagged" : "Analyzing",
      date: new Date().toISOString().split("T")[0],
      confidence: duplicateInfo?.isDuplicate ? "100%" : "...",
      mediaPath: storageUrl,
      mediaUrl: storageUrl,
      sha256: sha256Checksum || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      dhash: dhashHex,
      exifData,
      integrityAnalysis,
      duplicateInfo,
      accessMode,
      validation: {
        status: "VALIDATED",
        width: preprocess.width,
        height: preprocess.height,
        format: validation.detectedFormat,
        preprocessed: preprocess.changed,
        originalBytes: preprocess.originalBytes,
        processedBytes: preprocess.processedBytes,
      },
    };

    try {
      const createdCase = await prisma.case.create({
        data: {
          title: caseTitle,
          status: duplicateInfo?.isDuplicate ? "Flagged" : "Analyzing",
          createdBy: userId,
          mediaAssets: {
            create: {
              fileType: analysisMime,
              storageUrl,
              validationStatus: "VALIDATED",
              uploadedBy: userId,
              resolution: `${preprocess.width}x${preprocess.height}`,
              ...(sha256Checksum
                ? {
                    fingerprints: {
                      create: {
                        sha256: sha256Checksum,
                        ...(dhashHex ? { dhash: dhashHex, phash: dhashHex } : {}),
                      },
                    },
                  }
                : {}),
              sourceMetadata: {
                create: {
                  exifJson: exifData ?? {},
                  deviceFingerprint:
                    integrityAnalysis?.deviceFingerprint ?? "Unknown",
                  integrityScore: integrityAnalysis?.integrityScore ?? 0.95,
                },
              },
            },
          },
        },
        include: {
          mediaAssets: {
            include: {
              fingerprints: true,
              sourceMetadata: true,
            },
          },
        },
      });

      newCaseItem.id = createdCase.id;
      newCaseItem.title = createdCase.title;
      newCaseItem.subject = createdCase.title;
      newCaseItem.createdBy = userId;
      if (createdCase.mediaAssets?.[0]?.storageUrl) {
        newCaseItem.mediaUrl = createdCase.mediaAssets[0].storageUrl;
        newCaseItem.mediaPath = createdCase.mediaAssets[0].storageUrl;
      }

      await appendAuditLog({
        caseId: createdCase.id,
        userId,
        action: "CREATE_CASE",
        metadataJson: {
          source: duplicateInfo?.isDuplicate ? "Duplicate matched" : "New upload",
          fileName: file.originalname,
          validationStatus: "VALIDATED",
          accessMode,
          preprocess: {
            width: preprocess.width,
            height: preprocess.height,
            originalBytes: preprocess.originalBytes,
            processedBytes: preprocess.processedBytes,
          },
        },
      });

      const mediaAssetId = createdCase.mediaAssets?.[0]?.id;
      if (!mediaAssetId) {
        return res.status(500).json({
          success: false,
          message: "Case created but media asset missing.",
        });
      }

      // 6.9 — create VerificationJob + mark early stages
      const job = await createVerificationJob(createdCase.id, mediaAssetId);
      await updateJobStage(job.id, "UPLOAD", "PROCESSING");
      await updateJobStage(job.id, "FINGERPRINT", "PROCESSING");
      await updateJobStage(job.id, "INTEGRITY", "PROCESSING");

      newCaseItem.verificationJob = {
        id: job.id,
        status: "PROCESSING",
        stage: "INTEGRITY",
        progress: stageProgress("INTEGRITY", "PROCESSING"),
      };

      await notifyCaseEvent({
        event: "CASE_SUBMITTED",
        caseId: createdCase.id,
        caseTitle: caseTitle,
        targetUserId: userId,
        extra: accessMode,
      });

      // Cross-user duplicate starts Flagged — assign reviewer immediately
      if (createdCase.status === "Flagged") {
        await autoAssignReviewer({
          caseId: createdCase.id,
          triggeredByUserId: userId,
        });
      }

      const exifFlags: string[] = [];
      if (integrityAnalysis?.isTampered) exifFlags.push("software_detected");
      if (!exifData || Object.keys(exifData).length === 0) exifFlags.push("missing_exif");

      // 6.9 orchestrated async pipeline (forgery → decision → status)
      scheduleVerificationPipeline({
        jobId: job.id,
        caseId: createdCase.id,
        caseTitle,
        userId,
        mediaAssetId,
        fileBuffer,
        analysisName,
        analysisMime,
        exifFlags,
        integrityScore: integrityAnalysis?.integrityScore ?? null,
        fingerprintMatch: !!duplicateInfo?.isDuplicate,
        fingerprintKind:
          duplicateInfo?.matchType === "EXACT_SHA256"
            ? "exact"
            : duplicateInfo?.isDuplicate
              ? "near"
              : null,
        forceFlagged: !!duplicateInfo?.isDuplicate,
        accessMode,
      });
    } catch (dbErr) {
      safeUnlink(preprocess.processedPath);
      console.error(
        "DB error creating case — not using memory fallback for authenticated uploads:",
        dbErr
      );
      return res.status(500).json({
        success: false,
        message:
          "Failed to save case to the database. Check DATABASE_URL and that your user account exists.",
      });
    }

    return res.status(201).json({
      success: true,
      message: duplicateInfo?.isDuplicate
        ? duplicateInfo.message
        : "Image validated and preprocessed; verification pipeline started.",
      data: newCaseItem,
      duplicateInfo,
      integrityAnalysis,
      accessMode,
      validation: newCaseItem.validation,
    });
  } catch (error) {
    console.error("Error in POST /api/cases/upload:", error);
    return res.status(500).json({ success: false, message: "Failed to create case." });
  }
});

export default router;
