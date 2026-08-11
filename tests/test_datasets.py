"""Tests for the torch Dataset classes (module M2).

Synthetic data throughout: tiny real JPEGs written under ``tmp_path`` via
``cv2.imwrite``, and hand-built ``CropRow``/``ImageRecord`` lists rather than
real manifests. Nothing here depends on the multi-hour extraction run or the
1.2 GB CASIA download having finished — ``rows=`` / ``records=`` bypass the
manifest file entirely, which is exactly why ``FaceCropDataset`` and
``TamperingDataset`` accept pre-loaded lists.
"""

from __future__ import annotations

from pathlib import Path

import albumentations as A
import numpy as np
import pytest
import torch

cv2 = pytest.importorskip("cv2")

from falsora_ai.config import Config  # noqa: E402
from falsora_ai.data.casia_manifest import ImageRecord  # noqa: E402
from falsora_ai.data.datasets import (  # noqa: E402
    CropRow,
    FaceCropDataset,
    TamperingDataset,
    make_dataloader,
    read_crop_index,
)
from falsora_ai.data.extract import write_crop_index  # noqa: E402
from falsora_ai.data.manifest import VideoRecord  # noqa: E402
from falsora_ai.data.transforms import (  # noqa: E402
    deepfake_transforms,
    tampering_spatial_transforms,
)


