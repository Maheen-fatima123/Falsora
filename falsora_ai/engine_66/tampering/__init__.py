"""
Module 6.6b — Tampering detection branch (CASIA v2.0-trained).
================================================================

Whole-image classical tampering detection: Error Level Analysis + noise
residual, feeding a small CNN. Operates on the full frame, not a face crop —
splicing and copy-move artefacts are global, per ENGINEERING_PLAN.md 3.3.

Fused with the deepfake branch (``engine_66.deepfake``) into a single
``TamperingSignal`` inside ``ForgeryResult`` by ``engine_66.engine`` (M5, not
yet built). This package only defines the signal-producing pieces; the
Dataset/train loop that trains :class:`TamperingCNN` depends on M2 and is not
built yet either.

Imports torch (via ``model``) — this package is not on Ujala's torch-free
import path; see ``falsora_ai/__init__.py``.
"""

from __future__ import annotations

from falsora_ai.engine_66.tampering.ela import compute_ela_map, ela_score
from falsora_ai.engine_66.tampering.model import (
    IN_CHANNELS,
    TamperingCNN,
    build_model_input,
)
from falsora_ai.engine_66.tampering.residual import (
    compute_residual_map,
    residual_score,
)

__all__ = [
    "compute_ela_map",
    "ela_score",
    "compute_residual_map",
    "residual_score",
    "IN_CHANNELS",
    "TamperingCNN",
    "build_model_input",
]
