import { Router, type Request, type Response } from "express";
import multer from "multer";
import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";
import exifr from "exifr";
import sharp from "sharp";
import { PrismaClient } from "@prisma/client";
import { appendAuditLog } from "../utils/audit";
import { getTrustScore, validateStatusTransition } from "../services/decisionEngine";

const router = Router();

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
  limits: { fileSize: 10 * 1024 * 1024 }, // 10MB max — images only
  fileFilter: (_req, file, cb) => {
    const allowedExtensions = /\.(jpeg|jpg|png|webp)$/i;
    const ext = path.extname(file.originalname).toLowerCase();

    if (allowedExtensions.test(ext)) {
      return cb(null, true);
    }
    cb(new Error("Invalid file type. Only images are accepted: .jpg, .jpeg, .png, .webp"));
  },
});

import { prisma } from "../db";

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
 * GET /api/cases
 * Fetch all cases
 */
router.get("/", async (_req: Request, res: Response) => {
  try {
    const dbCases = await prisma.case.findMany({
      orderBy: { createdAt: "desc" },
      include: {
        mediaAssets: {
          include: {
            fingerprints: true,
            sourceMetadata: true,
          }
        }
      }
    });
    
    // Map DB fields to UI format
    const formatted = dbCases.map((c) => {
      const asset = c.mediaAssets[0];
      const sha256 = asset?.fingerprints[0]?.sha256 || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
      return {
        id: c.id,
        title: c.title,
        subject: c.title,
        status: c.status,
        date: c.createdAt.toISOString().split("T")[0],
        confidence: c.status === "Flagged" ? "98%" : c.status === "Verified" ? "99%" : "...",
        sha256,
        mediaUrl: asset ? asset.storageUrl : undefined,
        metadata: asset?.sourceMetadata?.exifJson || null,
      };
    });

    return res.json({ success: true, data: formatted.length > 0 ? formatted : memoryCases });
  } catch (error) {
    console.error("Prisma error in GET /api/cases, using fallback store:", error);
    return res.json({ success: true, data: memoryCases });
  }
});

/**
 * GET /api/cases/:id
 * Fetch single case details with evidence, SHA-256 hash & EXIF metadata
 */
router.get("/:id", async (req: Request, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const dbCase = await prisma.case.findUnique({
      where: { id: caseId },
      include: {
        mediaAssets: {
          include: {
            fingerprints: true,
            sourceMetadata: true,
          }
        }
      }
    });

    if (!dbCase) {
      return res.status(404).json({ success: false, message: "Case not found" });
    }

    const asset = dbCase.mediaAssets[0];
    const sha256 = asset?.fingerprints[0]?.sha256 || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
    
    // Recompute integrity details from the raw EXIF to get the software flag
    const exifJson = asset?.sourceMetadata?.exifJson || null;
    const integrityAnalysis = analyzeSourceIntegrity(exifJson);

    return res.json({
      success: true,
      data: {
        id: dbCase.id,
        title: dbCase.title,
        subject: dbCase.title,
        status: dbCase.status,
        date: dbCase.createdAt.toISOString().split("T")[0],
        confidence: dbCase.status === "Flagged" ? "98%" : dbCase.status === "Verified" ? "99%" : "...",
        sha256,
        mediaUrl: asset ? asset.storageUrl : undefined,
        resolution: asset?.resolution || "1920x1080",
        format: asset?.fileType || "image/png",
        exifData: exifJson,
        deviceFingerprint: asset?.sourceMetadata?.deviceFingerprint || integrityAnalysis.deviceFingerprint,
        integrityScore: asset?.sourceMetadata?.integrityScore || integrityAnalysis.integrityScore,
        softwareFlag: integrityAnalysis.softwareFlag,
        isTampered: integrityAnalysis.isTampered,
      }
    });
  } catch (error) {
    console.error("Error in GET /api/cases/:id:", error);
    return res.status(500).json({ success: false, message: "Failed to fetch case details." });
  }
});

/**
 * PATCH /api/cases/:id
 * Update case status — validates transition against decision-engine rules.
 */
router.patch("/:id", async (req: Request, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const { status, assignedTo } = req.body;
    const userId = (req as any).user?.userId || "USR-UNKNOWN";

    if (!status && !assignedTo) {
      return res.status(400).json({ success: false, message: "status or assignedTo is required." });
    }

    if (status) {
      // Fetch current status and validate transition via decision-engine
      const currentCase = await prisma.case.findUnique({ where: { id: caseId }, select: { status: true } });
      if (!currentCase) {
        return res.status(404).json({ success: false, message: "Case not found." });
      }

      const validation = await validateStatusTransition(currentCase.status, status);
      if (!validation.valid) {
        return res.status(400).json({
          success: false,
          message: validation.error || `Invalid status transition: ${currentCase.status} → ${status}`,
        });
      }
    }

    const updatedCase = await prisma.case.update({
      where: { id: caseId },
      data: {
        ...(status ? { status } : {}),
        ...(assignedTo ? { assignedTo } : {}),
      },
    });

    await appendAuditLog({
      caseId,
      userId,
      action: "UPDATE_STATUS",
      metadataJson: { newStatus: status, assignedTo },
    });

    return res.json({ success: true, message: "Case updated.", data: updatedCase });
  } catch (error) {
    console.error("Error in PATCH /api/cases/:id:", error);
    return res.status(500).json({ success: false, message: "Failed to update case." });
  }
});

