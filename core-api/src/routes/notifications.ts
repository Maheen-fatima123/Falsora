import { Router, type Request, type Response } from "express";
import { prisma } from "../db";
import { formatNotification } from "../services/decisionEngine";

const router = Router();

/**
 * GET /api/notifications
 * Fetch all notifications for the authenticated user.
 */
router.get("/", async (req: Request, res: Response) => {
  try {
    const userId = (req as any).user?.userId;
    if (!userId) {
      return res.status(401).json({ success: false, message: "Unauthenticated" });
    }

    const notifications = await prisma.notification.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
      take: 50,
    });

    return res.json({ success: true, data: notifications });
  } catch (error) {
    console.error("Error in GET /api/notifications:", error);
    return res.status(500).json({ success: false, message: "Failed to fetch notifications." });
  }
});

/**
 * POST /api/notifications/:id/read
 * Mark a notification as read.
 */
router.post("/:id/read", async (req: Request, res: Response) => {
  try {
    const notifId = req.params.id as string;
    const updated = await prisma.notification.update({
      where: { id: notifId },
      data: { isRead: true },
    });
    return res.json({ success: true, data: updated });
  } catch (error) {
    console.error("Error in POST /api/notifications/:id/read:", error);
    return res.status(500).json({ success: false, message: "Failed to mark notification as read." });
  }
});

/**
 * POST /api/notifications/case-event
 * Create a notification for a case event.
 * Calls decision-engine for message templating, then persists via Prisma.
 * 
 * Body: { event, case_id, case_title, target_user_id, actor?, extra? }
 */
router.post("/case-event", async (req: Request, res: Response) => {
  try {
    const { event, case_id, case_title, target_user_id, actor, extra } = req.body;

    if (!event || !case_id || !case_title || !target_user_id) {
      return res.status(400).json({
        success: false,
        message: "event, case_id, case_title, and target_user_id are required.",
      });
    }

    // Get formatted message from decision-engine (degrades gracefully if offline)
    const template = await formatNotification({ event, case_id, case_title, actor, extra });

    const notification = await prisma.notification.create({
      data: {
        userId: target_user_id,
        type: template?.type ?? event,
        message: template?.message ?? `Case ${case_id} — ${event}`,
      },
    });

    return res.status(201).json({ success: true, data: notification });
  } catch (error) {
    console.error("Error in POST /api/notifications/case-event:", error);
    return res.status(500).json({ success: false, message: "Failed to create notification." });
  }
});

export default router;
