/**
 * Decision Engine Client — core-api → decision-engine (port 8001)
 *
 * All calls are wrapped in try/catch. If the decision-engine is unreachable,
 * the caller receives a graceful null result and the case still saves with
 * trustScore: null, riskLevel: "Pending".
 */

const DECISION_ENGINE_URL =
  process.env.DECISION_ENGINE_URL || "http://localhost:8001";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TrustScoreInput {
  forgery_score: number;   // 0.0 = genuine, 1.0 = deepfake
  exif_flags: string[];    // e.g. ["software_detected", "missing_exif"]
  fingerprint_match: boolean;
}

export interface TrustScoreResult {
  trust_score: number;
  risk_level: "Authentic" | "Uncertain" | "High-Risk";
  breakdown: {
    forgery_factor: number;
    exif_factor: number;
    fingerprint_factor: number;
  };
}

export interface RollingTrustResult {
  trust_score: number;
  risk_level: "Authentic" | "Uncertain" | "High-Risk";
}

export interface StatusValidateResult {
  valid: boolean;
  new_status?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

/**
 * Get composite trust score for a static media upload.
 * Called after EXIF + fingerprinting steps in the upload pipeline.
 */
export async function getTrustScore(
  input: TrustScoreInput
): Promise<TrustScoreResult | null> {
  try {
    const res = await fetch(`${DECISION_ENGINE_URL}/trust-score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      console.warn(`[decision-engine] /trust-score returned ${res.status}`);
      return null;
    }
    return (await res.json()) as TrustScoreResult;
  } catch (err) {
    console.warn("[decision-engine] /trust-score unreachable — degrading gracefully:", err);
    return null;
  }
}

/**
 * Get rolling trust score from a batch of webcam frame scores.
 * Called by the Socket.IO pipeline for live sessions.
 */
export async function getRollingTrustScore(
  frameScores: number[]
): Promise<RollingTrustResult | null> {
  try {
    const res = await fetch(`${DECISION_ENGINE_URL}/trust-score/rolling`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame_scores: frameScores }),
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) {
      console.warn(`[decision-engine] /trust-score/rolling returned ${res.status}`);
      return null;
    }
    return (await res.json()) as RollingTrustResult;
  } catch (err) {
    console.warn("[decision-engine] /trust-score/rolling unreachable:", err);
    return null;
  }
}

/**
 * Validate a case status transition against the Falsora workflow rules.
 * Returns { valid: true, new_status } or { valid: false, error }.
 */
export async function validateStatusTransition(
  currentStatus: string,
  newStatus: string
): Promise<StatusValidateResult> {
  try {
    const res = await fetch(`${DECISION_ENGINE_URL}/case-status/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_status: currentStatus,
        new_status: newStatus,
      }),
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) {
      console.warn(`[decision-engine] /case-status/validate returned ${res.status}`);
      // Fail open — allow the transition if the service is down
      return { valid: true, new_status: newStatus };
    }
    return (await res.json()) as StatusValidateResult;
  } catch (err) {
    console.warn("[decision-engine] /case-status/validate unreachable — allowing transition:", err);
    // Fail open so a downed decision-engine doesn't block reviewers
    return { valid: true, new_status: newStatus };
  }
}

/**
 * Get a formatted notification message for a case event.
 * core-api calls this, then persists the Notification row via Prisma.
 */
export async function formatNotification(payload: {
  event: string;
  case_id: string;
  case_title: string;
  actor?: string;
  extra?: string;
}): Promise<{ type: string; message: string } | null> {
  try {
    const res = await fetch(`${DECISION_ENGINE_URL}/notifications/format`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return null;
    return (await res.json()) as { type: string; message: string };
  } catch {
    return null;
  }
}
