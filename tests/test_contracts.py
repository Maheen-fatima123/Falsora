"""Tests for the integration contracts.

These matter more than typical unit tests: contracts.py is the interface three
people code against. A silent change here breaks Ujala's API layer and
Mehreen's decision engine at integration time, which is the worst moment to
find out. Every invariant the other modules rely on is asserted here.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from falsora_ai.contracts import (
    SCHEMA_VERSION,
    AnalysisMode,
    BoundingBox,
    DeepfakeSignal,
    EngineError,
    Explanation,
    FaceDetection,
    ForgeryResult,
    FrameScore,
    Label,
    LiveRiskState,
    RollingScoreState,
    TamperingSignal,
)

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def box() -> BoundingBox:
    return BoundingBox(x1=10, y1=20, x2=110, y2=140)


@pytest.fixture
def face(box: BoundingBox) -> FaceDetection:
    return FaceDetection(box=box, confidence=0.99, margin=0.3, detector="mtcnn")


@pytest.fixture
def deepfake() -> DeepfakeSignal:
    return DeepfakeSignal(
        probability_fake=0.82,
        model_name="efficientnet_b0",
        model_version="run-001",
        input_size=224,
    )


# --------------------------------------------------------------------------
# BoundingBox
# --------------------------------------------------------------------------


class TestBoundingBox:
    def test_dimensions(self, box: BoundingBox) -> None:
        assert box.width == 100
        assert box.height == 120
        assert box.area == 12000

    @pytest.mark.parametrize(
        "coords",
        [
            (10, 20, 10, 140),  # zero width
            (10, 20, 110, 20),  # zero height
            (110, 20, 10, 140),  # inverted x
            (10, 140, 110, 20),  # inverted y
        ],
    )
    def test_degenerate_boxes_rejected(self, coords: tuple[float, ...]) -> None:
        x1, y1, x2, y2 = coords
        with pytest.raises(ValidationError):
            BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)

    def test_unknown_field_rejected(self) -> None:
        """extra='forbid' is what makes contract drift fail loudly."""
        with pytest.raises(ValidationError):
            BoundingBox(x1=0, y1=0, x2=1, y2=1, confidence=0.9)


class TestComputedFieldRoundTrip:
    """Regression guard for a bug found during Module 0.

    Computed fields (``width``, ``height``, ``authenticity``) are emitted by
    ``model_dump_json`` but are not constructor arguments, so with
    ``extra='forbid'`` a naive round-trip raised ValidationError. Every payload
    here crosses the network as JSON in production, so every one must survive.
    """

    @pytest.mark.parametrize(
        "model",
        [
            BoundingBox(x1=1, y1=2, x2=3, y2=4),
            FaceDetection(
                box=BoundingBox(x1=1, y1=2, x2=3, y2=4), confidence=0.9
            ),
            DeepfakeSignal(
                probability_fake=0.5,
                model_name="efficientnet_b0",
                model_version="v1",
                input_size=224,
            ),
            FrameScore(session_id="s", frame_index=1, probability_fake=0.4),
            RollingScoreState(
                session_id="s",
                rolling_authenticity=0.8,
                frames_in_buffer=5,
                buffer_capacity=5,
                frames_processed_total=5,
                risk_state=LiveRiskState.OK,
            ),
        ],
        ids=["BoundingBox", "FaceDetection", "DeepfakeSignal", "FrameScore", "RollingScoreState"],
    )
    def test_round_trip(self, model) -> None:  # noqa: ANN001
        restored = type(model).model_validate(json.loads(model.model_dump_json()))
        assert restored.model_dump_json() == model.model_dump_json()

    def test_computed_fields_still_appear_in_json(self) -> None:
        """Stripping them on input must not remove them from output."""
        payload = json.loads(
            FrameScore(session_id="s", frame_index=0, probability_fake=0.9).model_dump_json()
        )
        assert payload["authenticity"] == pytest.approx(0.1)

    def test_genuinely_unknown_fields_still_rejected(self) -> None:
        """The fix must not have degraded into extra='ignore'."""
        with pytest.raises(ValidationError):
            FrameScore(
                session_id="s",
                frame_index=0,
                probability_fake=0.5,
                totally_made_up_field=1,
            )


# --------------------------------------------------------------------------
# Probability / authenticity duality
# --------------------------------------------------------------------------


class TestProbabilityConvention:
    """The single most dangerous bug in this system would be inverting these.

    The scope document thresholds on *authenticity* (<0.35 is HIGH-RISK) while
    the model outputs P(fake). These tests pin the relationship down.
    """

    def test_deepfake_signal_authenticity_is_complement(
        self, deepfake: DeepfakeSignal
    ) -> None:
        assert deepfake.authenticity == pytest.approx(1.0 - 0.82)

    def test_frame_score_authenticity_is_complement(self) -> None:
        frame = FrameScore(session_id="s1", frame_index=0, probability_fake=0.9)
        assert frame.authenticity == pytest.approx(0.1)

    def test_a_confident_fake_is_low_authenticity(self) -> None:
        """P(fake)=0.9 must sit BELOW the 0.35 high-risk authenticity threshold."""
        frame = FrameScore(session_id="s1", frame_index=0, probability_fake=0.9)
        assert frame.authenticity < 0.35

    def test_a_confident_real_is_high_authenticity(self) -> None:
        frame = FrameScore(session_id="s1", frame_index=0, probability_fake=0.05)
        assert frame.authenticity > 0.35

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -5.0])
    def test_probabilities_are_bounded(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            FrameScore(session_id="s1", frame_index=0, probability_fake=bad)


# --------------------------------------------------------------------------
# ForgeryResult invariants
# --------------------------------------------------------------------------


class TestForgeryResult:
    def test_valid_deepfake_result(
        self, face: FaceDetection, deepfake: DeepfakeSignal
    ) -> None:
        result = ForgeryResult(
            face_detected=True, face=face, deepfake=deepfake, latency_ms=42.0
        )
        assert result.has_deepfake_signal
        assert not result.has_tampering_signal
        assert result.mode is AnalysisMode.STATIC
        assert result.schema_version == SCHEMA_VERSION

    def test_tampering_only_result_needs_no_face(self) -> None:
        """Splicing detection works on images with no face at all."""
        result = ForgeryResult(
            face_detected=False,
            tampering=TamperingSignal(probability_tampered=0.7),
            latency_ms=15.0,
        )
        assert result.has_tampering_signal
        assert not result.has_deepfake_signal

    def test_face_detected_without_face_object_rejected(
        self, deepfake: DeepfakeSignal
    ) -> None:
        with pytest.raises(ValidationError, match="no FaceDetection"):
            ForgeryResult(face_detected=True, deepfake=deepfake, latency_ms=1.0)

    def test_deepfake_signal_without_face_rejected(
        self, deepfake: DeepfakeSignal
    ) -> None:
        """The deepfake branch consumes face crops; a signal without a face is a bug."""
        with pytest.raises(ValidationError, match="without a detected face"):
            ForgeryResult(face_detected=False, deepfake=deepfake, latency_ms=1.0)

    def test_empty_result_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no signal at all"):
            ForgeryResult(face_detected=False, latency_ms=1.0)

    def test_no_risk_level_field(self, face: FaceDetection, deepfake: DeepfakeSignal) -> None:
        """Module 6.8 (Mehreen) owns risk banding. 6.6 must not duplicate it."""
        result = ForgeryResult(
            face_detected=True, face=face, deepfake=deepfake, latency_ms=1.0
        )
        assert not hasattr(result, "risk_level")
        assert "risk_level" not in result.model_dump()

    def test_json_round_trip(self, face: FaceDetection, deepfake: DeepfakeSignal) -> None:
        """Ujala serialises this over HTTP; it must survive the trip intact."""
        original = ForgeryResult(
            case_id="case-abc",
            face_detected=True,
            face=face,
            deepfake=deepfake,
            tampering=TamperingSignal(probability_tampered=0.2, ela_score=3.4),
            latency_ms=42.0,
            warnings=["low_resolution"],
        )
        restored = ForgeryResult.model_validate(json.loads(original.model_dump_json()))
        assert restored.case_id == original.case_id
        assert restored.deepfake is not None and original.deepfake is not None
        assert restored.deepfake.probability_fake == original.deepfake.probability_fake
        assert restored.warnings == ["low_resolution"]
        assert restored.result_id == original.result_id


# --------------------------------------------------------------------------
# Explanation / RollingScoreState / EngineError
# --------------------------------------------------------------------------


class TestExplanation:
    def test_links_to_result(self) -> None:
        rid = uuid4()
        exp = Explanation(
            result_id=rid,
            target_layer="features.8",
            overlay_path="/gradcam/abc_overlay.png",
        )
        assert exp.result_id == rid
        assert exp.method == "gradcam"


class TestRollingScoreState:
    def test_complement_and_buffer_flags(self) -> None:
        state = RollingScoreState(
            session_id="s1",
            rolling_authenticity=0.25,
            frames_in_buffer=5,
            buffer_capacity=5,
            frames_processed_total=17,
            risk_state=LiveRiskState.HIGH_RISK,
            alert_triggered=True,
        )
        assert state.rolling_probability_fake == pytest.approx(0.75)
        assert state.buffer_full
        assert state.risk_state is LiveRiskState.HIGH_RISK

    def test_partial_buffer_not_full(self) -> None:
        state = RollingScoreState(
            session_id="s1",
            rolling_authenticity=0.9,
            frames_in_buffer=2,
            buffer_capacity=5,
            frames_processed_total=2,
            risk_state=LiveRiskState.INSUFFICIENT_DATA,
        )
        assert not state.buffer_full
        assert not state.alert_triggered


class TestEngineError:
    def test_serialisable(self) -> None:
        err = EngineError(
            code="NO_FACE_DETECTED",
            message="No face found in the submitted image.",
            module="6.6",
            context={"image_size": [640, 480]},
        )
        payload = json.loads(err.model_dump_json())
        assert payload["code"] == "NO_FACE_DETECTED"
        assert payload["recoverable"] is True


# --------------------------------------------------------------------------
# Enum stability — other modules persist these strings to the database
# --------------------------------------------------------------------------


class TestEnumStability:
    def test_label_values(self) -> None:
        assert Label.REAL.value == "real"
        assert Label.FAKE.value == "fake"

    def test_live_risk_state_values(self) -> None:
        assert {s.value for s in LiveRiskState} == {
            "ok",
            "watch",
            "high_risk",
            "insufficient_data",
        }

    def test_analysis_mode_values(self) -> None:
        assert {m.value for m in AnalysisMode} == {"static", "live"}
