"""Tests for module 6.7's explanation engine (M6) — ``ExplanationEngine``.

Not testing that the heatmap is *correct* — that needs a real trained
checkpoint and a genuinely forged image to say anything meaningful, which
this untrained-weights CPU test setup cannot provide. What unit tests cover
is the contract: a detected-face result produces a valid ``Explanation``
with real files on disk, a no-face/no-deepfake result produces ``None`` (not
an error), and the module falls back to untrained weights without crashing
when no checkpoint is present — the same three guarantees ``test_engine_66.py``
makes for ``ForgeryEngine``, since ``ExplanationEngine`` is built the same way.

``DeepfakeNet`` is constructed with ``pretrained=False`` (no ImageNet
download) and no checkpoint override, so the engine falls back to untrained
weights — the "no checkpoint on disk" path every fresh clone hits before M3
is trained.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
torch = pytest.importorskip("torch")
pytest.importorskip("timm")
pytest.importorskip("pytorch_grad_cam")

from falsora_ai.config import Config, ModelConfig, PathConfig  # noqa: E402
from falsora_ai.contracts import (  # noqa: E402
    BoundingBox,
    DeepfakeSignal,
    FaceDetection,
    ForgeryResult,
    TamperingSignal,
)
from falsora_ai.engine_66.deepfake.model import DeepfakeNet  # noqa: E402
from falsora_ai.engine_67.explain import ExplanationEngine  # noqa: E402


def _tiny_cfg(tmp_path: Path) -> Config:
    """No pretrained download, everything routed to tmp_path so a test run
    never touches (or requires) the real project's checkpoints/ or gradcam/."""
    return Config(
        paths=PathConfig(
            root=tmp_path,
            checkpoints=tmp_path / "checkpoints",
            gradcam=tmp_path / "gradcam",
        ),
        model=ModelConfig(architecture="efficientnet_b0", pretrained=False),
    )


def _rgb_image(size: int = 300) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


def _result_with_face(face_detected: bool = True) -> ForgeryResult:
    tampering = TamperingSignal(probability_tampered=0.2, ela_score=1.0, residual_score=1.0)
    if not face_detected:
        return ForgeryResult(face_detected=False, face=None, deepfake=None, tampering=tampering, latency_ms=1.0)

    face = FaceDetection(
        box=BoundingBox(x1=10, y1=10, x2=200, y2=200), confidence=0.98, margin=0.3, detector="mtcnn"
    )
    deepfake = DeepfakeSignal(
        probability_fake=0.8, model_name="efficientnet_b0", model_version="unversioned", input_size=224, quantized=False
    )
    return ForgeryResult(
        face_detected=True, face=face, deepfake=deepfake, tampering=tampering, latency_ms=1.0
    )


def _engine(tmp_path: Path) -> ExplanationEngine:
    cfg = _tiny_cfg(tmp_path)
    return ExplanationEngine(cfg=cfg, device="cpu", model=DeepfakeNet(cfg.model))


class TestFaceDetected:
    def test_returns_a_valid_explanation(self, tmp_path: Path) -> None:
        image = _rgb_image()
        result = _result_with_face()
        engine = _engine(tmp_path)

        explanation = engine.explain(image, result)

        assert explanation is not None
        assert explanation.result_id == result.result_id
        assert explanation.method == "gradcam"
        assert explanation.target_layer == "backbone.conv_head"
        assert Path(explanation.overlay_path).exists()
        assert Path(explanation.heatmap_path).exists()

    def test_salient_regions_are_absolute_source_image_coordinates(self, tmp_path: Path) -> None:
        """Every returned box must land inside the face box it was derived
        from — a bug that forgot the ``box.x1``/``box.y1`` offset would
        instead produce coordinates relative to the crop (i.e. starting near
        (0, 0)), which for this face box (10, 10)-(200, 200) would be
        indistinguishable from correct only by coincidence."""
        image = _rgb_image()
        result = _result_with_face()
        engine = _engine(tmp_path)

        explanation = engine.explain(image, result)

        assert explanation is not None
        face_box = result.face.box
        for region in explanation.salient_regions:
            assert face_box.x1 <= region.x1 < region.x2 <= face_box.x2
            assert face_box.y1 <= region.y1 < region.y2 <= face_box.y2

    def test_gradcam_plusplus_is_also_supported(self, tmp_path: Path) -> None:
        image = _rgb_image()
        result = _result_with_face()
        engine = _engine(tmp_path)

        explanation = engine.explain(image, result, method="gradcam++")

        assert explanation is not None
        assert explanation.method == "gradcam++"


class TestNothingToExplain:
    def test_no_face_detected_returns_none_not_an_error(self, tmp_path: Path) -> None:
        image = _rgb_image()
        result = _result_with_face(face_detected=False)
        engine = _engine(tmp_path)

        assert engine.explain(image, result) is None


class TestMissingCheckpoint:
    def test_falls_back_to_untrained_weights_without_crashing(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        assert not (cfg.paths.checkpoints / "efficientnet_b0_best.pt").exists()

        engine = ExplanationEngine(cfg=cfg, device="cpu")
        explanation = engine.explain(_rgb_image(), _result_with_face())

        assert explanation is not None


class TestRealCheckpoint:
    """End-to-end sanity check against the project's real, trained M3
    checkpoint — skipped when it isn't present (e.g. a fresh clone or CI)."""

    @pytest.fixture()
    def real_engine(self) -> ExplanationEngine:
        cfg = Config()
        checkpoint = cfg.paths.checkpoints / f"{cfg.model.architecture}_best.pt"
        if not checkpoint.exists():
            pytest.skip("Real M3 checkpoint not present on this machine.")
        return ExplanationEngine(cfg=cfg, device="cpu")

    def test_explain_returns_a_valid_explanation(self, real_engine: ExplanationEngine) -> None:
        result = _result_with_face()
        explanation = real_engine.explain(_rgb_image(size=256), result)
        assert explanation is not None
        assert Path(explanation.overlay_path).exists()
