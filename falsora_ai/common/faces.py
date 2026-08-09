"""
Face detection and cropping — shared by training extraction and live inference.
==============================================================================

This module exists to make one specific bug impossible.

A deepfake classifier is extremely sensitive to how tightly the face is cropped.
Train on crops with 30% context and serve crops with 0% context and accuracy
drops sharply for no visible reason: the model never sees the hairline and jaw
boundary where blending artefacts concentrate. It is an easy mistake because the
two code paths are written weeks apart, by which time the margin looks like an
arbitrary constant rather than a contract.

So the geometry lives in exactly one function, :func:`expand_box`, and both the
offline extraction in :mod:`falsora_ai.data.extract` and the online path in
:mod:`falsora_ai.engine_66` call it. If the margin ever changes, it changes for
both at once.

Torch is imported lazily inside :class:`MTCNNDetector`, so importing this module
costs nothing in Ujala's API process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from falsora_ai.config import FaceConfig

__all__ = [
    "Box",
    "expand_box",
    "crop_face",
    "FaceDetector",
    "MTCNNDetector",
]


@dataclass(frozen=True)
class Box:
    """Axis-aligned face box in pixels, ``x2``/``y2`` exclusive."""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 1.0

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def size(self) -> int:
        """Shorter side — what ``FaceConfig.min_face_size`` is compared against."""
        return min(self.width, self.height)


def expand_box(box: Box, margin: float, frame_w: int, frame_h: int) -> Box:
    """Grow ``box`` by ``margin`` and square it, clipped to the frame.

    Three things happen, in this order, and the order is load-bearing:

    1. **Expand.** Each side grows by ``margin/2`` of the box dimension, so a
       margin of 0.3 adds 30% total width and height, centred.
    2. **Square.** The longer side wins. Non-square crops get squashed by the
       model's resize, distorting facial proportions differently depending on
       head pose — which is a feature the model can learn instead of learning
       forgery artefacts.
    3. **Clip, preserving size where possible.** A face near the frame edge is
       shifted back inside rather than truncated, so it keeps its scale. Only
       when the square exceeds the whole frame is it actually shrunk.

    Naive clipping (step 3 done as a plain ``max(0, ...)``) is the subtle bug
    here: it silently produces smaller, off-centre crops for exactly the
    profile and edge-of-frame faces that are hardest to classify.
    """
    if margin < 0:
        raise ValueError(f"margin must be non-negative, got {margin}")

    cx = (box.x1 + box.x2) / 2.0
    cy = (box.y1 + box.y2) / 2.0
    side = max(box.width, box.height) * (1.0 + margin)
    side = min(side, float(min(frame_w, frame_h)))  # cannot exceed the frame
    half = side / 2.0

    # Shift the centre so the square fits without shrinking.
    cx = min(max(cx, half), frame_w - half)
    cy = min(max(cy, half), frame_h - half)

    x1 = int(round(cx - half))
    y1 = int(round(cy - half))
    return Box(
        x1=max(0, x1),
        y1=max(0, y1),
        x2=min(frame_w, x1 + int(round(side))),
        y2=min(frame_h, y1 + int(round(side))),
        confidence=box.confidence,
    )


def crop_face(
    frame: np.ndarray, box: Box, face: FaceConfig
) -> np.ndarray:
    """Expand, crop and resize to ``face.crop_size``. Returns RGB uint8.

    Crops are stored larger than any model input (300 px by default) so that
    switching from EfficientNet-B0 at 224 to B4 at 320 does not require
    re-running the six-hour extraction.
    """
    import cv2  # local: keeps this module importable without OpenCV

    h, w = frame.shape[:2]
    expanded = expand_box(box, face.margin, w, h)
    patch = frame[expanded.y1 : expanded.y2, expanded.x1 : expanded.x2]
    if patch.size == 0:
        raise ValueError(f"Empty crop for box {expanded} in frame {w}x{h}")
    # INTER_AREA for downscaling (the usual case) avoids the aliasing that
    # INTER_LINEAR introduces — and aliasing is itself a high-frequency
    # artefact, which is precisely the signal the model is meant to read.
    interpolation = (
        cv2.INTER_AREA
        if patch.shape[0] > face.crop_size
        else cv2.INTER_CUBIC
    )
    return cv2.resize(
        patch, (face.crop_size, face.crop_size), interpolation=interpolation
    )


class FaceDetector(Protocol):
    """Minimal detector interface, so the pipeline is not welded to MTCNN.

    A batch method rather than a single-frame one: MTCNN is several times
    faster per frame on a batch, and extraction is the pipeline's slowest stage.
    """

    def detect_batch(self, frames: list[np.ndarray]) -> list[Box | None]:
        """One box per frame, or ``None`` where no face passed the filters."""
        ...


class MTCNNDetector:
    """MTCNN via facenet-pytorch.

    Chosen over Haar cascades because Haar misses profile and partially
    occluded faces at a rate that would silently bias the dataset toward
    frontal, well-lit examples — the easy cases — and inflate every metric.

    Torch is imported in ``__init__``, not at module scope, so that
    ``import falsora_ai.common.faces`` stays free for the API process.
    """

    def __init__(self, face: FaceConfig, device: str = "cpu") -> None:
        from facenet_pytorch import MTCNN  # noqa: PLC0415 — deliberately lazy

        self.face = face
        self._mtcnn = MTCNN(
            image_size=face.crop_size,
            margin=0,  # margin is applied by expand_box, not here
            min_face_size=face.min_face_size,
            keep_all=not face.largest_face_only,
            post_process=False,
            device=device,
        )

    def detect_batch(self, frames: list[np.ndarray]) -> list[Box | None]:
        """Detect in a batch of same-sized RGB frames.

        Frames of differing sizes are detected one at a time, because MTCNN
        requires a uniform batch. Within one video they are uniform, so the
        fallback is rare.
        """
        if not frames:
            return []
        shapes = {f.shape for f in frames}
        if len(shapes) > 1:
            return [self.detect_batch([f])[0] for f in frames]

        boxes, probs = self._mtcnn.detect(frames)
        # strict=True: MTCNN returns one entry per input frame. A length
        # mismatch would silently misalign boxes with frames — every crop taken
        # from the wrong image — so it must be an exception, not a truncation.
        return [
            self._best(frame_boxes, frame_probs, frames[0].shape)
            for frame_boxes, frame_probs in zip(boxes, probs, strict=True)
        ]

    def _best(
        self,
        boxes: np.ndarray | None,
        probs: np.ndarray | None,
        shape: tuple[int, ...],
    ) -> Box | None:
        """Largest face above the confidence and size thresholds.

        Largest rather than most-confident: these datasets are single-subject,
        and where a bystander appears in the background the subject is the
        bigger face. Picking by confidence can lock onto a small, sharply
        focused background face.
        """
        if boxes is None or len(boxes) == 0:
            return None
        if probs is None or len(probs) != len(boxes):
            # No usable confidences means we cannot apply min_confidence. Better
            # to drop the frame than to admit detections of unknown quality
            # into the training set.
            return None

        h, w = shape[0], shape[1]
        best: Box | None = None
        for raw, prob in zip(boxes, probs, strict=True):
            if prob is None or float(prob) < self.face.min_confidence:
                continue
            candidate = Box(
                x1=max(0, int(raw[0])),
                y1=max(0, int(raw[1])),
                x2=min(w, int(raw[2])),
                y2=min(h, int(raw[3])),
                confidence=float(prob),
            )
            if candidate.size < self.face.min_face_size:
                continue
            if best is None or candidate.size > best.size:
                best = candidate
        return best
