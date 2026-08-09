"""
Frame Buffer — sliding window over one live session's per-frame scores.
=========================================================================

Scope 6.16: "Store the last 5 frames received during a live session in a
sliding frame buffer." This is the raw window that :mod:`rolling` reduces to a
single verdict.

Deliberately **no torch import** (see ENGINEERING_PLAN.md 3.1) — Ujala's
WebSocket server (6.14) constructs and queries a buffer on every incoming
frame, and must not be forced to load a model just to hold state.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from falsora_ai.contracts import FrameScore

__all__ = ["BufferedFrame", "FrameBuffer"]


@dataclass(frozen=True)
class BufferedFrame:
    """A :class:`FrameScore` paired with the raw image bytes that produced it.

    ``image_bytes`` is optional and separate from ``FrameScore`` itself:
    the contract crosses process/network boundaries (it's JSON), while raw
    JPEG bytes only need to live as long as it takes to decide whether this
    frame becomes evidence. Most pushes never need it kept around.
    """

    score: FrameScore
    image_bytes: bytes | None = None


class FrameBuffer:
    """Fixed-size sliding window of :class:`BufferedFrame` for one session.

    One instance per live session — module 6.13 (Ujala) owns the session
    lifecycle and is expected to construct one buffer at session start and
    discard it at session end.
    """

    def __init__(self, session_id: str, capacity: int = 5) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self.session_id = session_id
        self.capacity = capacity
        self._frames: deque[BufferedFrame] = deque(maxlen=capacity)
        self._total_processed = 0

    def push(self, frame: FrameScore, image_bytes: bytes | None = None) -> None:
        """Append a frame, evicting the oldest if the buffer is already full."""
        if frame.session_id != self.session_id:
            raise ValueError(
                f"FrameScore.session_id {frame.session_id!r} does not match "
                f"this buffer's session {self.session_id!r}."
            )
        self._frames.append(BufferedFrame(score=frame, image_bytes=image_bytes))
        self._total_processed += 1

    @property
    def buffered(self) -> tuple[BufferedFrame, ...]:
        """Every buffered entry, oldest first, including any image bytes."""
        return tuple(self._frames)

    @property
    def frames(self) -> tuple[FrameScore, ...]:
        """Just the scores, oldest first — the common case for scoring."""
        return tuple(bf.score for bf in self._frames)

    @property
    def is_full(self) -> bool:
        return len(self._frames) >= self.capacity

    @property
    def total_processed(self) -> int:
        """Frames ever pushed, including ones since evicted. Never resets on overflow."""
        return self._total_processed

    def clear(self) -> None:
        """Empty the window. Does not reset ``total_processed``."""
        self._frames.clear()

    def __len__(self) -> int:
        return len(self._frames)
