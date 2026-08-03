"""Tests for configuration.

Two things are checked that are easy to get wrong and expensive to discover late:

  1. Importing config must have NO side effects (the original utils/config.py
     created directories and imported torch at import time).
  2. The frame budget must actually produce balanced classes. If someone edits
     frames_per_video without recomputing, training silently skews.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from falsora_ai.config import (
    Config,
    DataConfig,
    FaceConfig,
    LiveConfig,
    ModelConfig,
    PathConfig,
)


class TestNoImportSideEffects:
    def test_construction_creates_no_directories(self, tmp_path: Path) -> None:
        """Constructing config must be inert; only ensure() may touch the disk."""
        paths = PathConfig(
            root=tmp_path,
            raw_datasets=tmp_path / "raw_datasets",
            face_crops=tmp_path / "face_crops",
            manifests=tmp_path / "manifests",
            models=tmp_path / "models",
            checkpoints=tmp_path / "checkpoints",
            outputs=tmp_path / "outputs",
            gradcam=tmp_path / "gradcam",
            logs=tmp_path / "logs",
        )
        assert list(tmp_path.iterdir()) == [], "constructing PathConfig wrote to disk"

        paths.ensure()
        assert {p.name for p in tmp_path.iterdir()} == {
            "face_crops",
            "manifests",
            "models",
            "checkpoints",
            "outputs",
            "gradcam",
            "logs",
        }

    def test_ensure_never_creates_input_directories(self, tmp_path: Path) -> None:
        """Creating raw_datasets/ would mask a misconfigured dataset path."""
        paths = PathConfig(
            root=tmp_path,
            raw_datasets=tmp_path / "raw_datasets",
            face_crops=tmp_path / "face_crops",
            manifests=tmp_path / "manifests",
            models=tmp_path / "models",
            checkpoints=tmp_path / "checkpoints",
            outputs=tmp_path / "outputs",
            gradcam=tmp_path / "gradcam",
            logs=tmp_path / "logs",
        )
        paths.ensure()
        assert not (tmp_path / "raw_datasets").exists()

    def test_config_does_not_import_torch(self) -> None:
        """Ujala's API layer imports config; it must not pay for CUDA init."""
        import inspect

        import falsora_ai.config as cfg_module

        source = inspect.getsource(cfg_module)
        top_level = [
            line
            for line in source.splitlines()
            if line.startswith("import torch") or line.startswith("from torch")
        ]
        assert not top_level, "torch must only be imported inside functions"


class TestFrameBudget:
    """The frame budget is a correctness property, not a preference."""

    def test_every_source_has_a_frame_count(self) -> None:
        data = DataConfig()
        missing = set(data.SOURCE_LABELS) - set(data.frames_per_video)
        assert not missing, f"Sources without a frame budget: {missing}"

    def test_every_source_has_a_domain(self) -> None:
        data = DataConfig()
        missing = set(data.SOURCE_LABELS) - set(data.domain_of)
        assert not missing, f"Sources without a domain: {missing}"

    def test_duplicate_source_is_excluded(self) -> None:
        """FF++/fake is a verified subset of DeepFakeDetection."""
        data = DataConfig()
        assert "FF++/fake" in data.EXCLUDED_SOURCES
        assert "FF++/fake" not in data.SOURCE_LABELS

    def test_dfd_real_counterpart_is_included(self) -> None:
        """FF++/real is the only REAL counterpart to the 1000 DFD fakes."""
        data = DataConfig()
        assert data.SOURCE_LABELS["FF++/real"] == "real"
        assert data.domain_of["FF++/real"] == "dfd"

    def test_class_balance_is_within_tolerance(self) -> None:
        """Verified video counts x frame budget must give ~1:1 real:fake."""
        video_counts = {
            "FaceForensics++_C23/original": 1000,
            "FaceForensics++_C23/Deepfakes": 1000,
            "FaceForensics++_C23/Face2Face": 1000,
            "FaceForensics++_C23/FaceSwap": 1000,
            "FaceForensics++_C23/FaceShifter": 1000,
            "FaceForensics++_C23/NeuralTextures": 1000,
            "FaceForensics++_C23/DeepFakeDetection": 1000,
            "FF++/real": 200,
            "Celeb DF/Celeb-real": 590,
            "Celeb DF/YouTube-real": 300,
            "Celeb DF/Celeb-synthesis": 5639,
        }
        data = DataConfig()
        totals = {"real": 0, "fake": 0}
        for source, n_videos in video_counts.items():
            label = data.SOURCE_LABELS[source]
            totals[label] += n_videos * data.frames_for(source)

        ratio = totals["fake"] / totals["real"]
        assert 0.85 <= ratio <= 1.20, (
            f"Class imbalance {ratio:.2f}:1 fake:real exceeds tolerance. "
            f"real={totals['real']:,} fake={totals['fake']:,}. "
            "Re-tune DataConfig.frames_per_video."
        )

    def test_split_ratios_sum_to_one(self) -> None:
        data = DataConfig()
        total = data.train_ratio + data.val_ratio + data.test_ratio
        assert total == pytest.approx(1.0)


class TestLiveConfig:
    def test_scope_document_defaults(self) -> None:
        """These values are quoted in the scope document and must not drift."""
        live = LiveConfig()
        assert live.buffer_size == 5  # scope 6.16 "last 5 frames"
        assert live.high_risk_threshold == 0.35  # scope 5.1 Stage 4
        assert live.capture_fps == 1.0  # scope 5.1 Stage 1

    def test_threshold_ordering_enforced(self) -> None:
        with pytest.raises(ValueError, match="watch_threshold"):
            LiveConfig(high_risk_threshold=0.7, watch_threshold=0.4)

    def test_unreachable_verdict_rejected(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            LiveConfig(buffer_size=3, min_frames_for_verdict=5)


class TestModelConfig:
    @pytest.mark.parametrize(
        ("arch", "size"),
        [
            ("efficientnet_b0", 224),
            ("efficientnet_b3", 300),
            ("efficientnet_b4", 320),
            ("xception", 299),
        ],
    )
    def test_input_size_resolution(self, arch: str, size: int) -> None:
        assert ModelConfig(architecture=arch).resolved_input_size() == size


class TestConfigComposition:
    def test_defaults_construct(self) -> None:
        cfg = Config()
        assert cfg.model.architecture == "efficientnet_b0"
        assert cfg.face.margin == 0.3

    def test_replace_is_immutable(self) -> None:
        cfg = Config()
        modified = cfg.replace(face=FaceConfig(margin=0.5))
        assert modified.face.margin == 0.5
        assert cfg.face.margin == 0.3  # original untouched

    def test_frozen(self) -> None:
        """Config is immutable; mutation must fail, not silently succeed."""
        cfg = Config()
        with pytest.raises(FrozenInstanceError):
            cfg.model = ModelConfig()  # type: ignore[misc]

    def test_to_dict_is_serialisable_shape(self) -> None:
        assert set(Config().to_dict()) == {
            "paths",
            "data",
            "face",
            "model",
            "train",
            "live",
        }
