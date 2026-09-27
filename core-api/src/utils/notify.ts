import { prisma } from "../db";
import { formatNotification } from "../services/decisionEngine";

/**
 * Persist an in-app notification for a case workflow event (6.9 / 6.12).
 * Uses decision-engine templates when available; always falls back locally.
 */
export async function notifyCaseEvent(opts: {
  event: string;
  caseId: string;
  caseTitle: string;
  targetUserId: string;
  actor?: string;
  extra?: string;
}): Promise<void> {
  if (!opts.targetUserId) return;
  try {
    const template = await formatNotification({
      event: opts.event,
      case_id: opts.caseId,
      case_title: opts.caseTitle,
      ...(opts.actor ? { actor: opts.actor } : {}),
      ...(opts.extra ? { extra: opts.extra } : {}),
    });

    await prisma.notification.create({
      data: {
        userId: opts.targetUserId,
        type: template?.type ?? opts.event,
        message:
          template?.message ??
          `Case "${opts.caseTitle}" — ${opts.event}${opts.extra ? `: ${opts.extra}` : ""}`,
      },
    });
  } catch (err) {
    console.warn("notifyCaseEvent failed:", err);
  }
}
