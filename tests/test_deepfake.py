"""Tests for module 6.6a — the deepfake branch: model, training loop, eval.

Everything here runs on CPU with ``ModelConfig(pretrained=False)`` (no
ImageNet download) and tiny synthetic datasets (a handful of real JPEGs
written under ``tmp_path`` via ``cv2.imwrite``, matching the pattern in
``tests/test_datasets.py``). Nothing asserts the model has learned anything
— that needs a real ~80k-crop training run and is out of scope for a unit
test. What is tested is the contract: shapes, checkpoint round-trips,
resume-from-checkpoint behaviour, and the AUC aggregation math in
``evaluate.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
torch = pytest.importorskip("torch")
pytest.importorskip("timm")

from falsora_ai.config import Config, ModelConfig, PathConfig, TrainConfig  # noqa: E402
from falsora_ai.data.datasets import CropRow, FaceCropDataset, make_dataloader  # noqa: E402
from falsora_ai.data.transforms import deepfake_transforms  # noqa: E402
from falsora_ai.engine_66.deepfake.evaluate import (  # noqa: E402
    evaluate_split,
    frame_level_auc,
    video_level_auc,
)
from falsora_ai.engine_66.deepfake.model import DeepfakeNet  # noqa: E402
from falsora_ai.engine_66.deepfake.train import (  # noqa: E402
    TrainState,
    evaluate_epoch,
    fit,
    load_checkpoint,
    save_checkpoint,
    train_one_epoch,
)


def _write_jpeg(path: Path, size: int = 48, color: tuple[int, int, int] = (10, 20, 30)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((size, size, 3), color, dtype=np.uint8)
    cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))


def _tiny_cfg(tmp_path: Path) -> Config:
    """No pretrained download, tiny batch size, everything routed to
    tmp_path so a test run never touches the real project's checkpoints/."""
    return Config(
        paths=PathConfig(root=tmp_path, checkpoints=tmp_path / "checkpoints"),
        model=ModelConfig(architecture="efficientnet_b0", pretrained=False),
        train=TrainConfig(
            batch_size=2,
            epochs=2,
            num_workers=0,
            mixed_precision=False,
            early_stopping_patience=10,
            warmup_epochs=1,
        ),
    )


def _rows(tmp_path: Path, n_real: int = 2, n_fake: int = 2, split: str = "train") -> list[CropRow]:
    rows = []
    for i in range(n_real):
        path = tmp_path / "crops" / f"real_{i}.jpg"
        _write_jpeg(path, color=(200, 200, 200))
        rows.append(
            CropRow(str(path), split, "real", "ffpp", "FaceForensics++_C23/original", f"g{i}", f"v{i}.mp4")
        )
    for i in range(n_fake):
        path = tmp_path / "crops" / f"fake_{i}.jpg"
        _write_jpeg(path, color=(20, 20, 20))
        rows.append(
            CropRow(str(path), split, "fake", "ffpp", "FaceForensics++_C23/Deepfakes", f"g{i+n_real}", f"v{i}_fake.mp4")
        )
    return rows


class TestDeepfakeNet:
    def test_forward_shape_and_dtype(self) -> None:
        model = DeepfakeNet(ModelConfig(architecture="efficientnet_b0", pretrained=False))
        x = torch.randn(2, 3, 224, 224)
        out = model(x)
        assert out.shape == (2, 1)
        assert out.dtype == torch.float32

    def test_reads_architecture_from_config(self) -> None:
        model = DeepfakeNet(ModelConfig(architecture="efficientnet_b0", pretrained=False, dropout=0.1))
        assert model.cfg.architecture == "efficientnet_b0"
        assert isinstance(model.dropout, torch.nn.Dropout)


