"""
Evidence Capture — persist frame snapshots when a HIGH-RISK alert fires.
===========================================================================

Scope 6.16: "Save frame snapshots as evidence whenever a HIGH-RISK alert is
triggered." Snapshots are written under ``PathConfig.outputs/evidence/<session>/``
so module 6.10 (Mehreen, Digital Forensic Report Generation) can attach them
to the case file.

Only buffered frames that actually carry image bytes are written. Passing no
bytes on every push (e.g. in tests, or before Ujala's live path is wired up)
is valid — evidence capture degrades to a no-op rather than raising, since it
is a side channel and must never be the reason a live session breaks.
"""

from __future__ import annotations

from falsora_ai.common.logging import get_logger
from falsora_ai.config import PathConfig
from falsora_ai.engine_616.buffer import BufferedFrame

__all__ = ["save_snapshots"]

logger = get_logger(__name__)


def save_snapshots(
    session_id: str,
    buffered_frames: tuple[BufferedFrame, ...],
    paths: PathConfig | None = None,
) -> list[str]:
    """Write any image bytes present in ``buffered_frames`` to disk.

    Returns the paths actually written, in buffer order (oldest first) — this
    is what populates ``RollingScoreState.evidence_paths``. Frames with no
    attached bytes are silently skipped.
    """
    paths = paths or PathConfig()
    out_dir = paths.outputs / "evidence" / session_id

    written: list[str] = []
    for bf in buffered_frames:
        if bf.image_bytes is None:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"frame_{bf.score.frame_index:06d}.jpg"
        file_path.write_bytes(bf.image_bytes)
        written.append(str(file_path))

    if written:
        logger.info(
            "Saved %d evidence snapshot(s) for session %s -> %s",
            len(written),
            session_id,
            out_dir,
        )
    return written
