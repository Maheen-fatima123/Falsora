"""Tests for module 6.6b's training loop and evaluation — the CASIA v2.0
counterpart to ``tests/test_deepfake.py``.

Same discipline as the deepfake branch's tests: CPU-only, tiny synthetic
image sets written under ``tmp_path``, nothing asserted about learned
accuracy (that needs the real ~12.6k-image CASIA run). What is tested is the
contract: shapes, checkpoint round-trips, resume behaviour, and the AUC
aggregation math in ``evaluate.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
torch = pytest.importorskip("torch")

from falsora_ai.config import Config, PathConfig, TamperingConfig, TrainConfig  # noqa: E402
from falsora_ai.data.casia_manifest import ImageRecord  # noqa: E402
from falsora_ai.data.datasets import TamperingDataset, make_dataloader  # noqa: E402
from falsora_ai.data.transforms import tampering_spatial_transforms  # noqa: E402
from falsora_ai.engine_66.tampering.evaluate import (  # noqa: E402
    evaluate_split,
    image_level_auc,
)
from falsora_ai.engine_66.tampering.model import TamperingCNN  # noqa: E402
from falsora_ai.engine_66.tampering.train import (  # noqa: E402
    CHECKPOINT_STEM,
    TrainState,
    evaluate_epoch,
    fit,
    load_checkpoint,
    save_checkpoint,
    train_one_epoch,
)


def _write_jpeg(path: Path, size: int = 64, color: tuple[int, int, int] = (10, 20, 30)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((size, size, 3), color, dtype=np.uint8)
    cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))


def _tiny_cfg(tmp_path: Path) -> Config:
    """Tiny batch size, everything routed to tmp_path so a test run never
    touches the real project's checkpoints/. ``casia_root`` is a computed
    property (``raw_datasets / "CASIA2"``), not a field — see the identical
    note in ``tests/test_datasets.py::TestTamperingDataset._cfg`` — so
    isolating the fixture means overriding ``raw_datasets`` directly."""
    return Config(
        paths=PathConfig(
            root=tmp_path, raw_datasets=tmp_path, checkpoints=tmp_path / "checkpoints"
        ),
        tampering=TamperingConfig(input_size=32),
        train=TrainConfig(
            batch_size=2,
            epochs=2,
            num_workers=0,
            mixed_precision=False,
            early_stopping_patience=10,
            warmup_epochs=1,
        ),
    )


def _records(
    tmp_path: Path, n_au: int = 2, n_tp: int = 2, split: str = "train"
) -> list[ImageRecord]:
    casia_root = tmp_path / "CASIA2"
    records = []
    for i in range(n_au):
        relpath = f"Au/au_{i}.jpg"
        _write_jpeg(casia_root / relpath, color=(200, 200, 200))
        records.append(
            ImageRecord(relpath=relpath, label="authentic", sources=(f"casia:au{i}",), split=split)
        )
    for i in range(n_tp):
        relpath = f"Tp/tp_{i}.jpg"
        _write_jpeg(casia_root / relpath, color=(20, 20, 20))
        records.append(
            ImageRecord(
                relpath=relpath,
                label="tampered",
                sources=(f"casia:au{i}",),
                mask_relpath=f"CASIA 2 Groundtruth/tp_{i}_gt.png",
                split=split,
            )
        )
    return records


class TestCheckpointRoundTrip:
    def test_save_and_load_restores_state_exactly(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        model = TamperingCNN(cfg.tampering)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: 1.0)
        scaler = torch.cuda.amp.GradScaler(enabled=False)

        state = TrainState(epoch=3, best_metric=0.87, epochs_without_improvement=1)
        state.history.append({"epoch": 3, "train_loss": 0.5, "loss": 0.4, "auc": 0.87})
        path = tmp_path / "ckpt.pt"
        save_checkpoint(path, model, optimizer, scheduler, scaler, state)

        fresh_model = TamperingCNN(cfg.tampering)
        fresh_optimizer = torch.optim.AdamW(fresh_model.parameters(), lr=1e-4)
        fresh_scheduler = torch.optim.lr_scheduler.LambdaLR(fresh_optimizer, lambda step: 1.0)
        restored = load_checkpoint(path, fresh_model, fresh_optimizer, fresh_scheduler, device="cpu")

        assert restored.epoch == 3
        assert restored.best_metric == pytest.approx(0.87)
        assert restored.epochs_without_improvement == 1
        assert restored.history == state.history
        for p1, p2 in zip(model.parameters(), fresh_model.parameters(), strict=True):
            assert torch.allclose(p1, p2)


class TestTrainingLoop:
    def _loaders(self, cfg: Config, tmp_path: Path):
        train_records = _records(tmp_path, split="train")
        val_records = _records(tmp_path, n_au=1, n_tp=1, split="val")
        train_ds = TamperingDataset(cfg, split="train", records=train_records)
        val_ds = TamperingDataset(
            cfg,
            split="val",
            records=val_records,
            spatial_transform=tampering_spatial_transforms(split="val"),
        )
        train_loader = make_dataloader(train_ds, cfg, split="train")
        val_loader = make_dataloader(val_ds, cfg, split="val", shuffle=False)
        return train_loader, val_loader

    def test_train_one_epoch_returns_finite_loss(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        train_loader, _ = self._loaders(cfg, tmp_path)
        model = TamperingCNN(cfg.tampering)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: 1.0)
        loss = train_one_epoch(model, train_loader, optimizer, scheduler, "cpu", None, cfg)
        assert np.isfinite(loss)

    def test_evaluate_epoch_returns_loss_and_auc(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        _, val_loader = self._loaders(cfg, tmp_path)
        model = TamperingCNN(cfg.tampering)
        metrics = evaluate_epoch(model, val_loader, "cpu")
        assert np.isfinite(metrics["loss"])
        assert 0.0 <= metrics["auc"] <= 1.0 or np.isnan(metrics["auc"])

    def test_fit_checkpoints_and_resumes(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path).replace(
            train=TrainConfig(
                batch_size=2,
                epochs=1,
                num_workers=0,
                mixed_precision=False,
                early_stopping_patience=10,
                warmup_epochs=1,
            )
        )
        train_loader, val_loader = self._loaders(cfg, tmp_path)
        state = fit(cfg, resume=False, device="cpu", train_loader=train_loader, val_loader=val_loader)

        assert state.epoch == 1
        latest = cfg.paths.checkpoints / f"{CHECKPOINT_STEM}_latest.pt"
        assert latest.exists()

        # Resuming with epochs already reached should be a no-op: the loop
        # range(start_epoch, epochs) is empty and state is returned unchanged.
        resumed_state = fit(
            cfg, resume=True, device="cpu", train_loader=train_loader, val_loader=val_loader
        )
        assert resumed_state.epoch == state.epoch


class TestImageLevelAUC:
    def test_perfect_separation_gives_auc_one(self) -> None:
        probs = np.array([0.1, 0.2, 0.8, 0.9])
        labels = np.array([0.0, 0.0, 1.0, 1.0])
        auc, accuracy = image_level_auc(probs, labels)
        assert auc == pytest.approx(1.0)
        assert accuracy == pytest.approx(1.0)

    def test_single_class_returns_nan_not_a_crash(self) -> None:
        probs = np.array([0.1, 0.2, 0.3])
        labels = np.array([0.0, 0.0, 0.0])
        auc, _ = image_level_auc(probs, labels)
        assert np.isnan(auc)


class TestEvaluateSplit:
    def test_returns_consistent_image_count(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        records = _records(tmp_path, n_au=2, n_tp=2, split="test")
        dataset = TamperingDataset(
            cfg,
            split="test",
            records=records,
            spatial_transform=tampering_spatial_transforms(split="test"),
        )
        model = TamperingCNN(cfg.tampering)
        result = evaluate_split(model, cfg, "test", "cpu", dataset=dataset)

        assert result.n_images == 4
        assert 0.0 <= result.accuracy <= 1.0
