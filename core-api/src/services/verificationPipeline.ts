/**
 * Module 6.9 — Verification Orchestration
 *
 * Sequences: upload → fingerprint → integrity → forgery AI → trust decision
 * → case status / verdict → optional reviewer assign. Tracks VerificationJob
 * stages so the UI can show real pipeline progress.
 */

import { prisma } from "../db";
import { appendAuditLog } from "../utils/audit";
import { autoAssignReviewer } from "../utils/autoAssign";
import { notifyCaseEvent } from "../utils/notify";
import { verdictFromRisk, writeCaseVerdict } from "../utils/verdicts";
import {
  publishEvidenceFile,
  publishExplanationArtifacts,
} from "../utils/evidenceAssets";
import { analyzeForgery } from "./aiEngine";
import { getTrustScore, isElevatedRisk } from "./decisionEngine";

export const PIPELINE_STAGES = [
  "UPLOAD",
  "FINGERPRINT",
  "INTEGRITY",
  "FORGERY",
  "DECISION",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

const PIPELINE_TIMEOUT_MS = Number(process.env.VERIFICATION_TIMEOUT_MS) || 90_000;

export function stageProgress(stage: string | null | undefined, status?: string | null): number {
  if (status === "COMPLETED") return 100;
  if (status === "FAILED") return 100;
  const idx = PIPELINE_STAGES.indexOf(stage as PipelineStage);
  if (idx < 0) return 8;
  // Mid-stage estimate: UPLOAD=12 … DECISION=88
  return Math.min(92, Math.round(((idx + 1) / PIPELINE_STAGES.length) * 88));
}

export async function createVerificationJob(caseId: string, mediaId: string) {
  return prisma.verificationJob.create({
    data: {
      caseId,
      mediaId,
      status: "PROCESSING",
      stage: "UPLOAD",
    },
  });
}

export async function updateJobStage(
  jobId: string,
  stage: PipelineStage,
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" = "PROCESSING",
  errorLog?: string | null
) {
  return prisma.verificationJob.update({
    where: { id: jobId },
    data: {
      stage,
      status,
      ...(errorLog !== undefined ? { errorLog } : {}),
    },
  });
}

async function failPipeline(opts: {
  jobId: string;
  caseId: string;
  caseTitle: string;
  userId: string;
  error: unknown;
}) {
  const msg =
    opts.error instanceof Error ? opts.error.message : String(opts.error || "Unknown error");
  console.error(`[6.9] Pipeline failed for ${opts.caseId}:`, msg);

  try {
    await updateJobStage(opts.jobId, "DECISION", "FAILED", msg.slice(0, 2000));
  } catch {
    /* ignore */
  }

  try {
    await prisma.case.update({
      where: { id: opts.caseId },
      data: {
        status: "Flagged",
        riskLevel: "High",
      },
    });
  } catch {
    /* ignore */
  }

  await appendAuditLog({
    caseId: opts.caseId,
    userId: opts.userId,
    action: "PIPELINE_FAILED",
    metadataJson: { error: msg.slice(0, 500), orchestrator: "6.9" },
  });

  await notifyCaseEvent({
    event: "ANALYSIS_FAILED",
    caseId: opts.caseId,
    caseTitle: opts.caseTitle,
    targetUserId: opts.userId,
    extra: msg.slice(0, 120),
  });

  await autoAssignReviewer({
    caseId: opts.caseId,
    triggeredByUserId: opts.userId,
  });
}

export interface PipelineRunInput {
  jobId: string;
  caseId: string;
  caseTitle: string;
  userId: string;
  mediaAssetId: string;
  fileBuffer: Buffer;
  analysisName: string;
  analysisMime: string;
  exifFlags: string[];
  integrityScore: number | null;
  fingerprintMatch: boolean;
  fingerprintKind: "exact" | "near" | null;
  /** Cross-user / prior-evidence duplicate → keep Flagged for human review */
  forceFlagged?: boolean;
  accessMode: string;
}

async function runPipelineSteps(input: PipelineRunInput): Promise<void> {
  const {
    jobId,
    caseId,
    caseTitle,
    userId,
    mediaAssetId,
    fileBuffer,
    analysisName,
    analysisMime,
    exifFlags,
    integrityScore,
    fingerprintMatch,
    fingerprintKind,
    forceFlagged,
    accessMode,
  } = input;

  // Sync stages already done at upload — mark them for UI polling
  await updateJobStage(jobId, "FINGERPRINT", "PROCESSING");
  await updateJobStage(jobId, "INTEGRITY", "PROCESSING");

  await updateJobStage(jobId, "FORGERY", "PROCESSING");

  let forgeryScore = 0.5; // cautious default if AI unavailable
  let aiAvailable = false;

  const analysis = await analyzeForgery(
    fileBuffer,
    analysisName,
    analysisMime,
    caseId
  );

  if (analysis?.forgery_result) {
    aiAvailable = true;
    const fr = analysis.forgery_result;
    const deepfakeScore = fr.deepfake?.probability_fake ?? null;
    const tamperingScore = fr.tampering?.probability_tampered ?? null;
    const syntheticScore = fr.synthetic?.probability_synthetic ?? null;

    // §6.6: the branches run independently and any one signal alone can
    // indicate forgery (a face-swap with no splicing, a spliced photo with
    // no face, or a fully AI-generated face) — so the score fed to the
    // decision engine, and the label describing it, must both come from
    // whichever branch is most suspicious (see issue #19). Ties keep the
    // earlier branch in this list.
    let manipulationType: string | null = null;
    const branches: Array<[string, number | null]> = [
      ["DEEPFAKE", deepfakeScore],
      ["TAMPERING", tamperingScore],
      ["AI_GENERATED", syntheticScore],
    ];
    for (const [label, score] of branches) {
      if (score !== null && (manipulationType === null || score > forgeryScore)) {
        manipulationType = label;
        forgeryScore = score;
      }
    }

    // Stored alongside the raw AI output (no schema change needed).
    const elaUrl = publishEvidenceFile(analysis.ela_path, "ela", caseId);

    const savedForgeryResult = await prisma.forgeryResult.create({
      data: {
        mediaId: mediaAssetId,
        modelName:
          fr.deepfake?.model_name ||
          fr.tampering?.model_name ||
          "falsora_ai",
        confidenceScore: forgeryScore,
        manipulationType,
        rawOutputJson: (elaUrl ? { ...fr, ela_url: elaUrl } : fr) as any,
      },
    });

    if (analysis.explanation) {
      const published = publishExplanationArtifacts(
        analysis.explanation,
        caseId
      );
      const overlayUrl =
        published?.overlayUrl ||
        analysis.explanation.overlay_path ||
        null;
      await prisma.evidenceVisual.create({
        data: {
          forgeryResultId: savedForgeryResult.id,
          heatmapUrl: overlayUrl || "",
          explanationText: JSON.stringify({
            method: published?.method || analysis.explanation.method,
            targetLayer:
              published?.targetLayer ||
              analysis.explanation.target_layer,
            overlayUrl: published?.overlayUrl || null,
            heatmapUrl: published?.heatmapUrl || null,
            summary:
              published?.summary ||
              `Grad-CAM (${analysis.explanation.method}) — target layer ${analysis.explanation.target_layer}`,
            faceDetected: fr.face_detected,
          }),
        },
      });
    }
  } else {
    console.warn(
      `[6.9] AI engine unreachable for ${caseId} — using cautious forgery_score 0.5`
    );
  }

  await updateJobStage(jobId, "DECISION", "PROCESSING");

  const trustResult = await getTrustScore({
    forgery_score: forgeryScore,
    exif_flags: exifFlags,
    fingerprint_match: fingerprintMatch,
    integrity_score: integrityScore,
    fingerprint_kind: fingerprintKind,
  });

  if (!trustResult) {
    throw new Error("Decision engine returned no trust score");
  }

  let finalStatus = isElevatedRisk(trustResult.risk_level)
    ? "Flagged"
    : "Verified";
  let riskLevel = trustResult.risk_level;

  // Prior-evidence / forced review path must not quietly become Verified
  if (forceFlagged && finalStatus === "Verified") {
    finalStatus = "Flagged";
    riskLevel = riskLevel === "Low" ? "Medium" : riskLevel;
  }

  // AI down → never auto-Verified
  if (!aiAvailable && finalStatus === "Verified") {
    finalStatus = "Flagged";
    riskLevel = "Medium";
  }

  await prisma.case.update({
    where: { id: caseId },
    data: {
      trustScore: trustResult.trust_score,
      riskLevel,
      status: finalStatus,
    },
  });

  await appendAuditLog({
    caseId,
    userId,
    action: "UPDATE_STATUS",
    metadataJson: {
      newStatus: finalStatus,
      reason: "AI Analysis Complete",
      riskLevel,
      legacyRiskLevel: trustResult.legacy_risk_level,
      breakdown: trustResult.breakdown,
      orchestrator: "6.9",
      aiAvailable,
      forceFlagged: !!forceFlagged,
    },
  });

  const mapped = verdictFromRisk(riskLevel, finalStatus);
  await writeCaseVerdict({
    caseId,
    mediaId: mediaAssetId,
    finalVerdict: mapped.finalVerdict,
    confidence: trustResult.trust_score ?? mapped.confidence,
    ruleTrace: {
      source: "verification_orchestration_6_9",
      ...(trustResult.rule_trace || {}),
      forgery_score: forgeryScore,
      accessMode,
      breakdown: trustResult.breakdown,
      legacy_risk_level: trustResult.legacy_risk_level,
      ai_available: aiAvailable,
    },
  });

  await updateJobStage(jobId, "DECISION", "COMPLETED");

  await notifyCaseEvent({
    event: finalStatus === "Flagged" ? "CASE_FLAGGED" : "ANALYSIS_COMPLETE",
    caseId,
    caseTitle,
    targetUserId: userId,
    extra: `Risk ${riskLevel}, trust ${Math.round(trustResult.trust_score * 100)}%`,
  });

  if (finalStatus === "Flagged") {
    await autoAssignReviewer({
      caseId,
      triggeredByUserId: userId,
    });
  }
}

/**
 * Kick off async analysis after HTTP upload returns (non-blocking).
 */
export function scheduleVerificationPipeline(
  input: PipelineRunInput,
  delayMs = 400
): void {
  setTimeout(() => {
    void (async () => {
      try {
        await Promise.race([
          runPipelineSteps(input),
          new Promise<never>((_, reject) =>
            setTimeout(
              () =>
                reject(
                  new Error(
                    `Verification pipeline timed out after ${PIPELINE_TIMEOUT_MS}ms`
                  )
                ),
              PIPELINE_TIMEOUT_MS
            )
          ),
        ]);
      } catch (err) {
        await failPipeline({
          jobId: input.jobId,
          caseId: input.caseId,
          caseTitle: input.caseTitle,
          userId: input.userId,
          error: err,
        });
      }
    })();
  }, delayMs);
}
