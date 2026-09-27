/**
 * Decision Engine Client — core-api → decision-engine (port 8001)
 *
 * Module 6.8: trust scoring with Low / Medium / High bands + rule_trace.
 * If the decision-engine is unreachable, a local fallback runs the same rules
 * so cases still get a persisted decision.
 */

const DECISION_ENGINE_URL =
  process.env.DECISION_ENGINE_URL || "http://localhost:8001";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TrustScoreInput {
  forgery_score: number;
  exif_flags: string[];
  fingerprint_match: boolean;
  integrity_score?: number | null;
  fingerprint_kind?: "exact" | "near" | null;
}

export type RiskBand = "Low" | "Medium" | "High";

export interface TrustScoreResult {
  trust_score: number;
  /** Scope §6.8 band: Low | Medium | High */
  risk_level: RiskBand | string;
  legacy_risk_level?: "Authentic" | "Uncertain" | "High-Risk" | string;
  breakdown: {
    forgery_factor: number;
    exif_factor: number;
    fingerprint_factor: number;
    weights?: { forgery: number; exif: number; fingerprint: number };
  };
  rule_trace?: Record<string, unknown>;
}

export interface RollingTrustResult {
  trust_score: number;
  risk_level: RiskBand | string;
  legacy_risk_level?: string;
}

export interface StatusValidateResult {
  valid: boolean;
  new_status?: string;
  error?: string;
}

const W_FORGERY = 0.6;
const W_EXIF = 0.25;
const W_FINGERPRINT = 0.15;
const THRESH_LOW = 0.7;
const THRESH_MEDIUM = 0.4;

/** Same rules as decision-engine/modules/trust_engine.py (offline fallback). */
export function calculateTrustScoreLocal(input: TrustScoreInput): TrustScoreResult {
  const forgery = Math.max(0, Math.min(1, input.forgery_score));
  const forgeryFactor = 1 - forgery;
  const flags = input.exif_flags || [];
  const rulesFired: string[] = [];

  if (forgery >= 0.7) rulesFired.push("forgery_high_probability");
  else if (forgery >= 0.4) rulesFired.push("forgery_moderate_probability");
  else rulesFired.push("forgery_low_probability");

  let exifFactor = 1;
  if (typeof input.integrity_score === "number" && !Number.isNaN(input.integrity_score)) {
    exifFactor = Math.max(0, Math.min(1, input.integrity_score));
    rulesFired.push("exif_integrity_score_used");
  } else if (!flags.length) {
    exifFactor = 1;
    rulesFired.push("exif_clean_no_flags");
  } else if (flags.includes("software_detected")) {
    exifFactor = 0.2;
    rulesFired.push("exif_editing_software_detected");
  } else if (flags.includes("missing_exif")) {
    exifFactor = 0.7;
    rulesFired.push("exif_missing_inconclusive");
  } else if (flags.includes("timestamp_inconsistent")) {
    exifFactor = 0.45;
    rulesFired.push("exif_timestamp_inconsistent");
  } else {
    exifFactor = 0.8;
    rulesFired.push("exif_minor_unknown_flags");
  }

  let fingerprintFactor = 1;
  if (!input.fingerprint_match) {
    rulesFired.push("fingerprint_no_prior_match");
  } else if (input.fingerprint_kind === "exact") {
    fingerprintFactor = 0.45;
    rulesFired.push("fingerprint_exact_duplicate");
  } else if (input.fingerprint_kind === "near") {
    fingerprintFactor = 0.6;
    rulesFired.push("fingerprint_near_duplicate");
  } else {
    fingerprintFactor = 0.5;
    rulesFired.push("fingerprint_duplicate_unspecified");
  }

  let trust =
    forgeryFactor * W_FORGERY +
    exifFactor * W_EXIF +
    fingerprintFactor * W_FINGERPRINT;
  trust = Math.round(Math.max(0, Math.min(1, trust)) * 10000) / 10000;

  const risk_level: RiskBand =
    trust >= THRESH_LOW ? "Low" : trust >= THRESH_MEDIUM ? "Medium" : "High";
  const legacy =
    risk_level === "Low"
      ? "Authentic"
      : risk_level === "Medium"
        ? "Uncertain"
        : "High-Risk";

  rulesFired.push(`classify_${risk_level.toLowerCase()}_risk_band`);

  return {
    trust_score: trust,
    risk_level,
    legacy_risk_level: legacy,
    breakdown: {
      forgery_factor: Math.round(forgeryFactor * 10000) / 10000,
      exif_factor: Math.round(exifFactor * 10000) / 10000,
      fingerprint_factor: Math.round(fingerprintFactor * 10000) / 10000,
      weights: { forgery: W_FORGERY, exif: W_EXIF, fingerprint: W_FINGERPRINT },
    },
    rule_trace: {
      module: "6.8 Decision Intelligence Engine (local fallback)",
      weights: { forgery: W_FORGERY, exif: W_EXIF, fingerprint: W_FINGERPRINT },
      thresholds: { low_min_trust: THRESH_LOW, medium_min_trust: THRESH_MEDIUM },
      inputs: {
        forgery_score: forgery,
        exif_flags: flags,
        integrity_score: input.integrity_score ?? null,
        fingerprint_match: input.fingerprint_match,
        fingerprint_kind: input.fingerprint_kind ?? null,
      },
      rules_fired: rulesFired,
      decision: {
        trust_score: trust,
        risk_level,
        legacy_risk_level: legacy,
        recommended_case_status: risk_level === "Low" ? "Verified" : "Flagged",
      },
    },
  };
}

