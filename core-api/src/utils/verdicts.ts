import { prisma } from "../db";

export type FinalVerdict = "GENUINE" | "MANIPULATED" | "INCONCLUSIVE";

/**
 * Persist a Verdict row for module 6.3 / 6.8 decision trail.
 * No-ops (logs) if the case has no media asset yet.
 */
export async function writeCaseVerdict(opts: {
  caseId: string;
  finalVerdict: FinalVerdict;
  confidence: number;
  ruleTrace?: Record<string, unknown>;
  mediaId?: string | null;
}): Promise<void> {
  try {
    let mediaId = opts.mediaId || null;
    if (!mediaId) {
      const asset = await prisma.mediaAsset.findFirst({
        where: { caseId: opts.caseId },
        select: { id: true },
        orderBy: { createdAt: "asc" },
      });
      mediaId = asset?.id || null;
    }
    if (!mediaId) {
      console.warn(`writeCaseVerdict: no media for case ${opts.caseId}`);
      return;
    }

    const confidence = Math.max(0, Math.min(1, opts.confidence));

    await prisma.verdict.create({
      data: {
        caseId: opts.caseId,
        mediaId,
        finalVerdict: opts.finalVerdict,
        confidence,
        ruleTraceJson: opts.ruleTrace ?? undefined,
      },
    });
  } catch (err) {
    console.warn("writeCaseVerdict failed:", err);
  }
}

export function verdictFromRisk(
  riskLevel: string | null | undefined,
  status: string
): { finalVerdict: FinalVerdict; confidence: number } {
  if (
    status === "Verified" ||
    riskLevel === "Authentic" ||
    riskLevel === "Low"
  ) {
    return { finalVerdict: "GENUINE", confidence: 0.9 };
  }
  if (riskLevel === "Uncertain" || riskLevel === "Medium") {
    return { finalVerdict: "INCONCLUSIVE", confidence: 0.55 };
  }
  if (
    status === "Flagged" ||
    riskLevel === "High-Risk" ||
    riskLevel === "High"
  ) {
    return { finalVerdict: "MANIPULATED", confidence: 0.85 };
  }
  return { finalVerdict: "INCONCLUSIVE", confidence: 0.5 };
}
