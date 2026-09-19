import { Router, type Request, type Response } from "express";
import { prisma } from "../db";
import { requireAuth, type AuthenticatedRequest } from "../middleware/auth";

const router = Router();

/**
 * GET /api/streams
 * Fetch all streams
 */
router.get("/", requireAuth, async (_req: AuthenticatedRequest, res: Response) => {
  try {
    const sessions = await prisma.streamSession.findMany({
      include: { caseRef: true },
      orderBy: { startedAt: 'desc' }
    });
    return res.json({ success: true, data: sessions });
  } catch (error) {
    console.error("Error fetching streams:", error);
    return res.status(500).json({ success: false, error: "Failed to fetch streams" });
  }
});

/**
 * POST /api/streams
 * Add a new live stream
 */
router.post("/", requireAuth, async (req: AuthenticatedRequest, res: Response) => {
  try {
    const { title } = req.body;
    const sessionTitle = title || "Live Webcam Session - " + new Date().toLocaleTimeString();
    const userId = req.user?.userId || "SYS";
    
    // 1. Create the associated Case
    const newCase = await prisma.case.create({
      data: {
        title: sessionTitle,
        description: "Live webcam session analysis.",
        status: "Analyzing",
        priority: "Medium",
        format: "video/webm",
        reporterId: userId,
      }
    });

    // 2. Create the Stream Session
    const newStream = await prisma.streamSession.create({
      data: {
        caseId: newCase.id,
        hostId: "HOST-001",
        status: "ACTIVE",
      },
      include: { caseRef: true }
    });

    return res.status(201).json({
      success: true,
      message: "Webcam session started successfully.",
      data: newStream,
    });
  } catch (error) {
    console.error("Error creating stream:", error);
    return res.status(500).json({ success: false, message: "Failed to start webcam session." });
  }
});

/**
 * POST /api/streams/:id/end
 * End an active stream session
 */
router.post("/:id/end", requireAuth, async (req: AuthenticatedRequest, res: Response) => {
  try {
    const id = req.params.id as string;
    const session = await prisma.streamSession.update({
      where: { id },
      data: {
        status: "ENDED",
        endedAt: new Date(),
      },
      include: { caseRef: true }
    });
    
    // Also update the associated case status
    await prisma.case.update({
      where: { id: session.caseId },
      data: { status: "Verified" } // Or whatever terminal status makes sense
    });

    return res.json({ success: true, data: session });
  } catch (error) {
    console.error("Error ending stream:", error);
    return res.status(500).json({ success: false, message: "Failed to end stream session." });
  }
});

/**
 * DELETE /api/streams/:id
 * Remove a stream
 */
router.delete("/:id", requireAuth, async (req: AuthenticatedRequest, res: Response) => {
  try {
    const id = req.params.id as string;
    const session = await prisma.streamSession.findUnique({ where: { id } });
    if (session) {
      await prisma.streamSession.delete({ where: { id } });
      await prisma.case.delete({ where: { id: session.caseId } }).catch(() => {});
    }
    return res.json({ success: true, message: "Session removed." });
  } catch (error) {
    console.error("Error deleting stream:", error);
    return res.status(500).json({ success: false, message: "Failed to delete session." });
  }
});

export default router;
