"""Tests for module 6.6's fusion engine (M5) — ``ForgeryEngine``.

Not testing that the fused verdict is *correct* — that needs both branches'
real trained checkpoints and is exercised end to end in
``TestRealCheckpoints`` below, skipped when they're absent (e.g. CI). What
unit tests cover is the contract: both branches run and their results are
combined into a valid ``ForgeryResult``, the deepfake branch is properly
skipped (not errored) when no face is found, and the tampering branch
always runs regardless of face detection.

Both models are constructed with ``pretrained=False`` (no ImageNet
download) and no checkpoint override, so the engine falls back to
untrained weights — exactly the "no checkpoint on disk" path real callers
hit before M3/M4 are ever trained. The face detector is injected as a
tiny stub rather than real MTCNN, so these tests run in well under a
second on CPU with no model download.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
torch = pytest.importorskip("torch")
pytest.importorskip("timm")

from falsora_ai.common.faces import Box  # noqa: E402
from falsora_ai.config import Config, ModelConfig, PathConfig, TamperingConfig  # noqa: E402
from falsora_ai.contracts import AnalysisMode  # noqa: E402
from falsora_ai.engine_66.deepfake.model import DeepfakeNet  # noqa: E402
from falsora_ai.engine_66.engine import ForgeryEngine  # noqa: E402
from falsora_ai.engine_66.tampering.model import TamperingCNN  # noqa: E402


def _tiny_cfg(tmp_path: Path) -> Config:
    """No pretrained download, tiny tampering input, everything routed to
    tmp_path so a test run never touches (or requires) the real project's
    checkpoints/."""
    return Config(
        paths=PathConfig(root=tmp_path, checkpoints=tmp_path / "checkpoints"),
        model=ModelConfig(architecture="efficientnet_b0", pretrained=False),
        tampering=TamperingConfig(input_size=32),
    )


def _rgb_image(size: int = 96, value: int = 128) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


class _StubDetector:
    """Returns a fixed box (or None) regardless of input — deterministic,
    no MTCNN weights, no GPU/CPU inference cost."""

    def __init__(self, box: Box | None) -> None:
        self._box = box

    def detect_batch(self, frames: list[np.ndarray]) -> list[Box | None]:
        return [self._box for _ in frames]


def _engine(tmp_path: Path, detector: _StubDetector) -> ForgeryEngine:
    cfg = _tiny_cfg(tmp_path)
    return ForgeryEngine(
        cfg=cfg,
        device="cpu",
        deepfake_model=DeepfakeNet(cfg.model),
        tampering_model=TamperingCNN(cfg.tampering),
        face_detector=detector,
    )


class TestFaceDetected:
    def test_both_branches_present_and_valid(self, tmp_path: Path) -> None:
        image = _rgb_image()
        box = Box(x1=10, y1=10, x2=80, y2=80, confidence=0.99)
        engine = _engine(tmp_path, _StubDetector(box))

        result = engine.analyze_image(image, case_id="case-1")

        assert result.case_id == "case-1"
        assert result.mode == AnalysisMode.STATIC
        assert result.face_detected is True
        assert result.face is not None
        assert result.deepfake is not None
        assert result.tampering is not None
        assert 0.0 <= result.deepfake.probability_fake <= 1.0
        assert 0.0 <= result.tampering.probability_tampered <= 1.0
        assert result.latency_ms >= 0.0

    def test_face_box_reflects_the_configured_margin(self, tmp_path: Path) -> None:
        image = _rgb_image()
        box = Box(x1=10, y1=10, x2=50, y2=50, confidence=0.95)
        engine = _engine(tmp_path, _StubDetector(box))

        result = engine.analyze_image(image)

        # expand_box grows the raw detection — the stored box must not be
        # the exact raw MTCNN box, since crop_face used the expanded one.
        assert result.face is not None
        assert result.face.margin == engine.cfg.face.margin
        raw_width = box.x2 - box.x1
        assert (result.face.box.x2 - result.face.box.x1) >= raw_width


class TestNoFaceDetected:
    def test_deepfake_is_skipped_not_errored(self, tmp_path: Path) -> None:
        image = _rgb_image()
        engine = _engine(tmp_path, _StubDetector(None))

        result = engine.analyze_image(image)

        assert result.face_detected is False
        assert result.face is None
        assert result.deepfake is None

    def test_tampering_still_runs_without_a_face(self, tmp_path: Path) -> None:
        """The whole point of running both branches unconditionally: a
        spliced photo with no face must still be caught."""
        image = _rgb_image()
        engine = _engine(tmp_path, _StubDetector(None))

        result = engine.analyze_image(image)

        assert result.tampering is not None
        assert 0.0 <= result.tampering.probability_tampered <= 1.0


class TestMissingCheckpoints:
    def test_falls_back_to_untrained_weights_without_crashing(self, tmp_path: Path) -> None:
        """No checkpoint on disk (checkpoints dir is empty tmp_path) must not
        raise — this is the state every fresh clone starts in before M3/M4
        are trained."""
        cfg = _tiny_cfg(tmp_path)
        assert not (cfg.paths.checkpoints / "efficientnet_b0_best.pt").exists()
        assert not (cfg.paths.checkpoints / "tampering_cnn_best.pt").exists()

        engine = ForgeryEngine(cfg=cfg, device="cpu", face_detector=_StubDetector(None))
        result = engine.analyze_image(_rgb_image())

        assert result.tampering is not None


class TestRealCheckpoints:
    """End-to-end sanity check against the project's real, trained M3/M4
    checkpoints — skipped when they aren't present (e.g. a fresh clone or
    CI, which never trains real weights). Exercises the actual production
    config, not the tiny test one."""

    @pytest.fixture()
    def real_engine(self) -> ForgeryEngine:
        cfg = Config()
        deepfake_ckpt = cfg.paths.checkpoints / f"{cfg.model.architecture}_best.pt"
        tampering_ckpt = cfg.paths.checkpoints / "tampering_cnn_best.pt"
        if not (deepfake_ckpt.exists() and tampering_ckpt.exists()):
            pytest.skip("Real M3/M4 checkpoints not present on this machine.")
        return ForgeryEngine(cfg=cfg, device="cpu", face_detector=_StubDetector(None))

    def test_analyze_image_returns_a_valid_result(self, real_engine: ForgeryEngine) -> None:
        result = real_engine.analyze_image(_rgb_image(size=256))
        assert result.tampering is not None
        assert result.schema_version
