"""
Torch ``Dataset`` classes — module 6.6's read path onto disk.
===============================================================

Two datasets, matching the two manifests written earlier in the pipeline:

* :class:`FaceCropDataset` reads ``manifests/crops.csv``
  (:func:`falsora_ai.data.extract.write_crop_index`) — face crops for the
  deepfake branch (module 6.6a).
* :class:`TamperingDataset` reads ``manifests/casia.csv`` via
  :func:`falsora_ai.data.casia_manifest.read_casia_manifest` — whole images
  for the tampering branch (module 6.6b), stacked to 5 channels by
  :func:`falsora_ai.engine_66.tampering.model.build_model_input`.

Not imported by :mod:`falsora_ai.data`'s package ``__init__``, for the same
reason ``extract.py`` is not: this module needs torch, and
``falsora_ai.data`` otherwise stays importable in a plain ``[dev]``
environment with no GPU dependency. Import it directly:
``from falsora_ai.data.datasets import FaceCropDataset``.

Channel order
-------------
Crop JPEGs on disk are BGR-encoded — ``extract.py`` converts RGB to BGR
immediately before ``cv2.imwrite``, matching what ``cv2.imwrite`` expects.
Both datasets here read with ``cv2.imread`` (BGR) and convert back to RGB
before anything else touches the array, so every downstream consumer
(augmentation, the model, Grad-CAM in module 6.7) sees RGB consistently,
matching the convention documented in ``common/faces.py``.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any

import albumentations as A
import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from falsora_ai.config import Config, TamperingConfig
from falsora_ai.data.casia_manifest import ImageRecord, read_casia_manifest
from falsora_ai.data.transforms import (
    SplitName,
    deepfake_transforms,
    resize_stacked_input,
    tampering_spatial_transforms,
)

__all__ = [
    "DEEPFAKE_LABEL_TO_FLOAT",
    "TAMPERING_LABEL_TO_FLOAT",
    "CropRow",
    "FaceCropDataset",
    "TamperingDataset",
    "read_crop_index",
    "make_dataloader",
]

# probability_fake convention (contracts.py): higher = worse, so the positive
# class is "fake" / "tampered". Single logit + BCEWithLogitsLoss on both
# branches, matching ``TamperingCNN.forward``'s docstring.
DEEPFAKE_LABEL_TO_FLOAT = {"real": 0.0, "fake": 1.0}
TAMPERING_LABEL_TO_FLOAT = {"authentic": 0.0, "tampered": 1.0}


def _read_rgb(path: str | Path) -> np.ndarray:
    """``cv2.imread`` (BGR) -> RGB ``uint8``. Raises if the file is unreadable,
    rather than returning ``None`` for a caller to mishandle three lines later."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


# --------------------------------------------------------------------------
# Deepfake branch — face crops
# --------------------------------------------------------------------------


class CropRow:
    """One row of ``manifests/crops.csv``, typed. See
    :func:`~falsora_ai.data.extract.write_crop_index` for the column contract."""

    __slots__ = ("crop_path", "split", "label", "domain", "source", "group", "video_relpath")

    def __init__(
        self,
        crop_path: str,
        split: str,
        label: str,
        domain: str,
        source: str,
        group: str,
        video_relpath: str,
    ) -> None:
        self.crop_path = crop_path
        self.split = split
        self.label = label
        self.domain = domain
        self.source = source
        self.group = group
        self.video_relpath = video_relpath


