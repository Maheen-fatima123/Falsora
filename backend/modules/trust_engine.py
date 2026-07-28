def calculate_trust_score(forgery_score: float, exif_flags: list, fingerprint_match: bool) -> dict:
    # Step 1: Flip forgery_score into an authenticity value
    authenticity_from_ai = 1.0 - forgery_score

    # Step 2: Each EXIF flag reduces trust by 5%
    exif_penalty = len(exif_flags) * 0.05
    authenticity_from_exif = max(0.0, 1.0 - exif_penalty)

    # Step 3: A known duplicate gets a 20% penalty
    fingerprint_penalty = 0.20 if fingerprint_match else 0.0

    # Step 4: Weighted combination — AI carries the most weight
    weighted_score = (
        authenticity_from_ai * 0.65 +
        authenticity_from_exif * 0.25 +
        (1 - fingerprint_penalty) * 0.10
    )

    trust_score = round(weighted_score * 100, 1)

    if trust_score >= 75:
        risk_level = "Authentic"
    elif trust_score >= 40:
        risk_level = "Uncertain"
    else:
        risk_level = "High-Risk"

    return {
        "trust_score": trust_score,
        "risk_level": risk_level,
        "breakdown": {
            "ai_contribution": round(authenticity_from_ai * 65, 1),
            "exif_contribution": round(authenticity_from_exif * 25, 1),
            "fingerprint_contribution": round((1 - fingerprint_penalty) * 10, 1)
        }
    }


def calculate_rolling_trust(frame_scores: list) -> dict:
    """For live stream: average the last 5 frame authenticity scores"""
    if not frame_scores:
        return {"trust_score": 50, "risk_level": "Uncertain"}

    recent = frame_scores[-5:]
    avg = sum(recent) / len(recent)
    trust_score = round(avg * 100, 1)

    if trust_score >= 75:
        risk_level = "Authentic"
    elif trust_score >= 40:
        risk_level = "Uncertain"
    else:
        risk_level = "High-Risk"

    return {"trust_score": trust_score, "risk_level": risk_level}