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


# Video counts verified by directly counting files on disk (audit, M0).
# These are facts about the datasets, not preferences — if a count changes it
# means the data on disk changed, and the frame budget must be re-tuned.
VIDEO_COUNTS = {
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


def _crop_totals(data: DataConfig, sources: tuple[str, ...]) -> dict[str, int]:
    totals = {"real": 0, "fake": 0}
    for source in sources:
        label = data.SOURCE_LABELS[source]
        totals[label] += VIDEO_COUNTS[source] * data.frames_for(source)
    return totals


class TestDatasetRoles:
    """Celeb-DF is held out of training. This is a protocol decision that the
    test suite must enforce, because a single edit to ``DOMAIN_ROLES`` would
    silently turn an honest cross-dataset benchmark into a self-graded exam.

    The reason it is held out: Celeb-DF's official test list is not
    identity-disjoint from the rest of the dataset — 56 of its 59 celebrity
    identities appear on both sides. Training on the remainder and reporting
    on the test list would measure face memorisation, not deepfake detection.
    """

    def test_celebdf_is_never_trained_on(self) -> None:
        data = DataConfig()
        assert data.DOMAIN_ROLES["celebdf"] == "heldout_test"
        assert not [s for s in data.training_sources() if s.startswith("Celeb DF")]

    def test_heldout_sources_are_exactly_celebdf(self) -> None:
        data = DataConfig()
        assert set(data.heldout_sources()) == {
            "Celeb DF/Celeb-real",
            "Celeb DF/YouTube-real",
            "Celeb DF/Celeb-synthesis",
        }

    def test_training_pool_is_ffpp_and_dfd(self) -> None:
        data = DataConfig()
        assert {data.domain_of[s] for s in data.training_sources()} == {"ffpp", "dfd"}

    def test_every_domain_has_a_role(self) -> None:
        data = DataConfig()
        missing = set(data.domain_of.values()) - set(data.DOMAIN_ROLES)
        assert not missing, f"Domains without a role: {missing}"

    def test_heldout_set_contains_both_classes(self) -> None:
        """A benchmark of only fakes would report a meaningless number."""
        data = DataConfig()
        labels = {data.SOURCE_LABELS[s] for s in data.heldout_sources()}
        assert labels == {"real", "fake"}


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

    def test_training_pool_class_balance(self) -> None:
        """Balance is only meaningful over data we actually train on.

        Held-out Celeb-DF is 6:1 fake by construction and is irrelevant here —
        including it in this sum was the bug this test previously had.
        """
        data = DataConfig()
        totals = _crop_totals(data, data.training_sources())

        ratio = totals["fake"] / totals["real"]
        assert 0.85 <= ratio <= 1.20, (
            f"Training-pool imbalance {ratio:.2f}:1 fake:real exceeds tolerance. "
            f"real={totals['real']:,} fake={totals['fake']:,}. "
            "Re-tune DataConfig.frames_per_video."
        )

    @pytest.mark.parametrize("domain", ["ffpp", "dfd"])
    def test_each_training_domain_is_balanced(self, domain: str) -> None:
        """Global balance can hide a domain that is 90% fake, which teaches the
        model to use domain artefacts as a shortcut for the label."""
        data = DataConfig()
        sources = tuple(
            s for s in data.training_sources() if data.domain_of[s] == domain
        )
        totals = _crop_totals(data, sources)

        ratio = totals["fake"] / totals["real"]
        assert 0.85 <= ratio <= 1.20, (
            f"Domain '{domain}' is {ratio:.2f}:1 fake:real. "
            f"real={totals['real']:,} fake={totals['fake']:,}."
        )

    def test_training_pool_size_is_tractable(self) -> None:
        """A budget that quietly grows past ~120k crops no longer fits the
        overnight CPU extraction window the compute plan assumes."""
        data = DataConfig()
        totals = _crop_totals(data, data.training_sources())
        total = totals["real"] + totals["fake"]
        assert 60_000 <= total <= 120_000, (
            f"Training pool is {total:,} crops; the compute plan assumes ~80k."
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
