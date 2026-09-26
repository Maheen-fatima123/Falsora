"""
Falsora AI Engine — HTTP service (port 8000).
=================================================

Thin FastAPI wrapper around the M9 adapters already built and tested in
``falsora_ai.service`` (``StaticPredictor``, ``FramePredictor``). Those
adapters were written as process-lifetime Python classes for exactly this
purpose (see their own docstrings: "Construct once, at process startup");
this file is that process.

Endpoints match the contract documented in the shared ``openapi.yaml``
(Ujala/Mehreen's repo, "AI Engine" section):

  GET  /health
  POST /ai/forgery/analyze   — static image upload -> ForgeryResult (+ optional Explanation)
  POST /ai/frame/score       — one live frame -> FrameScore

Both predictors are constructed once in the FastAPI ``lifespan`` and reused
for every request — building them per-request would reload the model
checkpoints on every call, which is exactly the mistake both adapters'
docstrings warn against.

Run from the repo root (falsora_ai must be importable — the project venv
already has it editable-installed):

    uvicorn ai-engine.main:app --port 8000 --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from falsora_ai.common.logging import get_logger
from falsora_ai.contracts import EngineError
from falsora_ai.service.predict_frame import FramePredictor
from falsora_ai.service.predict_static import StaticPredictor

logger = get_logger(__name__)

_predictors: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading StaticPredictor (deepfake + tampering + Grad-CAM)...")
    # device="cpu" pinned deliberately: PyTorch's MPS backend has a known
    # adaptive-pooling limitation ("input sizes must be divisible by output
    # sizes") that surfaces on some face-crop sizes and is unrelated to
    # engine_66/engine_67's own tested logic. CPU is also what M7's
    # benchmark and the live ONNX path already target, so this keeps both
    # predictors on the same, more portable device.
    _predictors["static"] = StaticPredictor(device="cpu")
    logger.info("Loading FramePredictor (quantized ONNX live model)...")
    _predictors["frame"] = FramePredictor()
    logger.info("AI engine ready.")
    yield
    _predictors.clear()


app = FastAPI(title="Falsora AI Engine", version="0.1.0", lifespan=lifespan)

# Local multi-service dev: core-api (4000) and frontend (3000) call this
# directly from the browser/server side, not through a shared gateway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FrameScoreRequest(BaseModel):
    session_id: str
    frame_index: int
    frame_data: str  # base64-encoded JPEG, per openapi.yaml
    quality_ok: bool = True


def _engine_error_status(err: EngineError) -> int:
    """Map an EngineError onto an HTTP status. Decode failures are the
    caller's fault (bad upload); inference failures are ours."""
    return 422 if err.code == "decode_failed" else 500


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-engine"}


@app.post("/ai/forgery/analyze")
async def analyze_forgery(
    file: UploadFile = File(...),
    case_id: str | None = Form(default=None),
    explain: bool = Form(default=True),
) -> dict[str, Any]:
    """Static upload path (module 6.2/6.3). Accepts the raw image file
    directly (multipart) rather than a ``media_url`` — simpler and avoids
    this service needing its own credentials to fetch from core-api's
    storage."""
    predictor: StaticPredictor = _predictors["static"]
    image_bytes = await file.read()

    result, explanation = predictor.predict(image_bytes, case_id=case_id, explain=explain)

    if isinstance(result, EngineError):
        raise HTTPException(status_code=_engine_error_status(result), detail=result.model_dump(mode="json"))

    return {
        "forgery_result": result.model_dump(mode="json"),
        "explanation": explanation.model_dump(mode="json") if explanation else None,
    }


@app.post("/ai/frame/score")
def score_frame(payload: FrameScoreRequest) -> dict[str, Any]:
    """Live per-frame path (modules 6.13/6.14). One frame in, one
    ``FrameScore`` out — no rolling buffer here, that is module 6.16's job
    on the caller's side."""
    import base64

    predictor: FramePredictor = _predictors["frame"]

    try:
        frame_bytes = base64.b64decode(payload.frame_data)
    except Exception as exc:  # noqa: BLE001 — malformed base64 is a client error
        raise HTTPException(
            status_code=422,
            detail={"code": "decode_failed", "message": f"Invalid base64 frame_data: {exc}"},
        ) from exc

    score = predictor.predict(
        frame_bytes,
        session_id=payload.session_id,
        frame_index=payload.frame_index,
        quality_ok=payload.quality_ok,
    )

    if isinstance(score, EngineError):
        raise HTTPException(status_code=_engine_error_status(score), detail=score.model_dump(mode="json"))

    return score.model_dump(mode="json")
