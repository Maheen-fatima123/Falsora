"""Tests for the ELA, noise-residual, and model-input pieces of module 6.6b.

Not testing that the model *detects tampering* — that needs a trained
checkpoint and is out of scope until M4's Dataset/train loop exists. What is
tested here is the contract each function promises its caller: correct output
shape/dtype/range, the near-zero response of both signals on genuinely flat
input (the property each map's design leans on), and that ``TamperingCNN``'s
forward pass produces the shape the training loop and the fused engine (M5)
will assume.
"""

from __future__ import annotations

import numpy as np
import pytest

from falsora_ai.config import TamperingConfig
from falsora_ai.engine_66.tampering.ela import compute_ela_map, ela_score
from falsora_ai.engine_66.tampering.model import (
    IN_CHANNELS,
    TamperingCNN,
    build_model_input,
)
from falsora_ai.engine_66.tampering.residual import compute_residual_map, residual_score

torch = pytest.importorskip("torch")


def flat_image(size: int = 32, value: int = 128) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def noisy_image(size: int = 32, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


class TestELA:
    def test_output_shape_and_dtype(self) -> None:
        image = noisy_image()
        out = compute_ela_map(image)
        assert out.shape == image.shape[:2]
        assert out.dtype == np.uint8

    def test_rejects_non_hwc3(self) -> None:
        with pytest.raises(ValueError):
            compute_ela_map(np.zeros((32, 32), dtype=np.uint8))

    def test_flat_image_has_low_ela(self) -> None:
        """A uniform patch has nothing for JPEG resave to disturb — the
        resaved copy should barely differ from the original."""
        score = ela_score(flat_image())
        assert score < 5.0

    def test_gain_amplifies_the_score(self) -> None:
        image = noisy_image()
        low_gain = ela_score(image, TamperingConfig(ela_gain=1.0))
        high_gain = ela_score(image, TamperingConfig(ela_gain=30.0))
        assert high_gain >= low_gain


class TestResidual:
    def test_output_shape_and_dtype(self) -> None:
        image = noisy_image()
        out = compute_residual_map(image)
        assert out.shape == image.shape[:2]
        assert out.dtype == np.uint8

    def test_rejects_non_hwc3(self) -> None:
        with pytest.raises(ValueError):
            compute_residual_map(np.zeros((32, 32, 4), dtype=np.uint8))

    def test_flat_image_has_zero_residual(self) -> None:
        """The SRM kernel is normalised to a zero flat-field response — a
        uniform patch must produce an exact-zero map, not a small bias."""
        out = compute_residual_map(flat_image())
        assert np.all(out == 0)
        assert residual_score(flat_image()) == 0.0

    def test_noisy_image_has_higher_residual_than_flat(self) -> None:
        assert residual_score(noisy_image()) > residual_score(flat_image())


class TestBuildModelInput:
    def test_shape_dtype_and_range(self) -> None:
        image = noisy_image()
        stacked = build_model_input(image)
        assert stacked.shape == (32, 32, IN_CHANNELS)
        assert stacked.dtype == np.float32
        assert stacked.min() >= 0.0
        assert stacked.max() <= 1.0

    def test_first_three_channels_are_the_rgb_image(self) -> None:
        image = noisy_image()
        stacked = build_model_input(image)
        np.testing.assert_allclose(stacked[..., :3], image.astype(np.float32) / 255.0)


class TestTamperingCNN:
    def test_forward_pass_output_shape(self) -> None:
        model = TamperingCNN()
        model.eval()
        batch = torch.zeros(2, IN_CHANNELS, 64, 64)
        with torch.no_grad():
            out = model(batch)
        assert out.shape == (2, 1)

    def test_output_is_raw_logits_not_bounded(self) -> None:
        """Head has no final activation — pairs with BCEWithLogitsLoss, so
        the output must not already be squashed into [0, 1]."""
        model = TamperingCNN()
        model.eval()
        batch = torch.full((1, IN_CHANNELS, 64, 64), 100.0)
        with torch.no_grad():
            out = model(batch)
        assert torch.isfinite(out).all()

    def test_end_to_end_from_a_real_image(self) -> None:
        """The exact pipeline the training loop and M5 will use: raw image
        -> build_model_input -> NCHW tensor -> model."""
        image = noisy_image(size=64)
        stacked = build_model_input(image)
        tensor = torch.from_numpy(stacked).permute(2, 0, 1).unsqueeze(0)
        model = TamperingCNN()
        model.eval()
        with torch.no_grad():
            out = model(tensor)
        assert out.shape == (1, 1)
