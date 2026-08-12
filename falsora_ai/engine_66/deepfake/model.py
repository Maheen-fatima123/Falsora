"""
Deepfake classifier — EfficientNet-trained (module 6.6a).
===========================================================

Branch A of module 6.6: AI face-forgery detection. Input is a single face
crop (RGB, the M1 extraction output), output is one logit, sigmoid ->
P(fake). This mirrors the tampering branch's convention (raw logits paired
with ``BCEWithLogitsLoss``) so both branches train and calibrate the same
way — see ``engine_66/tampering/model.py``.

Backbone comes from ``timm`` rather than ``torchvision`` because scope
section 5.1 commits to two variants sharing one architecture family
(EfficientNet-B0 for the live/quantized path, B3 or B4 for the static path)
and ``timm`` exposes all of them, plus ImageNet pretrained weights, through
one ``create_model`` call — no per-variant boilerplate to keep in sync.

Training (this module's ``train.py``) and evaluation are not built yet in
this file — this is the architecture definition only, which is what M2's
``FaceCropDataset``/``deepfake_transforms`` already assume as their
downstream consumer (``ModelConfig.resolved_input_size()`` is the same
config both sides read).

Torch is imported at module level, same rationale as
``engine_66/tampering/model.py``: this module is only ever imported by code
that already intends to run the deepfake model, so it never sits on Ujala's
torch-free import path (see ``falsora_ai/__init__.py`` and
``tests/test_dependencies.py``).
"""

from __future__ import annotations

import torch
from torch import nn

from falsora_ai.config import ModelConfig

__all__ = ["DeepfakeNet"]


class DeepfakeNet(nn.Module):
    """EfficientNet backbone (via ``timm``), single logit head.

    ``architecture`` and ``input_size`` are read from ``ModelConfig`` rather
    than hardcoded, so switching from B0 (live path) to B3/B4 (static path)
    is a config change, not a code change — the same discipline
    ``TamperingConfig`` applies to ELA quality/gain.
    """

    def __init__(self, cfg: ModelConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or ModelConfig()

        import timm  # local import: keeps timm off any path that only needs the dataclass

        self.backbone = timm.create_model(
            self.cfg.architecture,
            pretrained=self.cfg.pretrained,
            num_classes=0,  # strip the built-in classifier; we attach our own head
            drop_rate=self.cfg.dropout,
        )
        feature_dim = self.backbone.num_features
        self.dropout = nn.Dropout(self.cfg.dropout)
        self.head = nn.Linear(feature_dim, self.cfg.num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """``x``: ``NxCxHxW``. Returns raw logits, ``(N, num_classes)``.

        Raw logits, not sigmoid — pairs with ``BCEWithLogitsLoss`` at
        training time; the caller applies sigmoid once, at inference, into
        ``DeepfakeSignal.probability_fake``.
        """
        feats = self.backbone(x)
        return self.head(self.dropout(feats))
