"""
Deepfake branch training loop (module 6.6a).
===============================================

Standard binary classification loop over :class:`DeepfakeNet`, built for the
constraint ENGINEERING_PLAN.md section 2.3 names explicitly: free-tier GPU
sessions (Colab/Kaggle) die at a time limit, not at a natural stopping point.
Every epoch is checkpointed, and :func:`fit` resumes from the latest
checkpoint by default — an interrupted 12-epoch run restarted the next day
picks up at the epoch it reached, not epoch 0.

Two checkpoints are kept, not one: ``<arch>_latest.pt`` (every epoch, for
resuming) and ``<arch>_best.pt`` (only on improvement, for evaluation/export).
They can diverge — the latest epoch is not always the best one — and M6/M7
(Grad-CAM, ONNX export) want the best checkpoint, not necessarily the last.

Label smoothing (``TrainConfig.label_smoothing``) is implemented by hand
because ``BCEWithLogitsLoss`` has no ``label_smoothing`` argument (unlike
``CrossEntropyLoss``): targets are pulled toward 0.5 by the smoothing
fraction before the loss is computed.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.utils.data import DataLoader

from falsora_ai.common.logging import get_logger
from falsora_ai.common.seed import seed_everything
from falsora_ai.config import Config, resolve_device
from falsora_ai.data.datasets import FaceCropDataset, make_dataloader
from falsora_ai.engine_66.deepfake.model import DeepfakeNet

__all__ = [
    "TrainState",
    "fit",
    "train_one_epoch",
    "evaluate_epoch",
    "save_checkpoint",
    "load_checkpoint",
]

logger = get_logger(__name__)


@dataclass
class TrainState:
    """Everything that must survive a checkpoint round-trip to resume exactly:
    which epoch to start at, whether the current run has already beaten its
    best metric, and the full per-epoch history for the eventual model card
    (M10)."""

    epoch: int = 0
    best_metric: float = -float("inf")
    epochs_without_improvement: int = 0
    history: list[dict[str, float]] = field(default_factory=list)


def _smooth_labels(labels: torch.Tensor, smoothing: float) -> torch.Tensor:
    if smoothing <= 0:
        return labels
    return labels * (1.0 - smoothing) + 0.5 * smoothing


def _build_scheduler(
    optimizer: torch.optim.Optimizer, cfg: Config, steps_per_epoch: int
) -> torch.optim.lr_scheduler.LambdaLR:
    """Linear warmup for ``warmup_epochs``, then cosine decay to 0 over the
    remaining epochs. Step-based (not epoch-based) so warmup is smooth even
    when ``steps_per_epoch`` is small."""
    warmup_steps = max(1, cfg.train.warmup_epochs * steps_per_epoch)
    total_steps = max(warmup_steps + 1, cfg.train.epochs * steps_per_epoch)

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / warmup_steps
        progress = (step - warmup_steps) / (total_steps - warmup_steps)
        return 0.5 * (1.0 + math.cos(math.pi * min(progress, 1.0)))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


def save_checkpoint(
    path: str | Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LambdaLR,
    scaler: torch.cuda.amp.GradScaler | None,
    state: TrainState,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "scaler_state_dict": scaler.state_dict() if scaler is not None else None,
            "epoch": state.epoch,
            "best_metric": state.best_metric,
            "epochs_without_improvement": state.epochs_without_improvement,
            "history": state.history,
        },
        path,
    )


def load_checkpoint(
    path: str | Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: torch.optim.lr_scheduler.LambdaLR | None = None,
    scaler: torch.cuda.amp.GradScaler | None = None,
    device: str = "cpu",
) -> TrainState:
    """Restore model (+ optionally optimizer/scheduler/scaler) state and
    return the :class:`TrainState` to resume from. Callers that only want
    inference weights (M6/M7) pass ``optimizer=None``."""
    checkpoint: dict[str, Any] = torch.load(path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    if optimizer is not None and checkpoint.get("optimizer_state_dict") is not None:
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    if scheduler is not None and checkpoint.get("scheduler_state_dict") is not None:
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
    if scaler is not None and checkpoint.get("scaler_state_dict") is not None:
        scaler.load_state_dict(checkpoint["scaler_state_dict"])
    return TrainState(
        epoch=checkpoint["epoch"],
        best_metric=checkpoint["best_metric"],
        epochs_without_improvement=checkpoint["epochs_without_improvement"],
        history=checkpoint.get("history", []),
    )


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LambdaLR,
    device: str,
    scaler: torch.cuda.amp.GradScaler | None,
    cfg: Config,
) -> float:
    model.train()
    total_loss = 0.0
    n = 0
    amp_enabled = scaler is not None and scaler.is_enabled()
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        labels = _smooth_labels(
            batch["label"].to(device, non_blocking=True), cfg.train.label_smoothing
        )

        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", enabled=amp_enabled):
            logits = model(images)
            loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)

        if amp_enabled:
            assert scaler is not None
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), cfg.train.grad_clip)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), cfg.train.grad_clip)
            optimizer.step()
        scheduler.step()

        batch_size = images.size(0)
        total_loss += loss.item() * batch_size
        n += batch_size

    return total_loss / n


@torch.no_grad()
def evaluate_epoch(model: nn.Module, loader: DataLoader, device: str) -> dict[str, float]:
    """Validation-time loss + frame-level AUC. Video-level and cross-dataset
    metrics are ``evaluate.py``'s job — this is the cheap per-epoch signal
    used for early stopping and best-checkpoint selection only."""
    model.eval()
    total_loss = 0.0
    n = 0
    all_logits: list[torch.Tensor] = []
    all_labels: list[torch.Tensor] = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        labels = batch["label"].to(device, non_blocking=True)
        logits = model(images)
        loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)

        batch_size = images.size(0)
        total_loss += loss.item() * batch_size
        n += batch_size
        all_logits.append(logits.cpu())
        all_labels.append(labels.cpu())

    logits_cat = torch.cat(all_logits).squeeze(1).numpy()
    labels_cat = torch.cat(all_labels).squeeze(1).numpy()
    probs = 1.0 / (1.0 + np.exp(-logits_cat))
    auc = (
        float(roc_auc_score(labels_cat, probs))
        if len(np.unique(labels_cat)) > 1
        else float("nan")
    )
    return {"loss": total_loss / n, "auc": auc}


def fit(
    cfg: Config | None = None,
    resume: bool = True,
    device: str | None = None,
    train_loader: DataLoader | None = None,
    val_loader: DataLoader | None = None,
) -> TrainState:
    """Train :class:`DeepfakeNet` end to end: build data loaders if not
    given, resume from ``<arch>_latest.pt`` when present, run epochs with
    checkpointing + early stopping, return the final :class:`TrainState`.

    ``train_loader``/``val_loader`` are injectable so tests can exercise the
    loop over a handful of synthetic items instead of the real ~80k-crop
    dataset.
    """
    cfg = cfg or Config()
    device = device or resolve_device()
    seed_everything(cfg.train.seed)

    model = DeepfakeNet(cfg.model).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=cfg.train.learning_rate, weight_decay=cfg.train.weight_decay
    )

    if train_loader is None:
        train_loader = make_dataloader(FaceCropDataset(cfg, split="train"), cfg, split="train")
    if val_loader is None:
        val_loader = make_dataloader(FaceCropDataset(cfg, split="val"), cfg, split="val")

    scheduler = _build_scheduler(optimizer, cfg, steps_per_epoch=len(train_loader))
    scaler = torch.cuda.amp.GradScaler(enabled=cfg.train.mixed_precision and device == "cuda")

    cfg.paths.ensure()
    checkpoint_path = cfg.paths.checkpoints / f"{cfg.model.architecture}_latest.pt"
    best_path = cfg.paths.checkpoints / f"{cfg.model.architecture}_best.pt"

    state = TrainState()
    start_epoch = 0
    if resume and checkpoint_path.exists():
        state = load_checkpoint(
            checkpoint_path, model, optimizer, scheduler, scaler, device=device
        )
        start_epoch = state.epoch
        logger.info(
            "Resumed from %s at epoch %d (best %s=%.4f)",
            checkpoint_path,
            start_epoch,
            cfg.train.monitor_metric,
            state.best_metric,
        )

    for epoch in range(start_epoch, cfg.train.epochs):
        t0 = time.perf_counter()
        train_loss = train_one_epoch(model, train_loader, optimizer, scheduler, device, scaler, cfg)
        val_metrics = evaluate_epoch(model, val_loader, device)
        elapsed = time.perf_counter() - t0

        state.epoch = epoch + 1
        state.history.append({"epoch": epoch + 1, "train_loss": train_loss, **val_metrics})
        logger.info(
            "epoch %d/%d | train_loss=%.4f | val_loss=%.4f | val_auc=%.4f | %.1fs",
            epoch + 1,
            cfg.train.epochs,
            train_loss,
            val_metrics["loss"],
            val_metrics["auc"],
            elapsed,
        )

        monitor_value = (
            val_metrics["auc"] if cfg.train.monitor_metric == "val_auc" else -val_metrics["loss"]
        )
        if not math.isnan(monitor_value) and monitor_value > state.best_metric:
            state.best_metric = monitor_value
            state.epochs_without_improvement = 0
            save_checkpoint(best_path, model, optimizer, scheduler, scaler, state)
        else:
            state.epochs_without_improvement += 1

        if cfg.train.checkpoint_every_epoch:
            save_checkpoint(checkpoint_path, model, optimizer, scheduler, scaler, state)

        if state.epochs_without_improvement >= cfg.train.early_stopping_patience:
            logger.info(
                "Early stopping at epoch %d (no improvement in %d epochs)",
                epoch + 1,
                state.epochs_without_improvement,
            )
            break

    return state
