import { prisma } from "../db";
import { appendAuditLog } from "./audit";

/**
 * Auto-assign the least-loaded active Reviewer to a Flagged case (6.3 / 6.9).
 * Creates a notification for the reviewer when assigned.
 */
export async function autoAssignReviewer(opts: {
  caseId: string;
  triggeredByUserId?: string | null;
}): Promise<string | null> {
  try {
    const existing = await prisma.case.findUnique({
      where: { id: opts.caseId },
      select: { id: true, status: true, assignedTo: true, title: true, createdBy: true },
    });
    if (!existing) return null;
    if (existing.assignedTo) return existing.assignedTo;
    if (existing.status !== "Flagged") return null;

    const reviewers = await prisma.user.findMany({
      where: {
        isActive: true,
        role: { name: "Reviewer" },
      },
      select: {
        id: true,
        name: true,
        email: true,
        assignedCases: {
          where: { status: { in: ["Flagged", "Analyzing"] } },
          select: { id: true },
        },
      },
    });

    if (reviewers.length === 0) {
      console.warn("autoAssignReviewer: no active Reviewer accounts");
      return null;
    }

    reviewers.sort(
      (a, b) => a.assignedCases.length - b.assignedCases.length
    );
    const pick = reviewers[0]!;

    await prisma.case.update({
      where: { id: opts.caseId },
      data: { assignedTo: pick.id },
    });

    const actor =
      opts.triggeredByUserId ||
      existing.createdBy ||
      pick.id;
    await appendAuditLog({
      caseId: opts.caseId,
      userId: actor,
      action: "AUTO_ASSIGN_REVIEWER",
      metadataJson: {
        reviewerId: pick.id,
        reviewerEmail: pick.email,
        load: pick.assignedCases.length,
        system: !opts.triggeredByUserId,
      },
    });

    try {
      await prisma.notification.create({
        data: {
          userId: pick.id,
          type: "CASE_ASSIGNED",
          message: `Case "${existing.title}" was auto-assigned to your review queue (Flagged).`,
        },
      });
    } catch (nErr) {
      console.warn("autoAssign notification failed:", nErr);
    }

    if (existing.createdBy && existing.createdBy !== pick.id) {
      try {
        await prisma.notification.create({
          data: {
            userId: existing.createdBy,
            type: "CASE_FLAGGED",
            message: `Your case "${existing.title}" was flagged and queued for reviewer ${pick.name}.`,
          },
        });
      } catch {
        /* ignore */
      }
    }

    return pick.id;
  } catch (err) {
    console.warn("autoAssignReviewer failed:", err);
    return null;
  }
}
