"""Tests for module M9's service adapters — ``StaticPredictor`` (REST) and
``FramePredictor`` (WebSocket).

Not testing that predictions are *accurate* — both adapters wrap already-
tested engines (``ForgeryEngine``/``ExplanationEngine`` for M6/M7,
``run_full_benchmark``'s export+quantize path for the ONNX model) with
untrained weights, same convention as ``test_engine_66.py``/
``test_optimization.py``. What these tests cover is the adapter contract:
bytes in, contract objects out; bad input produces an ``EngineError`` rather
than a raised exception; no-face frames are reported, not dropped; and both
classes can be constructed against a fresh clone (no checkpoint, no
pre-exported ONNX model — the latter is produced by the test itself, exactly
as a real deployment's setup step would).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
torch = pytest.importorskip("torch")
pytest.importorskip("timm")
onnx = pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")

from falsora_ai.common.faces import Box  # noqa: E402
from falsora_ai.config import Config, ModelConfig, PathConfig, TamperingConfig  # noqa: E402
from falsora_ai.contracts import EngineError, Explanation, ForgeryResult, FrameScore  # noqa: E402
from falsora_ai.engine_66.deepfake.model import DeepfakeNet  # noqa: E402
from falsora_ai.engine_66.engine import ForgeryEngine  # noqa: E402
from falsora_ai.engine_66.tampering.model import TamperingCNN  # noqa: E402
from falsora_ai.engine_67.explain import ExplanationEngine  # noqa: E402
from falsora_ai.optimization.export_onnx import export_deepfake_to_onnx  # noqa: E402
from falsora_ai.optimization.quantize import quantize_deepfake_onnx  # noqa: E402
from falsora_ai.service.predict_frame import FramePredictor  # noqa: E402
from falsora_ai.service.predict_static import StaticPredictor, decode_image  # noqa: E402


def _tiny_cfg(tmp_path: Path) -> Config:
    return Config(
        paths=PathConfig(
            root=tmp_path,
            checkpoints=tmp_path / "checkpoints",
            models=tmp_path / "models",
            gradcam=tmp_path / "gradcam",
        ),
        model=ModelConfig(architecture="efficientnet_b0", pretrained=False),
        tampering=TamperingConfig(input_size=32),
    )


def _rgb_image(size: int = 300, value: int = 128) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


def _jpeg_bytes(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


class _StubDetector:
    """Returns a fixed box (or None) regardless of input — same stub used by
    ``test_engine_66.py``, no MTCNN weights required."""

    def __init__(self, box: Box | None) -> None:
        self._box = box

    def detect_batch(self, frames: list[np.ndarray]) -> list[Box | None]:
        return [self._box for _ in frames]


class TestDecodeImage:
    def test_round_trips_a_real_jpeg(self) -> None:
        image = _rgb_image()
        decoded = decode_image(_jpeg_bytes(image))
        assert decoded.shape == image.shape
        assert decoded.dtype == np.uint8

    def test_raises_on_garbage_bytes(self) -> None:
        with pytest.raises(ValueError):
            decode_image(b"not an image")


class TestStaticPredictor:
    def _predictor(self, tmp_path: Path, detector: _StubDetector) -> StaticPredictor:
        cfg = _tiny_cfg(tmp_path)
        forgery_engine = ForgeryEngine(
            cfg=cfg,
            device="cpu",
            deepfake_model=DeepfakeNet(cfg.model),
            tampering_model=TamperingCNN(cfg.tampering),
            face_detector=detector,
        )
        explanation_engine = ExplanationEngine(
            cfg=cfg, device="cpu", model=forgery_engine.deepfake_model
        )
        return StaticPredictor(
            cfg=cfg,
            device="cpu",
            forgery_engine=forgery_engine,
            explanation_engine=explanation_engine,
        )

    def test_predict_returns_a_valid_result_and_explanation(self, tmp_path: Path) -> None:
        box = Box(x1=10, y1=10, x2=200, y2=200, confidence=0.99)
        predictor = self._predictor(tmp_path, _StubDetector(box))

        result, explanation = predictor.predict(_jpeg_bytes(_rgb_image()), case_id="case-1")

        assert isinstance(result, ForgeryResult)
        assert result.case_id == "case-1"
        assert result.face_detected is True
        assert isinstance(explanation, Explanation)
        assert explanation.result_id == result.result_id

    def test_predict_without_explain_skips_gradcam(self, tmp_path: Path) -> None:
        box = Box(x1=10, y1=10, x2=200, y2=200, confidence=0.99)
        predictor = self._predictor(tmp_path, _StubDetector(box))

        result, explanation = predictor.predict(_jpeg_bytes(_rgb_image()), explain=False)

        assert isinstance(result, ForgeryResult)
        assert explanation is None

    def test_no_face_detected_still_returns_a_result_with_no_explanation(
        self, tmp_path: Path
    ) -> None:
        predictor = self._predictor(tmp_path, _StubDetector(None))

        result, explanation = predictor.predict(_jpeg_bytes(_rgb_image()))

        assert isinstance(result, ForgeryResult)
        assert result.face_detected is False
        assert result.deepfake is None
        assert result.tampering is not None
        assert explanation is None

    def test_bad_bytes_return_an_engine_error_not_a_raise(self, tmp_path: Path) -> None:
        predictor = self._predictor(tmp_path, _StubDetector(None))

        result, explanation = predictor.predict(b"not an image")

        assert isinstance(result, EngineError)
        assert result.code == "decode_failed"
        assert explanation is None


class TestFramePredictor:
    @pytest.fixture()
    def int8_session_cfg(self, tmp_path: Path):
        cfg = _tiny_cfg(tmp_path)
        fp32 = export_deepfake_to_onnx(cfg=cfg, device="cpu")
        quantize_deepfake_onnx(fp32)
        return cfg

    def test_predict_returns_a_valid_frame_score(self, int8_session_cfg: Config) -> None:
        box = Box(x1=10, y1=10, x2=200, y2=200, confidence=0.99)
        predictor = FramePredictor(cfg=int8_session_cfg, face_detector=_StubDetector(box))

        score = predictor.predict(_jpeg_bytes(_rgb_image()), session_id="sess-1", frame_index=0)

        assert isinstance(score, FrameScore)
        assert score.session_id == "sess-1"
        assert score.frame_index == 0
        assert score.face_detected is True
        assert 0.0 <= score.probability_fake <= 1.0
        assert score.latency_ms >= 0.0

    def test_no_face_reports_uncertain_not_an_error(self, int8_session_cfg: Config) -> None:
        predictor = FramePredictor(cfg=int8_session_cfg, face_detector=_StubDetector(None))

        score = predictor.predict(_jpeg_bytes(_rgb_image()), session_id="sess-1", frame_index=0)

        assert isinstance(score, FrameScore)
        assert score.face_detected is False
        assert score.probability_fake == pytest.approx(0.5)

    def test_bad_bytes_return_an_engine_error_not_a_raise(self, int8_session_cfg: Config) -> None:
        predictor = FramePredictor(cfg=int8_session_cfg, face_detector=_StubDetector(None))

        result = predictor.predict(b"not an image", session_id="sess-1", frame_index=0)

        assert isinstance(result, EngineError)
        assert result.code == "decode_failed"

    def test_raises_when_no_int8_model_is_on_disk_and_no_session_injected(
        self, tmp_path: Path
    ) -> None:
        cfg = _tiny_cfg(tmp_path)
        with pytest.raises(FileNotFoundError):
            FramePredictor(cfg=cfg, face_detector=_StubDetector(None))

    def test_quality_ok_is_forwarded_unchanged(self, int8_session_cfg: Config) -> None:
        box = Box(x1=10, y1=10, x2=200, y2=200, confidence=0.99)
        predictor = FramePredictor(cfg=int8_session_cfg, face_detector=_StubDetector(box))

        score = predictor.predict(
            _jpeg_bytes(_rgb_image()), session_id="sess-1", frame_index=0, quality_ok=False
        )

        assert isinstance(score, FrameScore)
        assert score.quality_ok is False
