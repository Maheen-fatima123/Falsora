"""
Falsora Decision Engine — Stateless FastAPI microservice (port 8001).

Architecture rule: This service holds NO database connection.
It receives data via HTTP from core-api, performs pure computation,
and returns a result. core-api (Prisma) is the only service that
reads/writes PostgreSQL.

Endpoints:
  GET  /health
  POST /trust-score          → calculate_trust_score()
  POST /trust-score/rolling  → calculate_rolling_trust()
  POST /case-status/validate → validate_status_transition()
  POST /notifications/format → notification template helpers
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from modules.trust_engine import calculate_trust_score, calculate_rolling_trust
from modules.orchestration import validate_status_transition
from modules.notifications import (
    format_case_submitted,
    format_case_assigned,
    format_case_flagged,
    format_case_verified,
)

app = FastAPI(
    title="Falsora Decision Engine",
    description="Stateless trust-scoring and orchestration microservice. Internal use only — called by core-api.",
    version="1.0.0",
)

# Only accept requests from core-api. This service is never called
# directly from the browser frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class TrustScoreRequest(BaseModel):
    forgery_score: float
    exif_flags: Optional[List[str]] = []
    fingerprint_match: Optional[bool] = False


class RollingTrustRequest(BaseModel):
    frame_scores: List[float]


class StatusValidateRequest(BaseModel):
    current_status: str
    new_status: str


class NotificationFormatRequest(BaseModel):
    event: str             # CASE_SUBMITTED | CASE_ASSIGNED | CASE_FLAGGED | CASE_VERIFIED
    case_id: str
    case_title: str
    actor: Optional[str] = "System"
    extra: Optional[str] = None  # risk_level or verdict


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "decision-engine"}


@app.post("/trust-score")
def trust_score(data: TrustScoreRequest):
    """
    Compute a composite trust score for a static media asset upload.
    Called by core-api after EXIF + fingerprinting steps complete.
    """
    return calculate_trust_score(
        forgery_score=data.forgery_score,
        exif_flags=data.exif_flags or [],
        fingerprint_match=data.fingerprint_match or False,
    )


@app.post("/trust-score/rolling")
def rolling_trust_score(data: RollingTrustRequest):
    """
    Compute a rolling trust score across live webcam session frames.
    Called by core-api Socket.IO pipeline on each frame batch.
    """
    return calculate_rolling_trust(frame_scores=data.frame_scores)


@app.post("/case-status/validate")
def case_status_validate(data: StatusValidateRequest):
    """
    Validate whether a case status transition is permitted.
    Returns 200 with { valid: false, error: str } for invalid transitions
    (not 4xx — core-api controls the HTTP status code to the frontend).
    """
    return validate_status_transition(data.current_status, data.new_status)


@app.post("/notifications/format")
def format_notification(data: NotificationFormatRequest):
    """
    Generate a formatted notification message based on a case event.
    core-api calls this to get message text, then persists the
    Notification row itself via Prisma.
    """
    event = data.event.upper()

    if event == "CASE_SUBMITTED":
        return format_case_submitted(data.case_id, data.case_title, data.actor or "Unknown")
    elif event == "CASE_ASSIGNED":
        return format_case_assigned(data.case_id, data.case_title, data.actor or "Reviewer")
    elif event == "CASE_FLAGGED":
        return format_case_flagged(data.case_id, data.case_title, data.extra or "High-Risk")
    elif event == "CASE_VERIFIED":
        return format_case_verified(data.case_id, data.case_title, data.extra or "INCONCLUSIVE")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown event type: '{data.event}'")