def _write_jpeg(path: Path, size: int = 32, color: tuple[int, int, int] = (10, 20, 30)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = np.full((size, size, 3), color, dtype=np.uint8)
    cv2.imwrite(str(path), frame)


def _identity_transform() -> A.Compose:
    """Cheap, deterministic stand-in for the real augmentation stack."""
    return A.Compose([A.Resize(16, 16), A.ToFloat(max_value=255.0)])


# --------------------------------------------------------------------------
# FaceCropDataset
# --------------------------------------------------------------------------


class TestFaceCropDataset:
    def _rows(self, tmp_path: Path) -> list[CropRow]:
        real_path = tmp_path / "real.jpg"
        fake_path = tmp_path / "fake.jpg"
        _write_jpeg(real_path, color=(200, 100, 50))
        _write_jpeg(fake_path, color=(5, 5, 5))
        return [
            CropRow(str(real_path), "train", "real", "ffpp", "src", "grp1", "video1.mp4"),
            CropRow(str(fake_path), "train", "fake", "ffpp", "src", "grp2", "video2.mp4"),
            CropRow(str(fake_path), "val", "fake", "dfd", "src", "grp3", "video3.mp4"),
        ]

    def test_filters_to_the_requested_split(self, tmp_path: Path) -> None:
        ds = FaceCropDataset(rows=self._rows(tmp_path), split="train", transform=_identity_transform())
        assert len(ds) == 2

    def test_empty_split_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No rows with split"):
            FaceCropDataset(rows=self._rows(tmp_path), split="test", transform=_identity_transform())

    def test_item_shape_and_dtype(self, tmp_path: Path) -> None:
        ds = FaceCropDataset(rows=self._rows(tmp_path), split="train", transform=_identity_transform())
        item = ds[0]
        assert item["image"].shape == (16, 16, 3)  # ToFloat/no ToTensorV2 in the stub transform
        assert item["label"].dtype == torch.float32
        assert item["label"].shape == (1,)

    def test_label_direction_matches_probability_fake_convention(self, tmp_path: Path) -> None:
        """real -> 0.0, fake -> 1.0, matching contracts.py's 'higher = worse'."""
        ds = FaceCropDataset(rows=self._rows(tmp_path), split="train", transform=_identity_transform())
        labels = {row.label: item["label"].item() for row, item in zip(ds.rows, (ds[0], ds[1]), strict=True)}
        assert labels["real"] == 0.0
        assert labels["fake"] == 1.0

    def test_metadata_fields_survive(self, tmp_path: Path) -> None:
        ds = FaceCropDataset(rows=self._rows(tmp_path), split="val", transform=_identity_transform())
        item = ds[0]
        assert item["domain"] == "dfd"
        assert item["group"] == "grp3"
        assert item["video_relpath"] == "video3.mp4"

    def test_missing_file_raises_not_silently_returns_none(self, tmp_path: Path) -> None:
        rows = [CropRow(str(tmp_path / "nope.jpg"), "train", "real", "ffpp", "src", "g", "v.mp4")]
        ds = FaceCropDataset(rows=rows, split="train", transform=_identity_transform())
        with pytest.raises(FileNotFoundError):
            ds[0]

    def test_reads_rgb_not_bgr(self, tmp_path: Path) -> None:
        """crop_face stores RGB->BGR on disk (extract.py); the dataset must undo it."""
        path = tmp_path / "colored.jpg"
        _write_jpeg(path, size=8, color=(0, 0, 255))  # BGR order written by cv2.imwrite: pure red
        rows = [CropRow(str(path), "train", "real", "ffpp", "src", "g", "v.mp4")]
        ds = FaceCropDataset(rows=rows, split="train", transform=A.Compose([]))
        image = ds[0]["image"]
        # cv2 wrote BGR (0,0,255) = pure red in BGR order; after BGR->RGB the
        # dataset must report it as (255, 0, 0) in RGB, not (0, 0, 255).
        assert image[0, 0, 0] > 200  # R channel high
        assert image[0, 0, 2] < 50  # B channel low


class TestReadCropIndex:
    def test_round_trips_write_crop_index(self, tmp_path: Path) -> None:
        from falsora_ai.data.extract import ExtractionResult

        video = VideoRecord(
            relpath="FaceForensics++_C23/Deepfakes/000_003.mp4",
            source="FaceForensics++_C23/Deepfakes",
            domain="ffpp",
            label="fake",
            role="train_pool",
            identities=("ffpp:000", "ffpp:003"),
            frames=7,
            group="ffpp:000",
            split="train",
        )
        results = {
            video.relpath: ExtractionResult(
                relpath=video.relpath, status="ok", crops=["/tmp/a.jpg", "/tmp/b.jpg"]
            )
        }
        path = write_crop_index([video], results, tmp_path / "crops.csv")
        rows = read_crop_index(path)
        assert len(rows) == 2
        assert rows[0].crop_path == "/tmp/a.jpg"
        assert rows[0].split == "train"
        assert rows[0].label == "fake"
        assert rows[0].domain == "ffpp"


# --------------------------------------------------------------------------
# TamperingDataset
# --------------------------------------------------------------------------


class TestTamperingDataset:
    def _records(self, tmp_path: Path) -> list[ImageRecord]:
        _write_jpeg(tmp_path / "CASIA2" / "Au" / "Au_ani_00001.jpg", size=40)
        _write_jpeg(tmp_path / "CASIA2" / "Tp" / "Tp_x.jpg", size=40)
        return [
            ImageRecord(
                relpath="Au/Au_ani_00001.jpg",
                label="authentic",
                sources=("casia:ani1",),
                group="casia:ani1",
                split="train",
            ),
            ImageRecord(
                relpath="Tp/Tp_x.jpg",
                label="tampered",
                sources=("casia:ani1",),
                mask_relpath="",
                group="casia:ani1",
                split="train",
            ),
            ImageRecord(
                relpath="Au/Au_ani_00001.jpg",
                label="authentic",
                sources=("casia:ani1",),
                group="casia:ani1",
                split="val",
            ),
        ]

    def _cfg(self, tmp_path: Path) -> Config:
        """``casia_root`` is a computed property (``raw_datasets / "CASIA2"``),
        not a field — so isolating a test fixture means overriding
        ``raw_datasets`` directly, not the top-level ``root``."""
        return Config().replace(paths=Config().paths.__class__(raw_datasets=tmp_path))

    def test_filters_to_the_requested_split(self, tmp_path: Path) -> None:
        cfg = self._cfg(tmp_path)
        ds = TamperingDataset(cfg=cfg, records=self._records(tmp_path), split="train")
        assert len(ds) == 2

    def test_empty_split_raises(self, tmp_path: Path) -> None:
        cfg = self._cfg(tmp_path)
        with pytest.raises(ValueError, match="No records with split"):
            TamperingDataset(cfg=cfg, records=self._records(tmp_path), split="test")

    def test_item_is_five_channel(self, tmp_path: Path) -> None:
        cfg = self._cfg(tmp_path)
        ds = TamperingDataset(cfg=cfg, records=self._records(tmp_path), split="train")
        item = ds[0]
        assert item["image"].shape == (5, cfg.tampering.input_size, cfg.tampering.input_size)
        assert item["image"].dtype == torch.float32
        assert item["image"].min() >= 0.0 and item["image"].max() <= 1.0

    def test_label_direction(self, tmp_path: Path) -> None:
        cfg = self._cfg(tmp_path)
        ds = TamperingDataset(cfg=cfg, records=self._records(tmp_path), split="train")
        labels = [ds[i]["label"].item() for i in range(len(ds))]
        assert labels == [0.0, 1.0]  # authentic, tampered — matches self._records order

    def test_val_split_uses_identity_spatial_transform(self, tmp_path: Path) -> None:
        """Non-train splits must not randomly flip/rotate the eval image."""
        cfg = self._cfg(tmp_path)
        ds = TamperingDataset(cfg=cfg, records=self._records(tmp_path), split="val")
        # identity transform composed of zero ops
        assert len(ds.spatial_transform.transforms) == 0


# --------------------------------------------------------------------------
# Transforms
# --------------------------------------------------------------------------


class TestDeepfakeTransforms:
    def test_train_pipeline_resizes_to_model_input_size(self) -> None:
        cfg = Config()
        tfm = deepfake_transforms(cfg, split="train")
        image = np.zeros((50, 50, 3), dtype=np.uint8)
        out = tfm(image=image)["image"]
        assert out.shape[-2:] == (cfg.model.resolved_input_size(), cfg.model.resolved_input_size())

    def test_eval_pipeline_is_deterministic(self) -> None:
        cfg = Config()
        tfm = deepfake_transforms(cfg, split="val")
        image = np.random.default_rng(0).integers(0, 255, (60, 60, 3), dtype=np.uint8)
        out1 = tfm(image=image)["image"]
        out2 = tfm(image=image)["image"]
        assert torch.equal(out1, out2)


class TestTamperingSpatialTransforms:
    def test_non_train_split_is_identity(self) -> None:
        tfm = tampering_spatial_transforms("val")
        assert len(tfm.transforms) == 0

    def test_train_split_has_only_geometric_ops(self) -> None:
        tfm = tampering_spatial_transforms("train")
        names = {type(t).__name__ for t in tfm.transforms}
        assert names <= {"HorizontalFlip", "VerticalFlip", "RandomRotate90"}


# --------------------------------------------------------------------------
# DataLoader construction
# --------------------------------------------------------------------------


class TestMakeDataloader:
    def _dataset(self, tmp_path: Path) -> FaceCropDataset:
        path = tmp_path / "x.jpg"
        _write_jpeg(path)
        rows = [
            CropRow(str(path), "train", "real", "ffpp", "src", f"g{i}", f"v{i}.mp4")
            for i in range(5)
        ]
        return FaceCropDataset(rows=rows, split="train", transform=_identity_transform())

    def test_train_split_shuffles_and_drops_last(self, tmp_path: Path) -> None:
        loader = make_dataloader(self._dataset(tmp_path), split="train")
        assert loader.drop_last is True

    def test_eval_split_does_not_shuffle_or_drop(self, tmp_path: Path) -> None:
        loader = make_dataloader(self._dataset(tmp_path), split="val")
        assert loader.drop_last is False

    def test_batch_size_comes_from_train_config(self, tmp_path: Path) -> None:
        cfg = Config()
        loader = make_dataloader(self._dataset(tmp_path), cfg=cfg, split="train")
        assert loader.batch_size == cfg.train.batch_size
