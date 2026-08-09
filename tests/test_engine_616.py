"""Tests for module 6.16 — Frame Buffer & Rolling Score Engine.

Covers: sliding-window eviction, the weighted rolling average, the
INSUFFICIENT_DATA / OK / WATCH / HIGH_RISK bands, hysteresis (no alert flap),
alert-only-on-transition, and evidence capture on the HIGH_RISK transition.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from falsora_ai.config import LiveConfig, PathConfig
from falsora_ai.contracts import FrameScore, LiveRiskState
from falsora_ai.engine_616 import FrameBuffer, RollingScoreEngine

SESSION = "session-abc"


def make_frame(index: int, probability_fake: float, quality_ok: bool = True) -> FrameScore:
    return FrameScore(
        session_id=SESSION,
        frame_index=index,
        probability_fake=probability_fake,
        quality_ok=quality_ok,
    )


# --------------------------------------------------------------------------
# FrameBuffer
# --------------------------------------------------------------------------


class TestFrameBuffer:
    def test_rejects_non_positive_capacity(self) -> None:
        with pytest.raises(ValueError):
            FrameBuffer(session_id=SESSION, capacity=0)

    def test_push_and_len(self) -> None:
        buf = FrameBuffer(session_id=SESSION, capacity=5)
        for i in range(3):
            buf.push(make_frame(i, 0.1))
        assert len(buf) == 3
        assert not buf.is_full

    def test_evicts_oldest_when_full(self) -> None:
        buf = FrameBuffer(session_id=SESSION, capacity=3)
        for i in range(5):
            buf.push(make_frame(i, 0.1))
        assert len(buf) == 3
        assert buf.is_full
        assert [f.frame_index for f in buf.frames] == [2, 3, 4]

    def test_total_processed_does_not_reset_on_eviction(self) -> None:
        buf = FrameBuffer(session_id=SESSION, capacity=2)
        for i in range(5):
            buf.push(make_frame(i, 0.1))
        assert buf.total_processed == 5
        assert len(buf) == 2

    def test_rejects_mismatched_session_id(self) -> None:
        buf = FrameBuffer(session_id=SESSION, capacity=5)
        other = make_frame(0, 0.1)
        other.session_id = "different-session"  # validate_assignment=True, still just a str
        with pytest.raises(ValueError):
            buf.push(other)

    def test_clear_empties_but_keeps_total(self) -> None:
        buf = FrameBuffer(session_id=SESSION, capacity=5)
        buf.push(make_frame(0, 0.1))
        buf.clear()
        assert len(buf) == 0
        assert buf.total_processed == 1

    def test_buffered_carries_image_bytes(self) -> None:
        buf = FrameBuffer(session_id=SESSION, capacity=5)
        buf.push(make_frame(0, 0.1), image_bytes=b"jpeg-bytes")
        assert buf.buffered[0].image_bytes == b"jpeg-bytes"
        assert buf.frames[0].frame_index == 0


# --------------------------------------------------------------------------
# RollingScoreEngine — bands and INSUFFICIENT_DATA
# --------------------------------------------------------------------------


class TestRollingScoreBands:
    def test_insufficient_data_below_min_frames(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=3)
        engine = RollingScoreEngine(SESSION, config=cfg)

        state = engine.push(make_frame(0, probability_fake=0.9))  # authenticity 0.1
        assert state.risk_state == LiveRiskState.INSUFFICIENT_DATA
        assert state.alert_triggered is False
        assert state.frames_in_buffer == 1

        state = engine.push(make_frame(1, probability_fake=0.9))
        assert state.risk_state == LiveRiskState.INSUFFICIENT_DATA

    def test_ok_band_above_watch_threshold(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1)
        engine = RollingScoreEngine(SESSION, config=cfg)
        state = engine.push(make_frame(0, probability_fake=0.05))  # authenticity 0.95
        assert state.risk_state == LiveRiskState.OK

    def test_watch_band_between_thresholds(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, high_risk_threshold=0.35, watch_threshold=0.55)
        engine = RollingScoreEngine(SESSION, config=cfg)
        state = engine.push(make_frame(0, probability_fake=0.55))  # authenticity 0.45
        assert state.risk_state == LiveRiskState.WATCH

    def test_high_risk_below_threshold(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, high_risk_threshold=0.35)
        engine = RollingScoreEngine(SESSION, config=cfg)
        state = engine.push(make_frame(0, probability_fake=0.9))  # authenticity 0.1
        assert state.risk_state == LiveRiskState.HIGH_RISK

    def test_rolling_average_smooths_a_single_bad_frame(self) -> None:
        """Scope 6.16: distinguish one bad frame from a sustained trend."""
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=5, high_risk_threshold=0.35)
        engine = RollingScoreEngine(SESSION, config=cfg)
        # Four confidently-real frames, one spurious near-zero-authenticity frame.
        for i in range(4):
            state = engine.push(make_frame(i, probability_fake=0.05))
        state = engine.push(make_frame(4, probability_fake=0.99))
        # Mean authenticity ~= (4*0.95 + 0.01) / 5 ~= 0.762 — well above HIGH_RISK.
        assert state.risk_state != LiveRiskState.HIGH_RISK
        assert state.rolling_authenticity == pytest.approx(0.762, abs=1e-3)


# --------------------------------------------------------------------------
# RollingScoreEngine — alert transitions and hysteresis
# --------------------------------------------------------------------------


class TestAlertTransitionAndHysteresis:
    def test_alert_fires_only_on_transition_into_high_risk(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=1, high_risk_threshold=0.35)
        engine = RollingScoreEngine(SESSION, config=cfg)

        first = engine.push(make_frame(0, probability_fake=0.95))
        assert first.risk_state == LiveRiskState.HIGH_RISK
        assert first.alert_triggered is True

        second = engine.push(make_frame(1, probability_fake=0.95))
        assert second.risk_state == LiveRiskState.HIGH_RISK
        assert second.alert_triggered is False  # persists, does not re-fire

    def test_hysteresis_prevents_flap_near_the_threshold(self) -> None:
        cfg = LiveConfig(
            min_frames_for_verdict=1,
            buffer_size=1,
            high_risk_threshold=0.35,
            watch_threshold=0.55,
            hysteresis=0.05,
        )
        engine = RollingScoreEngine(SESSION, config=cfg)

        # Drop into HIGH_RISK.
        state = engine.push(make_frame(0, probability_fake=0.90))  # authenticity 0.10
        assert state.risk_state == LiveRiskState.HIGH_RISK

        # Recover to just above the bare threshold (0.36) but still inside the
        # hysteresis band (< 0.35 + 0.05 = 0.40) — must NOT clear yet.
        state = engine.push(make_frame(1, probability_fake=0.64))  # authenticity 0.36
        assert state.risk_state == LiveRiskState.HIGH_RISK
        assert state.alert_triggered is False

        # Recover past the hysteresis band entirely — now it may clear.
        state = engine.push(make_frame(2, probability_fake=0.10))  # authenticity 0.90
        assert state.risk_state != LiveRiskState.HIGH_RISK

    def test_re_entering_high_risk_after_clearing_fires_again(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=1, high_risk_threshold=0.35)
        engine = RollingScoreEngine(SESSION, config=cfg)

        first = engine.push(make_frame(0, probability_fake=0.95))
        assert first.alert_triggered is True

        recovered = engine.push(make_frame(1, probability_fake=0.05))
        assert recovered.risk_state != LiveRiskState.HIGH_RISK

        again = engine.push(make_frame(2, probability_fake=0.95))
        assert again.risk_state == LiveRiskState.HIGH_RISK
        assert again.alert_triggered is True

    def test_reset_clears_buffer_and_forgets_state(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=1, high_risk_threshold=0.35)
        engine = RollingScoreEngine(SESSION, config=cfg)
        engine.push(make_frame(0, probability_fake=0.95))
        engine.reset()
        assert len(engine.buffer) == 0

        state = engine.push(make_frame(1, probability_fake=0.95))
        assert state.alert_triggered is True  # fires again — state was forgotten


# --------------------------------------------------------------------------
# RollingScoreEngine — quality downweighting
# --------------------------------------------------------------------------


class TestQualityDownweighting:
    def test_low_quality_frame_is_downweighted_not_dropped(self) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=2, downweight_low_quality=0.5)
        engine = RollingScoreEngine(SESSION, config=cfg)
        engine.push(make_frame(0, probability_fake=0.0))  # authenticity 1.0, full weight
        state = engine.push(
            make_frame(1, probability_fake=1.0, quality_ok=False)
        )  # authenticity 0.0, half weight
        # weighted mean = (1.0*1.0 + 0.0*0.5) / (1.0 + 0.5) = 0.667
        assert state.rolling_authenticity == pytest.approx(2 / 3, abs=1e-6)


# --------------------------------------------------------------------------
# Evidence capture
# --------------------------------------------------------------------------


class TestEvidenceCapture:
    def test_no_snapshots_saved_without_image_bytes(self, tmp_path: Path) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=1, high_risk_threshold=0.35)
        paths = PathConfig(root=tmp_path, outputs=tmp_path / "outputs")
        engine = RollingScoreEngine(SESSION, config=cfg, paths=paths)

        state = engine.push(make_frame(0, probability_fake=0.95))
        assert state.alert_triggered is True
        assert state.evidence_paths == []
        assert not (tmp_path / "outputs").exists()

    def test_snapshots_saved_on_alert_when_bytes_provided(self, tmp_path: Path) -> None:
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=2, high_risk_threshold=0.35)
        paths = PathConfig(root=tmp_path, outputs=tmp_path / "outputs")
        engine = RollingScoreEngine(SESSION, config=cfg, paths=paths)

        engine.push(make_frame(0, probability_fake=0.6), image_bytes=b"frame-0")
        state = engine.push(make_frame(1, probability_fake=0.95), image_bytes=b"frame-1")

        assert state.alert_triggered is True
        assert len(state.evidence_paths) == 2
        for p in state.evidence_paths:
            assert Path(p).exists()
        session_dir = tmp_path / "outputs" / "evidence" / SESSION
        assert sorted(p.name for p in session_dir.iterdir()) == [
            "frame_000000.jpg",
            "frame_000001.jpg",
        ]

    def test_no_snapshots_when_evidence_disabled(self, tmp_path: Path) -> None:
        cfg = LiveConfig(
            min_frames_for_verdict=1,
            buffer_size=1,
            high_risk_threshold=0.35,
            save_evidence_on_alert=False,
        )
        paths = PathConfig(root=tmp_path, outputs=tmp_path / "outputs")
        engine = RollingScoreEngine(SESSION, config=cfg, paths=paths)

        state = engine.push(make_frame(0, probability_fake=0.95), image_bytes=b"frame-0")
        assert state.alert_triggered is True
        assert state.evidence_paths == []

    def test_no_snapshots_saved_while_high_risk_persists(self, tmp_path: Path) -> None:
        """Evidence captures the transition, not every subsequent HIGH_RISK frame."""
        cfg = LiveConfig(min_frames_for_verdict=1, buffer_size=1, high_risk_threshold=0.35)
        paths = PathConfig(root=tmp_path, outputs=tmp_path / "outputs")
        engine = RollingScoreEngine(SESSION, config=cfg, paths=paths)

        engine.push(make_frame(0, probability_fake=0.95), image_bytes=b"frame-0")
        state = engine.push(make_frame(1, probability_fake=0.95), image_bytes=b"frame-1")
        assert state.alert_triggered is False
        assert state.evidence_paths == []
