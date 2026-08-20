"""
Module 6.6a — Deepfake detection branch (EfficientNet, FF++/DFD-trained).
============================================================================

AI face-forgery detection: a single face crop in, one logit out, sigmoid ->
P(fake). Trained on the ``train_pool`` domains (``ffpp``, ``dfd``) per
``DataConfig.DOMAIN_ROLES``; evaluated in-domain on ``val``/``test`` and
cross-dataset on ``heldout`` (Celeb-DF), which is never trained on.

Fused with the tampering branch (``engine_66.tampering``) into a single
``DeepfakeSignal`` inside ``ForgeryResult`` by ``engine_66.engine`` (M5, not
yet built).

Imports torch (via ``model``) — this package is not on Ujala's torch-free
import path; see ``falsora_ai/__init__.py``.
"""

from __future__ import annotations

from falsora_ai.engine_66.deepfake.evaluate import (
    EvalResult,
    collect_predictions,
    evaluate_split,
    frame_level_auc,
    video_level_auc,
)
from falsora_ai.engine_66.deepfake.model import DeepfakeNet
from falsora_ai.engine_66.deepfake.train import TrainState, fit

__all__ = [
    "DeepfakeNet",
    "TrainState",
    "fit",
    "EvalResult",
    "collect_predictions",
    "evaluate_split",
    "frame_level_auc",
    "video_level_auc",
]
