"""
Deepfake branch evaluation (module 6.6a).
============================================

Two aggregation levels, because they answer different questions:

* **Frame-level AUC** — how well the model separates individual face crops.
  This is what the training loop's ``val_auc`` (``train.py``) tracks per
  epoch, because it is cheap to compute every epoch.
* **Video-level AUC** — mean-pool a video's frame probabilities into one
  score, then evaluate against that video's single ground-truth label. This
  is the number that actually matters: the static path (scope section 5.1)
  reports one verdict per uploaded video, not one per frame, and frame-level
  AUC can look better than the model actually is if a handful of ambiguous
  frames don't change the pooled verdict.

**Cross-dataset evaluation** is the same function applied to
``split="heldout"`` — Celeb-DF, per ``DataConfig.DOMAIN_ROLES``, never seen
during training (ENGINEERING_PLAN.md section 3.4). Expect this number to be
noticeably lower than in-domain (``val``/``test``) AUC; that gap is the
honest generalisation result, not a bug to chase away.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import torch
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.utils.data import DataLoader

from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config
from falsora_ai.data.datasets import FaceCropDataset, make_dataloader
from falsora_ai.data.transforms import SplitName

__all__ = [
    "EvalResult",
    "collect_predictions",
    "frame_level_auc",
    "video_level_auc",
    "evaluate_split",
]

logger = get_logger(__name__)


@dataclass
class EvalResult:
    split: str
    n_frames: int
    n_videos: int
    frame_auc: float
    video_auc: float
    frame_accuracy: float
    video_accuracy: float


@torch.no_grad()
def collect_predictions(
    model: nn.Module, loader: DataLoader, device: str
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Run inference over a full split. Returns parallel arrays: P(fake) per
    frame, ground-truth label per frame, and the source video path each frame
    belongs to (for video-level pooling)."""
    model.eval()
    probs: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    videos: list[str] = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        logits = model(images)
        probs.append(torch.sigmoid(logits).squeeze(1).cpu().numpy())
        labels.append(batch["label"].squeeze(1).numpy())
        videos.extend(batch["video_relpath"])
    return np.concatenate(probs), np.concatenate(labels), videos


def frame_level_auc(probs: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    auc = float(roc_auc_score(labels, probs)) if len(np.unique(labels)) > 1 else float("nan")
    accuracy = float(((probs >= 0.5).astype(np.float32) == labels).mean())
    return auc, accuracy


def video_level_auc(
    probs: np.ndarray, labels: np.ndarray, videos: list[str]
) -> tuple[float, float, int]:
    """Mean-pool frame probabilities per video before scoring. Every frame of
    a given video shares that video's label by construction (M1's extraction
    labels the whole video, not individual frames), so the label lookup is a
    plain last-write-wins dict build."""
    per_video_probs: dict[str, list[float]] = defaultdict(list)
    per_video_label: dict[str, float] = {}
    for prob, label, video in zip(probs, labels, videos, strict=True):
        per_video_probs[video].append(float(prob))
        per_video_label[video] = float(label)

    video_ids = sorted(per_video_probs)
    video_probs = np.array([np.mean(per_video_probs[v]) for v in video_ids])
    video_labels = np.array([per_video_label[v] for v in video_ids])

    auc = (
        float(roc_auc_score(video_labels, video_probs))
        if len(np.unique(video_labels)) > 1
        else float("nan")
    )
    accuracy = float(((video_probs >= 0.5).astype(np.float32) == video_labels).mean())
    return auc, accuracy, len(video_ids)


def evaluate_split(
    model: nn.Module,
    cfg: Config,
    split: SplitName,
    device: str,
    dataset: FaceCropDataset | None = None,
) -> EvalResult:
    """Evaluate one manifest split end to end: build its ``Dataset``/
    ``DataLoader`` (eval-mode transforms — no augmentation, since
    ``FaceCropDataset`` already selects those for any non-``"train"``
    split), run inference, aggregate at both levels.

    ``dataset`` is injectable so tests can evaluate over a handful of
    synthetic items instead of the real manifest.
    """
    dataset = dataset or FaceCropDataset(cfg, split=split)
    loader = make_dataloader(dataset, cfg, split=split, shuffle=False)

    probs, labels, videos = collect_predictions(model, loader, device)
    frame_auc, frame_accuracy = frame_level_auc(probs, labels)
    video_auc, video_accuracy, n_videos = video_level_auc(probs, labels, videos)

    result = EvalResult(
        split=split,
        n_frames=len(probs),
        n_videos=n_videos,
        frame_auc=frame_auc,
        video_auc=video_auc,
        frame_accuracy=frame_accuracy,
        video_accuracy=video_accuracy,
    )
    logger.info(
        "split=%s | frames=%d videos=%d | frame_auc=%.4f video_auc=%.4f "
        "frame_acc=%.4f video_acc=%.4f",
        split,
        result.n_frames,
        result.n_videos,
        frame_auc,
        video_auc,
        frame_accuracy,
        video_accuracy,
    )
    return result
