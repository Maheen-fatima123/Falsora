"""
Falsora AI Engine — Integration Contracts
=========================================

This module is the **integration surface** between the AI & Forensic Engine
(Maheen, modules 6.6 / 6.7 / 6.16 / Model Optimization) and the rest of the
Falsora system:

    * Ujala   — 6.2 Media Processing, 6.13 Live Session Mgmt, 6.14 WebRTC/WebSocket,
                API integration
    * Mehreen — 6.8 Decision Intelligence, 6.10 Forensic Reports, 6.12 Notifications,
                6.15 Stream Quality

Every value that crosses a module boundary is defined here as a Pydantic model.
No other module may invent its own cross-boundary payload shape.

DESIGN RULES
------------
1. This file has **no heavy dependencies**. It must import without torch,
   OpenCV, or any model weights. Ujala's FastAPI layer and Mehreen's decision
   engine import it directly; neither should be forced to install CUDA.

2. The AI engine reports **evidence and probabilities**. It does NOT assign the
   final Low / Medium / High risk band for a verification case — that is the
   Decision Intelligence Engine (6.8, Mehreen). The one exception is
   ``LiveRiskState``, which exists solely so module 6.16 can fire the real-time
   HIGH-RISK alert mandated by scope section 5.1 Stage 4.

3. ``SCHEMA_VERSION`` is bumped on any breaking change and announced to the
   team. Consumers should assert on it.

CONVENTIONS
-----------
* ``probability_fake`` — probability the media is manipulated. Higher = worse.
* ``authenticity``     — probability the media is genuine. Higher = better.
  These are complements: ``authenticity == 1.0 - probability_fake``.

  The scope document uses the *authenticity* convention for live streaming
  ("< 0.35 authenticity" is HIGH-RISK, section 5.1 Stage 4), while ML
  convention trains on P(fake). Both are exposed explicitly so no one has to
  guess which direction a number points. Mixing these up silently inverts the
  whole system, so the conversion lives in one place: ``FrameScore``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

SCHEMA_VERSION = "1.0.0"

__all__ = [
    "SCHEMA_VERSION",
    "Label",
    "AnalysisMode",
    "LiveRiskState",
    "BoundingBox",
    "FaceDetection",
    "DeepfakeSignal",
    "TamperingSignal",
    "ForgeryResult",
    "Explanation",
    "FrameScore",
    "RollingScoreState",
    "EngineError",
]


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Label(str, Enum):
    """Ground-truth / predicted class. Values match dataset folder naming."""

    REAL = "real"
    FAKE = "fake"


class AnalysisMode(str, Enum):
    """Which pipeline produced a result.

    STATIC uses the full-accuracy backbone (EfficientNet-B3/B4).
    LIVE uses the quantized EfficientNet-B0 required by scope section 5.1.
    Results from the two are NOT directly comparable and must be labelled.
    """

    STATIC = "static"
    LIVE = "live"


class LiveRiskState(str, Enum):
    """Real-time alert state for module 6.16 only.

    This is deliberately *not* the case-level risk band. Module 6.8 (Mehreen)
    owns Low/Medium/High for verification cases. This enum exists only to drive
    the live WebSocket alert described in scope section 5.1 Stage 4.
    """

    OK = "ok"
    WATCH = "watch"
    HIGH_RISK = "high_risk"
    INSUFFICIENT_DATA = "insufficient_data"


# --------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------


class _Base(BaseModel):
    """Shared config: reject unknown fields so contract drift fails loudly.

    ``extra="forbid"`` is deliberate — if Ujala or Mehreen sends a field we do
    not recognise, we want a loud error at the boundary rather than a value
    silently dropped.

    That strictness collides with ``@computed_field``: derived values such as
    ``authenticity`` and ``width`` are *written* during serialisation but are
    not accepted as *input*, so a plain
    ``Model.model_validate(json.loads(model.model_dump_json()))`` round-trip
    fails. Since these payloads genuinely do cross the network as JSON, the
    round-trip has to work. The validator below strips computed fields from
    incoming data before validation, which keeps both properties: derived
    values are visible to JSON consumers, and unknown fields are still
    rejected.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        validate_assignment=True,
        use_enum_values=False,
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_computed_fields(cls, data: Any) -> Any:
        """Discard round-tripped computed fields so ``extra='forbid'`` survives."""
        if isinstance(data, dict):
            computed = cls.model_computed_fields
            if computed:
                overlap = computed.keys() & data.keys()
                if overlap:
                    return {k: v for k, v in data.items() if k not in overlap}
        return data


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Geometry / face detection
# --------------------------------------------------------------------------


