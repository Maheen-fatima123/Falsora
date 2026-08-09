"""
Error Level Analysis (ELA).
============================

Resaves the image at a fixed JPEG quality and measures how much each region
changes. A region that has already been through this quantisation table once
has settled into a local error minimum and barely moves on a second save; a
spliced or retouched region was introduced *after* the original save — often
from a different source, at a different quality — and has not settled, so it
moves more. The map does not say *what* was edited, only *where* the
compression history looks discontinuous, which is exactly the complementary
signal to the noise residual in :mod:`residual.py` — one is sensitive to
recompression history, the other to sensor-noise inconsistency, and a forgery
that hides from one often shows up in the other.

Operates on the whole image, not a face crop: splicing artefacts are global,
per ENGINEERING_PLAN.md 3.3.
"""

from __future__ import annotations

import cv2
import numpy as np

from falsora_ai.config import TamperingConfig

__all__ = ["compute_ela_map", "ela_score"]


def compute_ela_map(image: np.ndarray, cfg: TamperingConfig | None = None) -> np.ndarray:
    """Return a single-channel ELA map, same height/width as ``image``.

    Args:
        image: RGB, ``uint8``, ``HxWx3``.
        cfg: supplies ``ela_quality`` (the resave JPEG quality) and
            ``ela_gain`` (amplification so a few-value difference is visible
            in ``[0, 255]``). Both must match between training and inference —
            the reason they live in config rather than as literals here.

    Returns:
        ``uint8`` array, ``HxW``. Higher values mean more compression-history
        discontinuity at that pixel.

    Raises:
        ValueError: If ``image`` is not ``HxWx3``.
    """
    cfg = cfg or TamperingConfig()
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected HxWx3 RGB, got shape {image.shape}")

    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, cfg.ela_quality])
    if not ok:
        raise ValueError("JPEG re-encode failed")
    resaved = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    diff = cv2.absdiff(bgr, resaved).astype(np.float32)
    gray_diff = diff.mean(axis=2)
    amplified = np.clip(gray_diff * cfg.ela_gain, 0, 255)
    return amplified.astype(np.uint8)


def ela_score(image: np.ndarray, cfg: TamperingConfig | None = None) -> float:
    """Scalar summary for ``TamperingSignal.ela_score`` — mean map intensity."""
    return float(compute_ela_map(image, cfg).mean())
