"""
Trust Engine — Pure computation, zero DB access (module 6.8).
Called by main.py endpoints. All inputs come from core-api via HTTP request body.
"""
from __future__ import annotations

from typing import Any, List, Optional


# Canonical bands aligned with scope §6.8 (Low / Medium / High).
# Legacy aliases kept in rule_trace for older UI copy.
BAND_LOW = "Low"
BAND_MEDIUM = "Medium"
BAND_HIGH = "High"

LEGACY_ALIAS = {
    BAND_LOW: "Authentic",
    BAND_MEDIUM: "Uncertain",
    BAND_HIGH: "High-Risk",
}

# Thresholds (trust_score is higher = more trustworthy)
THRESH_LOW = 0.70      # >= Low (Authentic)
THRESH_MEDIUM = 0.40   # >= Medium (Uncertain); else High


def _band_from_trust(trust_score: float) -> str:
    if trust_score >= THRESH_LOW:
        return BAND_LOW
    if trust_score >= THRESH_MEDIUM:
        return BAND_MEDIUM
    return BAND_HIGH


def calculate_trust_score(
    forgery_score: float,
    exif_flags: Optional[List[str]] = None,
    fingerprint_match: bool = False,
    integrity_score: Optional[float] = None,
    fingerprint_kind: Optional[str] = None,
) -> dict:
    """
    Compute a composite authenticity / trust score for a media asset.

    Args:
        forgery_score: 0.0 (genuine) → 1.0 (manipulated) from AI (6.6).
        exif_flags: integrity flags e.g. ["software_detected", "missing_exif"].
        fingerprint_match: True if duplicate / near-duplicate evidence exists.
        integrity_score: optional 0–1 source-integrity score from EXIF module.
        fingerprint_kind: "exact" | "near" | None — softens near-dup penalty.

    Returns:
        trust_score, risk_level (Low|Medium|High), legacy_risk_level,
        breakdown, rule_trace
    """
    exif_flags = list(exif_flags or [])

    # --- Factor weights (must sum to 1.0) ---
    W_FORGERY = 0.60
    W_EXIF = 0.25
    W_FINGERPRINT = 0.15

    rules_fired: List[str] = []

    # --- Forgery factor (inverted) ---
    forgery_clamped = max(0.0, min(1.0, float(forgery_score)))
    forgery_factor = 1.0 - forgery_clamped
    if forgery_clamped >= 0.70:
        rules_fired.append("forgery_high_probability")
    elif forgery_clamped >= 0.40:
        rules_fired.append("forgery_moderate_probability")
    else:
        rules_fired.append("forgery_low_probability")

    # --- EXIF / source-integrity factor ---
    if integrity_score is not None:
        try:
            exif_factor = max(0.0, min(1.0, float(integrity_score)))
            rules_fired.append("exif_integrity_score_used")
        except (TypeError, ValueError):
            integrity_score = None
            exif_factor = 1.0

    if integrity_score is None:
        if not exif_flags:
            exif_factor = 1.0
            rules_fired.append("exif_clean_no_flags")
        elif "software_detected" in exif_flags:
            exif_factor = 0.20
            rules_fired.append("exif_editing_software_detected")
        elif "missing_exif" in exif_flags:
            # Social platforms strip EXIF — inconclusive, not automatic High
            exif_factor = 0.70
            rules_fired.append("exif_missing_inconclusive")
        elif "timestamp_inconsistent" in exif_flags:
            exif_factor = 0.45
            rules_fired.append("exif_timestamp_inconsistent")
        else:
            exif_factor = 0.80
            rules_fired.append("exif_minor_unknown_flags")

    # --- Fingerprint / dedup factor ---
    kind = (fingerprint_kind or "").lower() if fingerprint_match else ""
    if not fingerprint_match:
        fingerprint_factor = 1.0
        rules_fired.append("fingerprint_no_prior_match")
    elif kind == "exact":
        fingerprint_factor = 0.45
        rules_fired.append("fingerprint_exact_duplicate")
    elif kind == "near":
        fingerprint_factor = 0.60
        rules_fired.append("fingerprint_near_duplicate")
    else:
        fingerprint_factor = 0.50
        rules_fired.append("fingerprint_duplicate_unspecified")

    # --- Weighted composite ---
    trust_score = (
        forgery_factor * W_FORGERY
        + exif_factor * W_EXIF
        + fingerprint_factor * W_FINGERPRINT
    )
    trust_score = round(max(0.0, min(1.0, trust_score)), 4)

    risk_level = _band_from_trust(trust_score)
    legacy_risk_level = LEGACY_ALIAS[risk_level]

    if risk_level == BAND_HIGH:
        rules_fired.append("classify_high_risk_band")
    elif risk_level == BAND_MEDIUM:
        rules_fired.append("classify_medium_risk_band")
    else:
        rules_fired.append("classify_low_risk_band")

    rule_trace: dict[str, Any] = {
        "module": "6.8 Decision Intelligence Engine",
        "weights": {
            "forgery": W_FORGERY,
            "exif": W_EXIF,
            "fingerprint": W_FINGERPRINT,
        },
        "thresholds": {
            "low_min_trust": THRESH_LOW,
            "medium_min_trust": THRESH_MEDIUM,
        },
        "inputs": {
            "forgery_score": round(forgery_clamped, 4),
            "exif_flags": exif_flags,
            "integrity_score": integrity_score,
            "fingerprint_match": bool(fingerprint_match),
            "fingerprint_kind": fingerprint_kind,
        },
        "rules_fired": rules_fired,
        "decision": {
            "trust_score": trust_score,
            "risk_level": risk_level,
            "legacy_risk_level": legacy_risk_level,
            "recommended_case_status": (
                "Verified" if risk_level == BAND_LOW else "Flagged"
            ),
        },
    }

    return {
        "trust_score": trust_score,
        "risk_level": risk_level,
        "legacy_risk_level": legacy_risk_level,
        "breakdown": {
            "forgery_factor": round(forgery_factor, 4),
            "exif_factor": round(exif_factor, 4),
            "fingerprint_factor": round(fingerprint_factor, 4),
            "weights": {
                "forgery": W_FORGERY,
                "exif": W_EXIF,
                "fingerprint": W_FINGERPRINT,
            },
        },
        "rule_trace": rule_trace,
    }


def calculate_rolling_trust(frame_scores: List[float]) -> dict:
    """
    Compute a rolling trust score across a live webcam session.
    """
    if not frame_scores:
        return {
            "trust_score": 1.0,
            "risk_level": BAND_LOW,
            "legacy_risk_level": LEGACY_ALIAS[BAND_LOW],
        }

    n = len(frame_scores)
    weights = [2 ** i for i in range(n)]
    total_weight = sum(weights)

    weighted_forgery = sum(
        frame_scores[i] * weights[i] for i in range(n)
    ) / total_weight

    trust_score = round(1.0 - max(0.0, min(1.0, weighted_forgery)), 4)
    risk_level = _band_from_trust(trust_score)

    return {
        "trust_score": trust_score,
        "risk_level": risk_level,
        "legacy_risk_level": LEGACY_ALIAS[risk_level],
    }
