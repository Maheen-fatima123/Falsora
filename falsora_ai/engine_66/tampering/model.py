"""
Tampering classifier — CASIA v2.0-trained (module 6.6b).
==========================================================

Input is 5 channels, not 3: the RGB image plus its ELA map (``ela.py``) and
its noise residual (``residual.py``), stacked. Splicing and copy-move
artefacts are often invisible in RGB alone and show up in one auxiliary map
or the other, so the network is given both rather than asked to rediscover
them from raw pixels on a dataset of only ~12.6k images.

Deliberately small relative to the deepfake branch's EfficientNet. CASIA v2.0
is two orders of magnitude smaller than the FF++/DFD training pool (~12.6k
images vs 80k+ crops), and a backbone sized for that pool would overfit this
one long before convergence. A shallow CNN with aggressive pooling is the
defensible choice at this data scale, per ENGINEERING_PLAN.md 3.3. No
pretrained weights exist for a 5-channel input either, so this trains from
scratch rather than by fine-tuning.

Training (M4's dataset/train loop) and the fused engine (M5) are not built
yet — this is the model definition and the channel-stacking contract only,
which is what M4 depends on M2's Dataset for.

Torch is imported at module level here, unlike ``falsora_ai.engine_616``:
this module is only ever imported by code that already intends to run the
tampering model, so it does not sit on Ujala's torch-free import path (see
``falsora_ai/__init__.py`` and ``tests/test_dependencies.py``).
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from falsora_ai.config import TamperingConfig
from falsora_ai.engine_66.tampering.ela import compute_ela_map
from falsora_ai.engine_66.tampering.residual import compute_residual_map

__all__ = ["IN_CHANNELS", "TamperingCNN", "build_model_input"]

IN_CHANNELS = 5  # RGB + ELA + residual


def build_model_input(image: np.ndarray, cfg: TamperingConfig | None = None) -> np.ndarray:
    """Stack RGB + ELA + residual into one ``HxWx5`` ``float32`` array in ``[0, 1]``.

    The single place this concatenation happens, so training and inference
    cannot drift apart on channel order or scale — the same discipline
    ``expand_box`` applies to the face-crop margin in
    ``falsora_ai.common.faces``.

    Args:
        image: RGB, ``uint8``, ``HxWx3``.
        cfg: forwarded to :func:`~falsora_ai.engine_66.tampering.ela.compute_ela_map`.

    Returns:
        ``float32`` array, ``HxWx5``, values in ``[0, 1]``.
    """
    cfg = cfg or TamperingConfig()
    ela = compute_ela_map(image, cfg)
    residual = compute_residual_map(image)
    stacked = np.dstack([image, ela, residual]).astype(np.float32) / 255.0
    return stacked


class _ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class TamperingCNN(nn.Module):
    """5-channel CNN, single logit output, sigmoid → P(tampered).

    Sized for CASIA v2.0 (~12.6k images): four conv blocks down to a small
    spatial map, global average pool, one linear head — roughly 400k
    parameters, small enough that overfitting is controlled by the dropout
    and the dataset's own augmentation (M2) rather than by the architecture
    alone.
    """

    def __init__(self, cfg: TamperingConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or TamperingConfig()
        self.features = nn.Sequential(
            _ConvBlock(IN_CHANNELS, 32),
            _ConvBlock(32, 64),
            _ConvBlock(64, 128),
            _ConvBlock(128, 256),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.dropout = nn.Dropout(0.3)
        self.head = nn.Linear(256, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """``x``: ``NxCxHxW``, ``C == IN_CHANNELS``. Returns raw logits, ``(N, 1)``.

        Raw logits, not sigmoid — pairs with ``BCEWithLogitsLoss`` at training
        time (same convention as the deepfake branch) and the caller applies
        sigmoid once, at inference, into ``TamperingSignal.probability_tampered``.
        """
        feats = self.features(x)
        pooled = self.pool(feats).flatten(1)
        return self.head(self.dropout(pooled))
