"""
Image transforms for the two branches of module 6.6.
======================================================

Two pipelines live here because the two branches need incompatible things from
augmentation.

**Deepfake branch (face crops).** The model has to be robust to whatever a real
video call or upload throws at it: recompression, blur, small pose jitter. So
training transforms deliberately damage the image (JPEG re-encode at a random
quality, blur, brightness/contrast jitter) the same way a phone camera or a
video call codec would, on top of the usual flip. Eval transforms do none of
that: resize and normalize only, because a validation number that used random
augmentation would not be reproducible run to run.

**Tampering branch (CASIA v2.0).** Here augmentation is dangerous rather than
merely unnecessary. Error Level Analysis and the noise residual, computed in
:mod:`falsora_ai.engine_66.tampering`, are themselves signals about
compression history and pixel-level noise. Blurring or recompressing the image
before those signals are computed would blur or recompress the very artefact
the model is trained to find, and a stray JPEG-quality augmentation would
inject a *fake* compression edge that has nothing to do with the tampering
boundary. So tampering-branch training augmentation is restricted to
label-preserving, signal-preserving geometry: flips and 90-degree rotations,
applied to the RGB image before ``build_model_input`` stacks it with ELA and
the residual. Resize is applied after stacking, via
:func:`resize_stacked_input`, so all five channels are resampled identically.

Both pipelines share one constant: ``IMAGENET_MEAN`` / ``IMAGENET_STD``, used
only by the deepfake branch. The tampering branch trains from scratch (see
``engine_66/tampering/model.py``), so its 5-channel input is deliberately left
in ``build_model_input``'s native ``[0, 1]`` range rather than normalized
against statistics that describe a pretrained ImageNet backbone it does not
use.
"""

from __future__ import annotations

from typing import Literal

import albumentations as A
import cv2
import numpy as np
from albumentations.pytorch import ToTensorV2

from falsora_ai.config import Config

__all__ = [
    "IMAGENET_MEAN",
    "IMAGENET_STD",
    "SplitName",
    "deepfake_transforms",
    "tampering_spatial_transforms",
    "resize_stacked_input",
]

# Standard ImageNet statistics. Correct because ``ModelConfig.pretrained=True``
# means the deepfake backbone (EfficientNet, via ``timm``) starts from ImageNet
# weights, and every torchvision/timm backbone expects inputs normalized this
# way. Getting this wrong does not error; it just quietly costs several points
# of AUC because the pretrained early layers see out-of-distribution input.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

SplitName = Literal["train", "val", "test", "heldout"]


def deepfake_transforms(cfg: Config | None = None, split: SplitName = "train") -> A.Compose:
    """Face-crop transforms for the deepfake branch (module 6.6a).

    ``split == "train"`` gets the full augmentation stack; every other split
    (``val`` / ``test`` / ``heldout``) gets resize + normalize only, so
    validation and test numbers are deterministic and comparable across runs.

    Args:
        cfg: Supplies the resolved input size for the configured backbone
            (``ModelConfig.resolved_input_size()``). Defaults to a fresh
            ``Config()`` when omitted.
        split: Which pipeline to build.
    """
    cfg = cfg or Config()
    size = cfg.model.resolved_input_size()

    if split == "train":
        return A.Compose(
            [
                A.HorizontalFlip(p=0.5),
                A.Affine(
                    scale=(0.9, 1.1),
                    rotate=(-10, 10),
                    translate_percent=(0.0, 0.05),
                    p=0.5,
                ),
                A.RandomBrightnessContrast(
                    brightness_limit=0.15, contrast_limit=0.15, p=0.5
                ),
                A.OneOf(
                    [
                        A.ImageCompression(quality_range=(50, 95), p=1.0),
                        A.GaussianBlur(blur_limit=(3, 5), p=1.0),
                        A.ISONoise(p=1.0),
                    ],
                    p=0.4,
                ),
                A.Resize(size, size, interpolation=cv2.INTER_AREA),
                A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
                ToTensorV2(),
            ]
        )

    return A.Compose(
        [
            A.Resize(size, size, interpolation=cv2.INTER_AREA),
            A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ToTensorV2(),
        ]
    )


def tampering_spatial_transforms(split: SplitName = "train") -> A.Compose:
    """Geometry-only augmentation for the tampering branch, applied to the RGB
    image before :func:`~falsora_ai.engine_66.tampering.model.build_model_input`
    computes ELA and the noise residual from it.

    Deliberately excludes anything that touches pixel intensity, blur, or
    compression: see the module docstring for why those would corrupt the
    forensic signal rather than just augment it. Returns the identity
    transform outside of ``train``.
    """
    if split != "train":
        return A.Compose([])
    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.2),
            A.RandomRotate90(p=0.3),
        ]
    )


def resize_stacked_input(stacked: np.ndarray, size: int) -> np.ndarray:
    """Resize an ``HxWxC`` array (the 5-channel tampering input) to ``size``.

    ``cv2.resize`` handles an arbitrary channel count in one call, which keeps
    all five channels resampled identically, unlike an albumentations
    ``Resize`` (built for 1/3/4-channel images and image+mask pairs).
    """
    interpolation = cv2.INTER_AREA if stacked.shape[0] > size else cv2.INTER_CUBIC
    return cv2.resize(stacked, (size, size), interpolation=interpolation)
