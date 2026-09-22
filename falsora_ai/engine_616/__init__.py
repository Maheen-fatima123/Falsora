"""
Module 6.16 — Frame Buffer & Rolling Score Engine.
===================================================

Public API for Ujala (6.13/6.14) and Mehreen (6.8/6.12) to import. Everything
that crosses a module boundary is also defined in ``falsora_ai.contracts``
(``FrameScore`` in, ``RollingScoreState`` out) — import the types from there.

No torch import anywhere in this package; see ENGINEERING_PLAN.md 3.1.

Typical usage (one instance per live session, module 6.13 owns the lifecycle):

    from falsora_ai.engine_616 import RollingScoreEngine
    from falsora_ai.contracts import FrameScore

    engine = RollingScoreEngine(session_id="...")
    for frame in incoming_frames:  # FrameScore, one per analysed frame
        state = engine.push(frame)
        if state.alert_triggered:
            notify_reviewer(state)  # module 6.12
"""

from __future__ import annotations

from falsora_ai.engine_616.buffer import BufferedFrame, FrameBuffer
from falsora_ai.engine_616.evidence import save_snapshots
from falsora_ai.engine_616.rolling import RollingScoreEngine

__all__ = [
    "BufferedFrame",
    "FrameBuffer",
    "RollingScoreEngine",
    "save_snapshots",
]
