import fs from "node:fs";
import path from "node:path";
import multer from "multer";
import { Router, type Response } from "express";
import { requireAuth, type AuthenticatedRequest } from "../middleware/auth";
import { prisma } from "../db";
import { canAccessCase } from "../utils/caseAccess";
import { appendAuditLog } from "../utils/audit";

const router = Router({ mergeParams: true });

const reportsDir = path.join(process.cwd(), "uploads", "reports");
if (!fs.existsSync(reportsDir)) {
  fs.mkdirSync(reportsDir, { recursive: true });
}

const pdfUpload = multer({
  storage: multer.diskStorage({
    destination: (_req, _file, cb) => cb(null, reportsDir),
    filename: (_req, file, cb) => {
      const safe = (file.originalname || "report.pdf").replace(/[^a-zA-Z0-9._-]/g, "_");
      cb(null, `${Date.now()}-${safe}`);
    },
  }),
  limits: { fileSize: 15 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    if (
      file.mimetype === "application/pdf" ||
      file.originalname.toLowerCase().endsWith(".pdf")
    ) {
      return cb(null, true);
    }
    cb(new Error("Only PDF reports are accepted."));
  },
});

async function loadAccessibleCase(req: AuthenticatedRequest, caseId: string) {
  const dbCase = await prisma.case.findUnique({
    where: { id: caseId },
    select: { id: true, createdBy: true, assignedTo: true, status: true, title: true },
  });
  if (!dbCase) return { error: 404 as const, message: "Case not found." };
  if (
    !canAccessCase(req.user, {
      id: dbCase.id,
      createdBy: dbCase.createdBy,
      assignedTo: dbCase.assignedTo,
      status: dbCase.status,
    })
  ) {
    return { error: 403 as const, message: "You do not have access to this case." };
  }
  return { dbCase };
}

/**
 * GET /api/cases/:id/reports
 * List forensic reports linked to a case.
 */
router.get("/", requireAuth, async (req: AuthenticatedRequest, res: Response) => {
  try {
    const caseId = req.params.id as string;
    const access = await loadAccessibleCase(req, caseId);
    if ("error" in access && access.error) {
      return res.status(access.error).json({ success: false, message: access.message });
    }

    const reports = await prisma.report.findMany({
      where: { caseId },
      orderBy: { generatedAt: "desc" },
    });

    return res.json({
      success: true,
      data: reports.map((r) => ({
        id: r.id,
        caseId: r.caseId,
        generatedBy: r.generatedBy,
        pdfUrl: r.pdfUrl,
        generatedAt: r.generatedAt,
      })),
    });
  } catch (error) {
    console.error("GET reports error:", error);
    return res.status(500).json({ success: false, message: "Failed to list reports." });
  }
});

/**
 * POST /api/cases/:id/reports
 * Persist a generated forensic PDF (module 6.10).
 */
router.post(
  "/",
  requireAuth,
  (req, res, next) => {
    pdfUpload.single("pdf")(req, res, (err: unknown) => {
      if (err) {
        return res.status(400).json({
          success: false,
          message: err instanceof Error ? err.message : "PDF upload failed",
        });
      }
      return next();
    });
  },
  async (req: AuthenticatedRequest, res: Response) => {
    try {
      const caseId = req.params.id as string;
      const userId = req.user?.userId;
      if (!userId) {
        return res.status(401).json({ success: false, message: "Unauthenticated" });
      }

      const access = await loadAccessibleCase(req, caseId);
      if ("error" in access && access.error) {
        if (req.file?.path) {
          try {
            fs.unlinkSync(req.file.path);
          } catch {
            /* ignore */
          }
        }
        return res.status(access.error).json({ success: false, message: access.message });
      }

      if (!req.file) {
        return res.status(400).json({
          success: false,
          message: "PDF file required (field name: pdf).",
        });
      }

      const pdfUrl = `/uploads/reports/${req.file.filename}`;

      const report = await prisma.report.create({
        data: {
          caseId,
          generatedBy: userId,
          pdfUrl,
        },
      });

      await appendAuditLog({
        caseId,
        userId,
        action: "GENERATE_REPORT",
        metadataJson: { reportId: report.id, pdfUrl },
      });

      return res.status(201).json({
        success: true,
        message: "Forensic report saved and linked to case.",
        data: {
          id: report.id,
          caseId: report.caseId,
          generatedBy: report.generatedBy,
          pdfUrl: report.pdfUrl,
          generatedAt: report.generatedAt,
        },
      });
    } catch (error) {
      console.error("POST report error:", error);
      return res.status(500).json({ success: false, message: "Failed to save report." });
    }
  }
);

export default router;
