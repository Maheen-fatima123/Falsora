"""
Tampering branch evaluation (module 6.6b).
==============================================

One aggregation level, not two. The deepfake branch (``engine_66/deepfake/
evaluate.py``) pools frame predictions into a video verdict because the app
reports one verdict per uploaded video, not per frame. CASIA v2.0 has no such
grouping — every image is its own unit of evidence — so a single image-level
AUC/accuracy is the whole story here, no separate "video-level" pass to run.

There is also no cross-dataset benchmark analogous to Celeb-DF: CASIA v2.0 is
the only tampering-localisation dataset in scope (ENGINEERING_PLAN.md section
3.3), so ``evaluate_split`` only ever runs against its own train/val/test
splits.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.utils.data import DataLoader

from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config
from falsora_ai.data.datasets import TamperingDataset, make_dataloader
from falsora_ai.data.transforms import SplitName

__all__ = [
    "EvalResult",
    "collect_predictions",
    "image_level_auc",
    "evaluate_split",
]

logger = get_logger(__name__)


@dataclass
class EvalResult:
    split: str
    n_images: int
    auc: float
    accuracy: float


@torch.no_grad()
def collect_predictions(
    model: nn.Module, loader: DataLoader, device: str
) -> tuple[np.ndarray, np.ndarray]:
    """Run inference over a full split. Returns parallel arrays: P(tampered)
    and ground-truth label, one entry per image."""
    model.eval()
    probs: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        logits = model(images)
        probs.append(torch.sigmoid(logits).squeeze(1).cpu().numpy())
        labels.append(batch["label"].squeeze(1).numpy())
    return np.concatenate(probs), np.concatenate(labels)


def image_level_auc(probs: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    auc = float(roc_auc_score(labels, probs)) if len(np.unique(labels)) > 1 else float("nan")
    accuracy = float(((probs >= 0.5).astype(np.float32) == labels).mean())
    return auc, accuracy


def evaluate_split(
    model: nn.Module,
    cfg: Config,
    split: SplitName,
    device: str,
    dataset: TamperingDataset | None = None,
) -> EvalResult:
    """Evaluate one manifest split end to end: build its ``Dataset``/
    ``DataLoader`` (eval-mode transforms — no augmentation, since
    ``TamperingDataset`` already selects those for any non-``"train"``
    split), run inference, aggregate.

    ``dataset`` is injectable so tests can evaluate over a handful of
    synthetic items instead of the real CASIA manifest.
    """
    dataset = dataset or TamperingDataset(cfg, split=split)
    loader = make_dataloader(dataset, cfg, split=split, shuffle=False)

    probs, labels = collect_predictions(model, loader, device)
    auc, accuracy = image_level_auc(probs, labels)

    result = EvalResult(split=split, n_images=len(probs), auc=auc, accuracy=accuracy)
    logger.info(
        "split=%s | images=%d | auc=%.4f accuracy=%.4f",
        split,
        result.n_images,
        auc,
        accuracy,
    )
    return result