/** True when case should enter Flagged / review queue. */
export function isElevatedRisk(risk: string | null | undefined): boolean {
  return (
    risk === "High" ||
    risk === "Medium" ||
    risk === "High-Risk" ||
    risk === "Uncertain"
  );
}

export function isLowRisk(risk: string | null | undefined): boolean {
  return risk === "Low" || risk === "Authentic";
}

/**
 * Get composite trust score for a static media upload.
 */
export async function getTrustScore(
  input: TrustScoreInput
): Promise<TrustScoreResult | null> {
  try {
    const res = await fetch(`${DECISION_ENGINE_URL}/trust-score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        forgery_score: input.forgery_score,
        exif_flags: input.exif_flags,
        fingerprint_match: input.fingerprint_match,
        integrity_score: input.integrity_score ?? null,
        fingerprint_kind: input.fingerprint_kind ?? null,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      console.warn(`[decision-engine] /trust-score returned ${res.status} — using local fallback`);
      return calculateTrustScoreLocal(input);
    }
    const data = (await res.json()) as TrustScoreResult;
    // Normalize older engines that only returned Authentic/Uncertain/High-Risk
    if (data.risk_level === "Authentic") data.risk_level = "Low";
    if (data.risk_level === "Uncertain") data.risk_level = "Medium";
    if (data.risk_level === "High-Risk") data.risk_level = "High";
    return data;
  } catch (err) {
    console.warn("[decision-engine] unreachable — local 6.8 fallback:", err);
    return calculateTrustScoreLocal(input);
  }
}

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

/** Mirror of decision-engine/modules/orchestration.py (6.9 fail-closed local). */
export const VALID_STATUS_TRANSITIONS: Record<string, string[]> = {
  Analyzing: ["Flagged", "Verified", "Archived"],
  Flagged: ["Verified", "Analyzing", "Archived"],
  Verified: ["Archived"],
  Archived: ["Flagged", "Verified"],
};

export function validateStatusTransitionLocal(
  currentStatus: string,
  newStatus: string
): StatusValidateResult {
  if (currentStatus === newStatus) {
    return { valid: true, new_status: newStatus };
  }
  const allowed = VALID_STATUS_TRANSITIONS[currentStatus];
  if (!allowed) {
    return {
      valid: false,
      error: `Unknown current status: '${currentStatus}'`,
    };
  }
  if (!allowed.includes(newStatus)) {
    return {
      valid: false,
      error: `Cannot transition from '${currentStatus}' to '${newStatus}'. Allowed: ${allowed.join(", ")}`,
    };
  }
  return { valid: true, new_status: newStatus };
}

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
      console.warn(
        `[decision-engine] /case-status/validate returned ${res.status} — local 6.9 rules`
      );
      return validateStatusTransitionLocal(currentStatus, newStatus);
    }
    return (await res.json()) as StatusValidateResult;
  } catch (err) {
    console.warn(
      "[decision-engine] /case-status/validate unreachable — local 6.9 rules:",
      err
    );
    return validateStatusTransitionLocal(currentStatus, newStatus);
  }
}

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
