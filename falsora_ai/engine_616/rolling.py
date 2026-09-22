"""
Rolling Score Engine — smooths per-frame scores into a stable live verdict.
==============================================================================

Implements scope section 5.1 Stage 4 and module 6.16 end to end:

  * a 5-frame rolling **weighted** average authenticity (scope 6.16 bullet 2),
    down-weighting frames module 6.15 (Mehreen) has flagged as low quality
    rather than dropping them outright — a single bad frame should not be
    thrown away, but it also should not carry full voting weight;
  * distinguishing a single unreliable frame from a genuine sustained
    manipulation trend (scope 6.16 bullet 3) via ``min_frames_for_verdict``
    and hysteresis around the HIGH-RISK threshold;
  * firing the HIGH-RISK alert only on the *transition* into that state
    (scope 5.1 Stage 4), not on every frame while it persists;
  * triggering evidence capture on that same transition (scope 6.16 bullet 5).

Sits between module 6.6 (Forgery Detection — supplies ``FrameScore`` per
frame) and module 6.8 (Decision Intelligence — Mehreen). This module does not
decide case-level risk; ``LiveRiskState`` exists only to drive the real-time
WebSocket alert, per the boundary documented in contracts.py.

No torch import — see ENGINEERING_PLAN.md 3.1.
"""

from __future__ import annotations

from falsora_ai.config import LiveConfig, PathConfig
from falsora_ai.contracts import FrameScore, LiveRiskState, RollingScoreState
from falsora_ai.engine_616.buffer import FrameBuffer
from falsora_ai.engine_616.evidence import save_snapshots

__all__ = ["RollingScoreEngine"]


def _frame_weight(frame: FrameScore, config: LiveConfig) -> float:
    return 1.0 if frame.quality_ok else config.downweight_low_quality


def _weighted_mean_authenticity(frames: tuple[FrameScore, ...], config: LiveConfig) -> float:
    weights = [_frame_weight(f, config) for f in frames]
    total_weight = sum(weights)
    if total_weight <= 0:
        # Every buffered frame is flagged low-quality and the configured
        # downweight is exactly 0 — fall back to an unweighted mean rather
        # than dividing by zero. Extreme configuration, not a normal path.
        return sum(f.authenticity for f in frames) / len(frames)
    return sum(f.authenticity * w for f, w in zip(frames, weights, strict=True)) / total_weight


class RollingScoreEngine:
    """Stateful rolling-score tracker for exactly one live session.

    Construct one instance per session (module 6.13 owns the lifecycle) and
    call :meth:`push` once per analysed frame, in order. The engine is not
    safe to share across sessions or across threads for the same session.
    """

    def __init__(
        self,
        session_id: str,
        config: LiveConfig | None = None,
        paths: PathConfig | None = None,
    ) -> None:
        self.session_id = session_id
        self.config = config or LiveConfig()
        self.paths = paths or PathConfig()
        self.buffer = FrameBuffer(session_id=session_id, capacity=self.config.buffer_size)
        self._last_state = LiveRiskState.INSUFFICIENT_DATA

    def push(self, frame: FrameScore, image_bytes: bytes | None = None) -> RollingScoreState:
        """Feed one analysed frame and get back the current smoothed verdict."""
        self.buffer.push(frame, image_bytes)
        buffered = self.buffer.buffered
        frames = tuple(bf.score for bf in buffered)

        rolling_authenticity = _weighted_mean_authenticity(frames, self.config)

        if len(frames) < self.config.min_frames_for_verdict:
            state = LiveRiskState.INSUFFICIENT_DATA
            alert = False
        else:
            state = self._classify(rolling_authenticity)
            alert = state == LiveRiskState.HIGH_RISK and self._last_state != LiveRiskState.HIGH_RISK

        self._last_state = state

        evidence_paths: list[str] = []
        if alert and self.config.save_evidence_on_alert:
            evidence_paths = save_snapshots(self.session_id, buffered, self.paths)

        return RollingScoreState(
            session_id=self.session_id,
            rolling_authenticity=rolling_authenticity,
            frames_in_buffer=len(frames),
            buffer_capacity=self.buffer.capacity,
            frames_processed_total=self.buffer.total_processed,
            risk_state=state,
            alert_triggered=alert,
            evidence_paths=evidence_paths,
        )

    def _classify(self, rolling_authenticity: float) -> LiveRiskState:
        """Band the rolling score, applying hysteresis while already HIGH_RISK.

        Once HIGH_RISK, the score must recover past
        ``high_risk_threshold + hysteresis`` (not just past the bare
        threshold) before the state is re-evaluated normally. Without this, a
        score oscillating a fraction of a point around the threshold would
        flap the alert on and off every frame.
        """
        cfg = self.config
        if (
            self._last_state == LiveRiskState.HIGH_RISK
            and rolling_authenticity < cfg.high_risk_threshold + cfg.hysteresis
        ):
            return LiveRiskState.HIGH_RISK

        if rolling_authenticity < cfg.high_risk_threshold:
            return LiveRiskState.HIGH_RISK
        if rolling_authenticity < cfg.watch_threshold:
            return LiveRiskState.WATCH
        return LiveRiskState.OK

    def reset(self) -> None:
        """Clear the buffer and forget state. Does not reset frames_processed_total."""
        self.buffer.clear()
        self._last_state = LiveRiskState.INSUFFICIENT_DATA