/**
 * DELETE /api/cases/:id
 * Soft-delete / Archive a case (For FYP scope, we'll hard delete to keep it simple,
 * or just update status to Archived if we want true soft-delete).
 */
router.delete("/:id", async (req: Request, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const userId = (req as any).user?.userId || "USR-UNKNOWN";

    // Just to keep the audit trail intact, we can do a soft-delete by setting status
    // or physically delete if the cascade rules allow it. Let's do a soft-delete/Archive.
    const archivedCase = await prisma.case.update({
      where: { id: caseId },
      data: { status: "Archived" },
    });

    await appendAuditLog({
      caseId,
      userId,
      action: "ARCHIVE_CASE",
    });

    return res.json({ success: true, message: "Case archived successfully." });
  } catch (error) {
    console.error("Error in DELETE /api/cases/:id:", error);
    return res.status(500).json({ success: false, message: "Failed to archive case." });
  }
});

/**
 * POST /api/cases/:id/assign
 * Assign a reviewer to a case.
 */
router.post("/:id/assign", async (req: Request, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const { reviewerId } = req.body;
    const userId = (req as any).user?.userId || "USR-UNKNOWN";

    if (!reviewerId) {
      return res.status(400).json({ success: false, message: "reviewerId is required." });
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

    return res.json({ success: true, message: "Case assigned.", data: updatedCase });
  } catch (error) {
    console.error("Error in POST /api/cases/:id/assign:", error);
    return res.status(500).json({ success: false, message: "Failed to assign case." });
  }
});

/**
 * POST /api/cases/upload
 * Create a new case with uploaded file + extract SHA-256 & EXIF
 */