class BoundingBox(_Base):
    """Axis-aligned box in **absolute pixel coordinates** of the source image.

    Origin is top-left, matching OpenCV and PIL. Coordinates are floats because
    detectors return sub-pixel boxes; consumers should round only at draw time.
    """

    x1: float = Field(..., description="Left edge, pixels")
    y1: float = Field(..., description="Top edge, pixels")
    x2: float = Field(..., description="Right edge, pixels")
    y2: float = Field(..., description="Bottom edge, pixels")

    @model_validator(mode="after")
    def _check_ordering(self) -> BoundingBox:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError(
                f"Degenerate bounding box: ({self.x1}, {self.y1}) -> ({self.x2}, {self.y2}). "
                "Expected x2 > x1 and y2 > y1."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @computed_field  # type: ignore[prop-decorator]
    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height


class FaceDetection(_Base):
    """A single detected face.

    ``margin`` records how much context was added around the raw detector box
    before cropping. Train and inference MUST use the same margin or the model
    sees a different framing than it was trained on.
    """

    box: BoundingBox
    confidence: float = Field(..., ge=0.0, le=1.0)
    margin: float = Field(
        default=0.0,
        ge=0.0,
        description="Fractional context expansion applied to the box (0.3 = +30%).",
    )
    detector: str = Field(default="mtcnn", description="Detector identifier.")


# --------------------------------------------------------------------------
# Module 6.6 — signals and result
# --------------------------------------------------------------------------


class DeepfakeSignal(_Base):
    """Output of branch A: AI face-forgery detection (EfficientNet)."""

    probability_fake: float = Field(
        ..., ge=0.0, le=1.0, description="P(face is AI-manipulated)."
    )
    model_name: str = Field(..., description="e.g. 'efficientnet_b0'")
    model_version: str = Field(..., description="Training run identifier.")
    input_size: int = Field(..., gt=0, description="Square input resolution used.")
    quantized: bool = Field(
        default=False, description="True if INT8 quantized (live path)."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def authenticity(self) -> float:
        return 1.0 - self.probability_fake


class TamperingSignal(_Base):
    """Output of branch B: classical tampering detection (CASIA v2.0 trained).

    Operates on the **whole image**, not the face crop — splicing and copy-move
    artefacts are global and would be cropped away.
    """

    probability_tampered: float = Field(
        ..., ge=0.0, le=1.0, description="P(image was spliced / copy-moved / edited)."
    )
    ela_score: float | None = Field(
        default=None, ge=0.0, description="Error Level Analysis summary statistic."
    )
    residual_score: float | None = Field(
        default=None, ge=0.0, description="Noise-residual inconsistency statistic."
    )
    model_name: str = Field(default="tampering_ela_cnn")
    model_version: str = Field(default="unversioned")


class ForgeryResult(_Base):
    """**Module 6.6 output.** The primary AI evidence payload.

    Consumed by:
      * 6.7  (Grad-CAM)                 — to explain the deepfake decision
      * 6.8  (Decision Intelligence)    — to fuse with metadata into a Trust Score
      * 6.10 (Forensic Report)          — as documented evidence
      * 6.16 (Rolling Score)            — via ``FrameScore`` in live mode

    Note what is absent: there is no ``risk_level`` field. Assigning
    Low/Medium/High is module 6.8's responsibility, and duplicating it here
    would let the two disagree.
    """

    result_id: UUID = Field(default_factory=uuid4)
    case_id: str | None = Field(
        default=None, description="Verification case UUID from module 6.3 (Ujala)."
    )
    mode: AnalysisMode = AnalysisMode.STATIC

    face_detected: bool = Field(
        ..., description="False means no face was found; deepfake signal is unreliable."
    )
    face: FaceDetection | None = None

    deepfake: DeepfakeSignal | None = Field(
        default=None, description="None when no face was detected."
    )
    tampering: TamperingSignal | None = Field(
        default=None, description="None when the tampering branch was skipped."
    )

    latency_ms: float = Field(..., ge=0.0, description="Wall-clock inference time.")
    created_at: datetime = Field(default_factory=_utcnow)
    schema_version: str = Field(default=SCHEMA_VERSION)
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal conditions, e.g. 'low_resolution', 'multiple_faces'.",
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> ForgeryResult:
        if self.face_detected and self.face is None:
            raise ValueError("face_detected=True but no FaceDetection was supplied.")
        if not self.face_detected and self.deepfake is not None:
            raise ValueError(
                "A deepfake signal was produced without a detected face. "
                "The deepfake branch operates on face crops only."
            )
        if self.deepfake is None and self.tampering is None:
            raise ValueError(
                "ForgeryResult carries no signal at all. At least one of "
                "'deepfake' or 'tampering' must be present."
            )
        return self

    @property
    def has_deepfake_signal(self) -> bool:
        return self.deepfake is not None

    @property
    def has_tampering_signal(self) -> bool:
        return self.tampering is not None


# --------------------------------------------------------------------------
# Module 6.7 — interpretability
# --------------------------------------------------------------------------


class Explanation(_Base):
    """**Module 6.7 output.** Visual evidence for a ``ForgeryResult``.

    The heatmap is persisted to disk rather than inlined so that large PNGs do
    not travel through the WebSocket or sit in the database. ``overlay_path`` is
    what the UI displays; ``heatmap_path`` is the raw activation map retained
    for the forensic report.
    """

    explanation_id: UUID = Field(default_factory=uuid4)
    result_id: UUID = Field(..., description="The ForgeryResult this explains.")

    method: str = Field(default="gradcam", description="'gradcam' | 'gradcam++'")
    target_layer: str = Field(..., description="Backbone layer the CAM was taken from.")

    overlay_path: str = Field(..., description="Heatmap composited over the face crop.")
    heatmap_path: str | None = Field(default=None, description="Raw heatmap PNG.")

    salient_regions: list[BoundingBox] = Field(
        default_factory=list,
        description="Highest-activation regions, for report annotation.",
    )
    created_at: datetime = Field(default_factory=_utcnow)
    schema_version: str = Field(default=SCHEMA_VERSION)


# --------------------------------------------------------------------------
# Module 6.16 — live frame scoring
# --------------------------------------------------------------------------


class FrameScore(_Base):
    """One analysed live frame. **Input to module 6.16.**

    Produced by the live inference path and pushed into the frame buffer.

    This class is the single place where the P(fake) <-> authenticity
    conversion happens. Construct it with ``probability_fake``; read
    ``authenticity`` for anything that compares against the scope's 0.35
    HIGH-RISK threshold.
    """

    session_id: str = Field(..., description="Live session UUID from module 6.13.")
    frame_index: int = Field(..., ge=0, description="Monotonic index within session.")
    probability_fake: float = Field(..., ge=0.0, le=1.0)

    captured_at: datetime = Field(default_factory=_utcnow)
    latency_ms: float = Field(default=0.0, ge=0.0)
    face_detected: bool = Field(default=True)
    quality_ok: bool = Field(
        default=True,
        description=(
            "False when module 6.15 (Mehreen) reports degraded stream quality. "
            "Low-quality frames are buffered but down-weighted."
        ),
    )
    snapshot_path: str | None = Field(
        default=None, description="Retained frame image, set when evidence is saved."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def authenticity(self) -> float:
        """P(frame is genuine). Compare against thresholds in this direction."""
        return 1.0 - self.probability_fake


class RollingScoreState(_Base):
    """**Module 6.16 output.** Smoothed live verdict over the frame buffer.

    Streamed back to the browser over Ujala's WebSocket (6.14) and used by
    Mehreen's notification module (6.12) when ``alert_triggered`` is True.
    """

    session_id: str
    rolling_authenticity: float = Field(
        ..., ge=0.0, le=1.0, description="Mean authenticity across the buffer."
    )
    frames_in_buffer: int = Field(..., ge=0)
    buffer_capacity: int = Field(..., gt=0)
    frames_processed_total: int = Field(..., ge=0)

    risk_state: LiveRiskState
    alert_triggered: bool = Field(
        default=False,
        description="True only on the transition into HIGH_RISK, not while it persists.",
    )
    evidence_paths: list[str] = Field(
        default_factory=list,
        description="Snapshots saved when the alert fired (scope 6.16).",
    )

    updated_at: datetime = Field(default_factory=_utcnow)
    schema_version: str = Field(default=SCHEMA_VERSION)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rolling_probability_fake(self) -> float:
        return 1.0 - self.rolling_authenticity

    @property
    def buffer_full(self) -> bool:
        return self.frames_in_buffer >= self.buffer_capacity


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class EngineError(_Base):
    """Structured failure payload.

    The AI engine returns this instead of raising across a module boundary, so
    that Ujala's API layer can serialise a useful message rather than a 500.
    """

    code: str = Field(..., description="Stable machine-readable code.")
    message: str = Field(..., description="Human-readable explanation.")
    module: str = Field(..., description="Originating module, e.g. '6.6'.")
    recoverable: bool = Field(default=True)
    context: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_utcnow)
    schema_version: str = Field(default=SCHEMA_VERSION)
