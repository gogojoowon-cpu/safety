"""Tests for the cardiac emergency suspicion detector."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from core.activity_classifier import Activity  # noqa: E402
from core.cardiac_emergency_detector import (  # noqa: E402
    CardiacEmergencyDetector,
    CardiacState,
)


def _quiet(now, apnea=True, activity=Activity.LYING):
    return dict(motion_magnitude=0.0, apnea_suspected=apnea, activity=activity, now=now)


def _moving(now):
    return dict(
        motion_magnitude=10.0, apnea_suspected=False,
        activity=Activity.STANDING, now=now,
    )


def test_movement_keeps_state_normal():
    det = CardiacEmergencyDetector()
    for t in range(0, 120, 5):
        res = det.update(**_moving(float(t)))
        assert res.state == CardiacState.NORMAL
        assert res.alert is None


def test_apnea_alone_does_not_fire():
    """Apnea + breathing flag but person is still moving / standing → ignore."""
    det = CardiacEmergencyDetector()
    for t in range(0, 90, 3):
        res = det.update(
            motion_magnitude=8.0,  # above threshold
            apnea_suspected=True,
            activity=Activity.STANDING,
            now=float(t),
        )
        assert res.state == CardiacState.NORMAL
        assert res.alert is None


def test_full_chain_fires_emergency():
    det = CardiacEmergencyDetector()
    # Start at t=0 immobile + apnea + lying
    det.update(**_quiet(0.0))
    # Cross the immobility threshold
    cross = config.CARDIAC_IMMOBILITY_SEC + 1.0
    suspected = det.update(**_quiet(cross))
    assert suspected.state == CardiacState.SUSPECTED
    assert suspected.alert is None

    # Hold suspicion long enough to confirm
    confirm_at = cross + config.CARDIAC_CONFIRMATION_SEC + 1.0
    emergency = det.update(**_quiet(confirm_at))
    assert emergency.state == CardiacState.EMERGENCY
    assert emergency.alert is not None
    assert "응급 의심" in emergency.alert


def test_motion_clears_suspicion():
    det = CardiacEmergencyDetector()
    det.update(**_quiet(0.0))
    det.update(**_quiet(config.CARDIAC_IMMOBILITY_SEC + 1.0))
    # Motion above threshold → state must reset
    res = det.update(**_moving(config.CARDIAC_IMMOBILITY_SEC + 2.0))
    assert res.state == CardiacState.NORMAL


def test_activity_standing_blocks_emergency_even_with_apnea():
    """If pose says STANDING (not lying or unknown), suppress cardiac suspicion
    regardless of breathing — apnea on a standing person is more likely a
    rPPG mis-read than a collapse."""
    det = CardiacEmergencyDetector()
    cross = config.CARDIAC_IMMOBILITY_SEC + 1.0
    confirm_at = cross + config.CARDIAC_CONFIRMATION_SEC + 1.0
    det.update(motion_magnitude=0.0, apnea_suspected=True,
               activity=Activity.STANDING, now=0.0)
    det.update(motion_magnitude=0.0, apnea_suspected=True,
               activity=Activity.STANDING, now=cross)
    final = det.update(motion_magnitude=0.0, apnea_suspected=True,
                       activity=Activity.STANDING, now=confirm_at)
    assert final.state == CardiacState.NORMAL
    assert final.alert is None


def test_cooldown_blocks_repeat_alert():
    det = CardiacEmergencyDetector()
    det.update(**_quiet(0.0))
    cross = config.CARDIAC_IMMOBILITY_SEC + 1.0
    confirm_at = cross + config.CARDIAC_CONFIRMATION_SEC + 1.0
    det.update(**_quiet(cross))
    first = det.update(**_quiet(confirm_at))
    assert first.alert is not None

    # Still meeting criteria a little later — cooldown should suppress
    second = det.update(**_quiet(confirm_at + 30.0))
    assert second.alert is None
