"""
Trust Engine — Pure computation, zero DB access.
Called by main.py endpoints. All inputs come from core-api via HTTP request body.
"""
from typing import List


def calculate_trust_score(
    forgery_score: float,
    exif_flags: List[str],
    fingerprint_match: bool,
) -> dict:
    """
    Compute a composite trust score for a media asset.

    Args:
        forgery_score: 0.0 (genuine) → 1.0 (deepfake) from the AI engine.
        exif_flags:    List of integrity flags from EXIF analysis
                       e.g. ["software_detected", "missing_exif"].
        fingerprint_match: True if this file is a known duplicate.

    Returns:
        {
            "trust_score": float (0.0 – 1.0, higher = more trustworthy),
            "risk_level":  "Authentic" | "Uncertain" | "High-Risk",
            "breakdown":   dict with per-factor scores
        }
    """

    # --- Factor weights ---
    W_FORGERY     = 0.60   # AI deepfake probability is the heaviest signal
    W_EXIF        = 0.25   # EXIF integrity is a strong supporting signal
    W_FINGERPRINT = 0.15   # Duplicate match is supplementary

    # --- Forgery factor (inverted: high forgery score = low trust) ---
    forgery_factor = 1.0 - max(0.0, min(1.0, forgery_score))

    # --- EXIF factor ---
    if not exif_flags:
        exif_factor = 1.0   # No flags = clean
    elif "software_detected" in exif_flags:
        exif_factor = 0.20  # Post-processing software found — strong signal
    elif "missing_exif" in exif_flags:
        exif_factor = 0.65  # Missing EXIF is inconclusive (social media strips it)
    else:
        exif_factor = 0.80  # Unknown minor flags

    # --- Fingerprint factor ---
    # Duplicate match means we've seen this exact image before.
    # A known original is fine; re-submission is suspicious.
    fingerprint_factor = 0.50 if fingerprint_match else 1.0

    # --- Weighted composite ---
    trust_score = (
        forgery_factor     * W_FORGERY
        + exif_factor      * W_EXIF
        + fingerprint_factor * W_FINGERPRINT
    )
    trust_score = round(max(0.0, min(1.0, trust_score)), 4)

    # --- Risk level classification ---
    if trust_score >= 0.70:
        risk_level = "Authentic"
    elif trust_score >= 0.40:
        risk_level = "Uncertain"
    else:
        risk_level = "High-Risk"

    return {
        "trust_score": trust_score,
        "risk_level": risk_level,
        "breakdown": {
            "forgery_factor": round(forgery_factor, 4),
            "exif_factor": round(exif_factor, 4),
            "fingerprint_factor": round(fingerprint_factor, 4),
        },
    }


def calculate_rolling_trust(frame_scores: List[float]) -> dict:
    """
    Compute a rolling trust score across a live webcam session.

    Args:
        frame_scores: List of per-frame forgery scores (0.0 – 1.0).
                      Most recent frames are weighted more heavily.

    Returns:
        { "trust_score": float, "risk_level": str }
    """
    if not frame_scores:
        return {"trust_score": 1.0, "risk_level": "Authentic"}

    # Exponential weighting — most recent frames count more
    n = len(frame_scores)
    weights = [2 ** i for i in range(n)]
    total_weight = sum(weights)

    weighted_forgery = sum(
        frame_scores[i] * weights[i] for i in range(n)
    ) / total_weight

    trust_score = round(1.0 - max(0.0, min(1.0, weighted_forgery)), 4)

    if trust_score >= 0.70:
        risk_level = "Authentic"
    elif trust_score >= 0.40:
        risk_level = "Uncertain"
    else:
        risk_level = "High-Risk"

    return {"trust_score": trust_score, "risk_level": risk_level}