class TestCheckpointRoundTrip:
    def test_save_and_load_restores_state_exactly(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        model = DeepfakeNet(cfg.model)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: 1.0)
        scaler = torch.cuda.amp.GradScaler(enabled=False)

        state = TrainState(epoch=3, best_metric=0.87, epochs_without_improvement=1)
        state.history.append({"epoch": 3, "train_loss": 0.5, "loss": 0.4, "auc": 0.87})
        path = tmp_path / "ckpt.pt"
        save_checkpoint(path, model, optimizer, scheduler, scaler, state)

        fresh_model = DeepfakeNet(cfg.model)
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
        train_rows = _rows(tmp_path, split="train")
        val_rows = _rows(tmp_path, n_real=1, n_fake=1, split="val")
        train_ds = FaceCropDataset(cfg, split="train", rows=train_rows)
        val_ds = FaceCropDataset(
            cfg, split="val", rows=val_rows, transform=deepfake_transforms(cfg, split="val")
        )
        train_loader = make_dataloader(train_ds, cfg, split="train")
        val_loader = make_dataloader(val_ds, cfg, split="val", shuffle=False)
        return train_loader, val_loader

    def test_train_one_epoch_returns_finite_loss(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        train_loader, _ = self._loaders(cfg, tmp_path)
        model = DeepfakeNet(cfg.model)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: 1.0)
        loss = train_one_epoch(model, train_loader, optimizer, scheduler, "cpu", None, cfg)
        assert np.isfinite(loss)

    def test_evaluate_epoch_returns_loss_and_auc(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        _, val_loader = self._loaders(cfg, tmp_path)
        model = DeepfakeNet(cfg.model)
        metrics = evaluate_epoch(model, val_loader, "cpu")
        assert np.isfinite(metrics["loss"])
        assert 0.0 <= metrics["auc"] <= 1.0 or np.isnan(metrics["auc"])

    def test_fit_checkpoints_and_resumes(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path).replace(train=TrainConfig(
            batch_size=2, epochs=1, num_workers=0, mixed_precision=False,
            early_stopping_patience=10, warmup_epochs=1,
        ))
        train_loader, val_loader = self._loaders(cfg, tmp_path)
        state = fit(cfg, resume=False, device="cpu", train_loader=train_loader, val_loader=val_loader)

        assert state.epoch == 1
        latest = cfg.paths.checkpoints / f"{cfg.model.architecture}_latest.pt"
        assert latest.exists()

        # Resuming with epochs already reached should be a no-op: the loop
        # range(start_epoch, epochs) is empty and state is returned unchanged.
        resumed_state = fit(
            cfg, resume=True, device="cpu", train_loader=train_loader, val_loader=val_loader
        )
        assert resumed_state.epoch == state.epoch


class TestFrameLevelAUC:
    def test_perfect_separation_gives_auc_one(self) -> None:
        probs = np.array([0.1, 0.2, 0.8, 0.9])
        labels = np.array([0.0, 0.0, 1.0, 1.0])
        auc, accuracy = frame_level_auc(probs, labels)
        assert auc == pytest.approx(1.0)
        assert accuracy == pytest.approx(1.0)

    def test_single_class_returns_nan_not_a_crash(self) -> None:
        probs = np.array([0.1, 0.2, 0.3])
        labels = np.array([0.0, 0.0, 0.0])
        auc, _ = frame_level_auc(probs, labels)
        assert np.isnan(auc)


class TestVideoLevelAUC:
    def test_pools_frames_by_video_before_scoring(self) -> None:
        # video A: real, frames disagree slightly but pool to a low score.
        # video B: fake, frames disagree slightly but pool to a high score.
        probs = np.array([0.1, 0.3, 0.7, 0.9])
        labels = np.array([0.0, 0.0, 1.0, 1.0])
        videos = ["A.mp4", "A.mp4", "B.mp4", "B.mp4"]
        auc, accuracy, n_videos = video_level_auc(probs, labels, videos)
        assert n_videos == 2
        assert auc == pytest.approx(1.0)
        assert accuracy == pytest.approx(1.0)

    def test_frame_disagreement_within_a_video_is_smoothed_by_pooling(self) -> None:
        # A single video with one wildly wrong frame still pools correctly.
        probs = np.array([0.05, 0.05, 0.95])
        labels = np.array([0.0, 0.0, 0.0])
        videos = ["A.mp4", "A.mp4", "A.mp4"]
        _, accuracy, n_videos = video_level_auc(probs, labels, videos)
        assert n_videos == 1
        assert accuracy == pytest.approx(1.0)  # mean prob ~0.35 -> below 0.5


class TestEvaluateSplit:
    def test_returns_consistent_frame_and_video_counts(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        rows = _rows(tmp_path, n_real=2, n_fake=2, split="test")
        dataset = FaceCropDataset(
            cfg, split="test", rows=rows, transform=deepfake_transforms(cfg, split="test")
        )
        model = DeepfakeNet(cfg.model)
        result = evaluate_split(model, cfg, "test", "cpu", dataset=dataset)

        assert result.n_frames == 4
        assert result.n_videos == 4  # each synthetic row has a distinct video_relpath
        assert 0.0 <= result.frame_accuracy <= 1.0
        assert 0.0 <= result.video_accuracy <= 1.0