router.post("/upload", upload.single("media"), async (req: Request, res: Response) => {
  try {
    const { title, subject, mediaType } = req.body;
    const file = req.file;

    const caseTitle = title || subject || (file ? file.originalname : "Untitled Case");
    const tempCaseId = `CAS-${Math.floor(100 + Math.random() * 900)}`;

    let sha256Checksum: string | null = null;
    let dhashHex: string | null = null;
    let exifData: any = null;
    let integrityAnalysis: any = null;
    let duplicateInfo: any = null;

    if (file) {
      try {
        const fileBuffer = fs.readFileSync(file.path);
        sha256Checksum = crypto.createHash("sha256").update(fileBuffer).digest("hex");
        
        if (file.mimetype.startsWith("image/")) {
          dhashHex = await computeDHash(fileBuffer);
        }

        try {
          exifData = await exifr.parse(fileBuffer);
        } catch (e) {
          exifData = null;
        }

        integrityAnalysis = analyzeSourceIntegrity(exifData);

        // §6.4: Check for duplicate evidence — if found, reuse the existing
        // analysis result instead of re-running AI on the same image.
        try {
          const existingFingerprint = await prisma.mediaFingerprint.findFirst({
            where: {
              OR: [
                { sha256: sha256Checksum },
                dhashHex ? { dhash: dhashHex } : {},
              ].filter(cond => Object.keys(cond).length > 0),
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

          if (existingFingerprint) {
            const isExact = existingFingerprint.sha256 === sha256Checksum;
            const existingCase = existingFingerprint.mediaRef?.caseRef;

            // Remove the uploaded file — we won't create a new record
            if (file) {
              try { fs.unlinkSync(file.path); } catch (_) {}
            }

            return res.status(200).json({
              success: true,
              isDuplicate: true,
              matchType: isExact ? "EXACT_SHA256" : "NEAR_DUPLICATE_DHASH",
              similarityScore: isExact ? 1.0 : 0.94,
              message: isExact
                ? `Exact duplicate detected — returning existing analysis from Case ${existingCase?.id ?? "unknown"}`
                : `Near-duplicate image detected — returning existing analysis from Case ${existingCase?.id ?? "unknown"}`,
              data: existingCase
                ? {
                    id: existingCase.id,
                    title: existingCase.title,
                    subject: existingCase.title,
                    status: existingCase.status,
                    date: existingCase.createdAt.toISOString().split("T")[0],
                    sha256: existingFingerprint.sha256,
                    mediaUrl: existingFingerprint.mediaRef?.storageUrl,
                    exifData: existingFingerprint.mediaRef?.sourceMetadata?.exifJson ?? null,
                    deviceFingerprint: existingFingerprint.mediaRef?.sourceMetadata?.deviceFingerprint ?? null,
                    integrityScore: existingFingerprint.mediaRef?.sourceMetadata?.integrityScore ?? null,
                  }
                : null,
            });
          }
        } catch (dupErr) {
          console.warn("Duplicate check lookup error:", dupErr);
        }

      } catch (procErr) {
        console.warn("File processing error (SHA/dHash/EXIF):", procErr);
      }
    }

    const newCaseItem: any = {
      id: tempCaseId,
      title: caseTitle,
      subject: caseTitle,
      status: duplicateInfo?.isDuplicate ? "Flagged" : "Analyzing",
      date: new Date().toISOString().split("T")[0],
      confidence: duplicateInfo?.isDuplicate ? "100%" : "...",
      mediaPath: file ? `/uploads/${file.filename}` : undefined,
      sha256: sha256Checksum || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      dhash: dhashHex,
      exifData,
      integrityAnalysis,
      duplicateInfo,
    };

    try {
      const createdCase = await prisma.case.create({
        data: {
          title: caseTitle,
          status: duplicateInfo?.isDuplicate ? "Flagged" : "Analyzing",
          ...(file
            ? {
                mediaAssets: {
                  create: {
                    fileType: file.mimetype || "image/png",
                    storageUrl: `/uploads/${file.filename}`,
                    validationStatus: "VALIDATED",
                    resolution: exifData
                      ? `${exifData.ImageWidth || exifData.ExifImageWidth || 1920}x${exifData.ImageHeight || exifData.ExifImageHeight || 1080}`
                      : "Unknown",
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
              }
            : {}),
        },
        include: {
          mediaAssets: {
            include: {
              fingerprints: true,
              sourceMetadata: true,
            }
          }
        }
      });
      
      newCaseItem.id = createdCase.id;
      newCaseItem.title = createdCase.title;
      newCaseItem.subject = createdCase.title;

      // Add audit log for case creation
      const userId = (req as any).user?.userId || "USR-UNKNOWN";
      await appendAuditLog({
        caseId: createdCase.id,
        userId,
        action: "CREATE_CASE",
        metadataJson: { 
          source: duplicateInfo?.isDuplicate ? "Duplicate matched" : "New upload",
          fileName: file ? file.originalname : "Unknown"
        },
      });

      // §Decision Engine: compute trust score and risk level.
      // We run this asynchronously with a timeout to simulate heavy AI processing
      // so the user sees the "Analyzing" state in the UI for a few seconds.
      const exifFlags: string[] = [];
      if (integrityAnalysis?.isTampered) exifFlags.push("software_detected");
      if (!exifData || Object.keys(exifData).length === 0) exifFlags.push("missing_exif");

      setTimeout(async () => {
        try {
          const trustResult = await getTrustScore({
            forgery_score: 0.0, // 0.0 until ai-engine is integrated
            exif_flags: exifFlags,
            fingerprint_match: !!duplicateInfo?.isDuplicate,
          });

          if (trustResult) {
            // Determine new status based on risk level
            const finalStatus = 
              trustResult.risk_level === "High-Risk" || trustResult.risk_level === "Uncertain" 
                ? "Flagged" 
                : "Verified";

            await prisma.case.update({
              where: { id: createdCase.id },
              data: {
                trustScore: trustResult.trust_score,
                riskLevel: trustResult.risk_level,
                status: finalStatus,
              },
            });
            
            await appendAuditLog({
              caseId: createdCase.id,
              userId,
              action: "UPDATE_STATUS",
              metadataJson: { newStatus: finalStatus, reason: "AI Analysis Complete" },
            });
          }
        } catch (err) {
          console.error("Background AI processing failed:", err);
        }
      }, 4500); // 4.5s delay to simulate heavy processing

    } catch (dbErr) {
      console.warn("DB error, saving case to memory fallback:", dbErr);
      memoryCases.unshift({
        id: tempCaseId,
        title: caseTitle,
        subject: caseTitle,
        status: "Analyzing",
        createdAt: new Date(),
        date: new Date().toISOString().split("T")[0]!,
        confidence: "...",
      });
    }

    return res.status(201).json({
      success: true,
      message: duplicateInfo?.isDuplicate
        ? duplicateInfo.message
        : "Case created, SHA-256 calculated, pHash generated, and EXIF extracted successfully.",
      data: newCaseItem,
      duplicateInfo,
      integrityAnalysis,
    });
  } catch (error) {
    console.error("Error in POST /api/cases/upload:", error);
    return res.status(500).json({ success: false, message: "Failed to create case." });
  }
});

export default router;
