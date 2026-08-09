"""
Noise residual analysis.
=========================

Camera sensor noise is a fingerprint: every pixel in a genuine photograph
carries noise from one sensor, one ISO, one JPEG chain. Splicing pastes in
content whose noise came from a different source, so a high-pass filter that
strips the image content and keeps only its noise floor makes that boundary
visible even where it is invisible in the raw pixels — the complementary
signal to :mod:`ela.py`'s compression-history map.

This is a fixed SRM-style residual, not a learned denoiser: sufficient at
CASIA v2.0 scale (~12.6k images) and cheap enough to run per frame later if
the live path ever needs it, per ENGINEERING_PLAN.md 3.3.
"""

from __future__ import annotations

import cv2
import numpy as np

__all__ = ["compute_residual_map", "residual_score"]

# Classic SRM high-pass kernel (Fridrich & Kodovsky, "Rich Models for
# Steganalysis of Digital Images"), normalised so the flat-field response is
# exactly zero — a genuinely uniform patch produces a residual of zero, not a
# small nonzero bias that would shift the score for every image alike.
_SRM_KERNEL = (
    np.array(
        [
            [-1, 2, -2, 2, -1],
            [2, -6, 8, -6, 2],
            [-2, 8, -12, 8, -2],
            [2, -6, 8, -6, 2],
            [-1, 2, -2, 2, -1],
        ],
        dtype=np.float32,
    )
    / 12.0
)


def compute_residual_map(image: np.ndarray) -> np.ndarray:
    """Return a single-channel noise-residual map, same height/width as ``image``.

    Args:
        image: RGB, ``uint8``, ``HxWx3``.

    Returns:
        ``uint8`` array, ``HxW``. Higher values mean stronger high-frequency
        residual at that pixel.

    Raises:
        ValueError: If ``image`` is not ``HxWx3``.
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected HxWx3 RGB, got shape {image.shape}")

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32)
    filtered = cv2.filter2D(gray, ddepth=cv2.CV_32F, kernel=_SRM_KERNEL)
    magnitude = np.clip(np.abs(filtered), 0, 255)
    return magnitude.astype(np.uint8)


def residual_score(image: np.ndarray) -> float:
    """Scalar summary for ``TamperingSignal.residual_score`` — mean residual magnitude."""
    return float(compute_residual_map(image).mean())
