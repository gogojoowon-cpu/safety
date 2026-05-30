"""Tests for the prolonged-inactivity detector."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from core.inactivity_detector import InactivityDetector  # noqa: E402


def test_movement_keeps_quiet_clock_reset():
    det = InactivityDetector()
    for t in range(0, 100):
        res = det.update(motion_magnitude=2.0, now=float(t))
        assert res.alert is None
        assert res.quiet_seconds == 0.0


def test_no_alert_before_threshold():
    det = InactivityDetector()
    det.update(motion_magnitude=0.0, now=0.0)
    short = config.INACTIVITY_THRESHOLD_MIN * 60.0 - 10.0
    res = det.update(motion_magnitude=0.0, now=short)
    assert res.alert is None


def test_alert_fires_after_threshold():
    det = InactivityDetector()
    det.update(motion_magnitude=0.0, now=0.0)
    just_past = config.INACTIVITY_THRESHOLD_MIN * 60.0 + 1.0
    res = det.update(motion_magnitude=0.0, now=just_past)
    assert res.alert is not None
    assert "장시간 미동 감지" in res.alert


def test_cooldown_blocks_repeat():
    det = InactivityDetector()
    det.update(motion_magnitude=0.0, now=0.0)
    just_past = config.INACTIVITY_THRESHOLD_MIN * 60.0 + 1.0
    first = det.update(motion_magnitude=0.0, now=just_past)
    assert first.alert is not None
    # Still quiet, just a few seconds later → no repeat
    second = det.update(motion_magnitude=0.0, now=just_past + 30.0)
    assert second.alert is None


def test_motion_resets_quiet_clock():
    det = InactivityDetector()
    det.update(motion_magnitude=0.0, now=0.0)
    det.update(motion_magnitude=0.0, now=100.0)
    # Significant motion at t=200 should reset the clock
    bump = det.update(motion_magnitude=5.0, now=200.0)
    assert bump.quiet_seconds == 0.0
    # And we shouldn't fire even though >threshold seconds since *start*
    later = det.update(
        motion_magnitude=0.0,
        now=200.0 + config.INACTIVITY_THRESHOLD_MIN * 60.0 - 10.0,
    )
    assert later.alert is None
