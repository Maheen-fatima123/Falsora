"""
Video decoding and frame sampling.
==================================

Depends on OpenCV only — no torch — so the data pipeline stays importable in a
CI job that installs ``[dev]``.

Why sampling matters
--------------------
The obvious implementation reads the first N frames, or every Kth frame from the
start. Both are wrong for this dataset. Talking-head videos open with a second
or two of a near-static subject, so the first 20 frames are close to 20 copies
of one image: the effective training set is a fraction of its nominal size, and
the model overfits to a single pose and lighting condition per identity.

:func:`sample_frame_indices` therefore spreads the requested frames evenly over
the whole clip, which is also what the model will face at inference time on a
live stream of arbitrary length.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

__all__ = [
    "VideoReadError",
    "sample_frame_indices",
    "probe_frame_count",
    "read_frames",
]


class VideoReadError(RuntimeError):
    """A video could not be opened or yielded no usable frames."""


def sample_frame_indices(total_frames: int, wanted: int) -> list[int]:
    """Pick ``wanted`` frame indices spread evenly across ``total_frames``.

    Indices are taken at the midpoint of ``wanted`` equal-width bins rather than
    at ``linspace(0, total-1)``. Endpoint sampling would always include frame 0
    and the final frame; the first is often a fade-in and the last is often a
    fade-out or a truncated frame, and both are systematically unrepresentative.

    If the clip is shorter than requested, every frame is returned — padding by
    repetition would put identical images in the same batch and inflate the
    apparent dataset size.

    Args:
        total_frames: Frames in the video. Must be positive.
        wanted: Frames to sample. Must be positive.

    Returns:
        Sorted, strictly increasing, all within ``[0, total_frames)``.
    """
    if total_frames <= 0:
        raise VideoReadError(f"total_frames must be positive, got {total_frames}")
    if wanted <= 0:
        raise ValueError(f"wanted must be positive, got {wanted}")
    if wanted >= total_frames:
        return list(range(total_frames))

    edges = np.linspace(0, total_frames, wanted + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0
    indices = np.clip(centres.astype(int), 0, total_frames - 1)
    # Rounding can collide on very short clips; dedupe while staying sorted.
    return sorted(set(indices.tolist()))


def probe_frame_count(path: Path) -> int:
    """Frame count from container metadata, which is fast but sometimes lies.

    Returns 0 when the header is unreliable so the caller can fall back to a
    sequential count rather than trusting a bad number.
    """
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise VideoReadError(f"Cannot open video: {path}")
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return max(count, 0)
    finally:
        cap.release()


def read_frames(path: Path, indices: list[int]) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(index, rgb_frame)`` for each requested index, in order.

    Frames are read sequentially and the wanted ones kept, rather than seeking
    with ``CAP_PROP_POS_FRAMES``. Seeking on H.264 lands on the nearest keyframe
    and silently returns a different frame than the one asked for — which would
    make extraction non-reproducible and, worse, could return the *same* frame
    for several distinct indices. A sequential pass over a 500-frame clip costs
    little and is exact.

    Frames are converted BGR→RGB here, once, so no downstream code has to
    remember which convention it is holding.

    Raises:
        VideoReadError: If the file cannot be opened or no frames were decoded.
    """
    if not indices:
        return

    wanted = set(indices)
    last = max(indices)
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise VideoReadError(f"Cannot open video: {path}")

        position = 0
        yielded = 0
        while position <= last:
            ok, frame = cap.read()
            if not ok:
                break  # truncated file; return what we have
            if position in wanted:
                yield position, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                yielded += 1
            position += 1

        if yielded == 0:
            raise VideoReadError(f"No frames decoded from {path}")
    finally:
        cap.release()