def read_crop_index(path: str | Path) -> list[CropRow]:
    """Read ``crops.csv`` in full. Small enough (~100k rows) to hold in memory;
    ``FaceCropDataset`` filters to one split from this list at construction."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        return [CropRow(**row) for row in csv.DictReader(fh)]


class FaceCropDataset(Dataset):
    """Face crops for the deepfake branch, one split at a time.

    Args:
        cfg: Root config. Supplies ``paths.crop_manifest`` (default source)
            and is threaded through to :func:`~falsora_ai.data.transforms.deepfake_transforms`
            when ``transform`` is not given explicitly.
        split: ``"train"`` | ``"val"`` | ``"test"`` | ``"heldout"``. Matches
            the ``split`` column written by ``write_crop_index`` (``heldout``
            is Celeb-DF, per ``DataConfig.DOMAIN_ROLES``).
        transform: Overrides the default albumentations pipeline. Mainly for
            tests, which need a cheap, deterministic transform rather than the
            real augmentation stack.
        manifest_path: Overrides ``cfg.paths.crop_manifest``, for tests.

    Each item is a dict rather than a bare tuple: the crop, video and domain
    are exactly what module 6.7's evidence trail and any per-domain metric
    breakdown need, and a dict survives the default collate function without
    extra work (strings collate to a list of strings).
    """

    def __init__(
        self,
        cfg: Config | None = None,
        split: SplitName = "train",
        transform: A.Compose | None = None,
        manifest_path: str | Path | None = None,
        rows: list[CropRow] | None = None,
    ) -> None:
        self.cfg = cfg or Config()
        self.split = split
        # NOT `transform or default`: an empty `A.Compose([])` is falsy (it
        # defines `__len__`), which would silently discard a caller's
        # deliberately-empty transform and substitute the real augmentation
        # pipeline in its place.
        self.transform = (
            transform if transform is not None else deepfake_transforms(self.cfg, split=split)
        )

        if rows is not None:
            all_rows = rows
        else:
            path = Path(manifest_path) if manifest_path is not None else self.cfg.paths.crop_manifest
            all_rows = read_crop_index(path)
        self.rows = [r for r in all_rows if r.split == split]
        if not self.rows:
            raise ValueError(
                f"No rows with split={split!r} in the crop index "
                f"({len(all_rows)} rows total). Has extraction finished, and "
                "does the manifest match this split name?"
            )

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        image = _read_rgb(row.crop_path)
        transformed = self.transform(image=image)["image"]
        label = DEEPFAKE_LABEL_TO_FLOAT[row.label]
        return {
            "image": transformed,
            "label": torch.tensor([label], dtype=torch.float32),
            "crop_path": row.crop_path,
            "video_relpath": row.video_relpath,
            "domain": row.domain,
            "group": row.group,
        }


# --------------------------------------------------------------------------
# Tampering branch — CASIA v2.0
# --------------------------------------------------------------------------


class TamperingDataset(Dataset):
    """Whole images for the tampering branch (module 6.6b), one split at a time.

    Unlike ``FaceCropDataset``, augmentation here happens in two stages: a
    geometry-only albumentations pass on the raw RGB image
    (:func:`~falsora_ai.data.transforms.tampering_spatial_transforms`), *then*
    ``build_model_input`` stacks ELA and the noise residual computed from the
    (possibly flipped/rotated) image, then the 5-channel stack is resized as
    one array. See ``transforms.py``'s module docstring for why the ordering
    matters.

    Args:
        cfg: Root config. Supplies ``paths.casia_manifest``, ``paths.casia_root``
            (crop_path resolution) and ``tampering`` (ELA/residual parameters,
            input size).
        split: ``"train"`` | ``"val"`` | ``"test"``, matching
            :mod:`falsora_ai.data.casia_splits`.
        spatial_transform: Overrides the default geometry-only pipeline.
        manifest_path: Overrides ``cfg.paths.casia_manifest``, for tests.
        records: Pre-loaded records, bypassing the manifest file entirely —
            what the test suite uses.
    """

    def __init__(
        self,
        cfg: Config | None = None,
        split: SplitName = "train",
        spatial_transform: A.Compose | None = None,
        manifest_path: str | Path | None = None,
        records: list[ImageRecord] | None = None,
    ) -> None:
        self.cfg = cfg or Config()
        self.tampering_cfg: TamperingConfig = self.cfg.tampering
        self.split = split
        # See the identical note in FaceCropDataset.__init__: `or` would
        # discard a caller's deliberately-empty `A.Compose([])`.
        self.spatial_transform = (
            spatial_transform if spatial_transform is not None else tampering_spatial_transforms(split)
        )

        if records is not None:
            all_records = records
        else:
            path = (
                Path(manifest_path)
                if manifest_path is not None
                else self.cfg.paths.casia_manifest
            )
            all_records = read_casia_manifest(path)
        self.records = [r for r in all_records if r.split == split]
        if not self.records:
            raise ValueError(
                f"No records with split={split!r} in the CASIA manifest "
                f"({len(all_records)} records total)."
            )

    def __len__(self) -> int:
        return len(self.records)

    def _image_path(self, record: ImageRecord) -> Path:
        return self.cfg.paths.casia_root / record.relpath

    def __getitem__(self, index: int) -> dict[str, Any]:
        # Local import: keeps torch out of this dataset's import-time cost
        # for callers that only need FaceCropDataset, and avoids a circular
        # import (engine_66.tampering.model doesn't need to know datasets.py
        # exists).
        from falsora_ai.engine_66.tampering.model import build_model_input

        record = self.records[index]
        image = _read_rgb(self._image_path(record))
        image = self.spatial_transform(image=image)["image"]

        stacked = build_model_input(image, self.tampering_cfg)  # HxWx5, float32, [0, 1]
        stacked = resize_stacked_input(stacked, self.tampering_cfg.input_size)
        tensor = torch.from_numpy(stacked.transpose(2, 0, 1).copy())  # CxHxW

        label = TAMPERING_LABEL_TO_FLOAT[record.label]
        return {
            "image": tensor,
            "label": torch.tensor([label], dtype=torch.float32),
            "relpath": record.relpath,
            "group": record.group,
        }


# --------------------------------------------------------------------------
# DataLoader construction
# --------------------------------------------------------------------------


def make_dataloader(
    dataset: Dataset,
    cfg: Config | None = None,
    split: SplitName = "train",
    shuffle: bool | None = None,
    collate_fn: Callable[[list[Any]], Any] | None = None,
) -> DataLoader:
    """One place to turn ``TrainConfig`` into a ``DataLoader``, so batch size,
    worker count and shuffling policy cannot drift between the two branches.

    ``shuffle`` defaults to ``True`` only for ``split == "train"``; val/test/
    heldout are evaluated in a fixed, reproducible order. ``drop_last`` mirrors
    the same rule, since a partial final batch only matters for training
    (batch-norm statistics), not for computing an AUC over a whole split.
    """
    cfg = cfg or Config()
    train_cfg = cfg.train
    is_train = split == "train"
    return DataLoader(
        dataset,
        batch_size=train_cfg.batch_size,
        shuffle=is_train if shuffle is None else shuffle,
        num_workers=train_cfg.num_workers,
        pin_memory=True,
        drop_last=is_train,
        collate_fn=collate_fn,
    )
