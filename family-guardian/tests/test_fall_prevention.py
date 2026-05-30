"""Tests for the y-coordinate based fall-prevention detector."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from core.fall_prevention import FallPreventionDetector, Zone  # noqa: E402
from core.pose_detector import PoseFrame  # noqa: E402


FRAME_H = 400  # easier arithmetic: 55% → 220, 70% → 280


def _pose_with_hip_y(hip_y: float, t: float) -> PoseFrame:
    return PoseFrame(
        nose=(200.0, hip_y - 150.0),
        left_shoulder=(170.0, hip_y - 100.0),
        right_shoulder=(230.0, hip_y - 100.0),
        left_hip=(180.0, hip_y),
        right_hip=(220.0, hip_y),
        visibility_ok=True,
        timestamp=t,
    )


def test_safe_when_hip_high():
    det = FallPreventionDetector()
    res = det.update(_pose_with_hip_y(100.0, t=0.0), frame_height=FRAME_H, now=0.0)
    assert res.zone == Zone.SAFE
    assert res.alert is None
    assert abs(res.warning_y - 220.0) < 1.0
    assert abs(res.danger_y - 280.0) < 1.0


def test_warning_band_no_alert():
    det = FallPreventionDetector()
    res = det.update(_pose_with_hip_y(240.0, t=0.0), frame_height=FRAME_H, now=0.0)
    assert res.zone == Zone.WARNING
    assert res.alert is None


def test_danger_entry_fires_alert():
    det = FallPreventionDetector()
    det.update(_pose_with_hip_y(100.0, t=0.0), frame_height=FRAME_H, now=0.0)
    res = det.update(_pose_with_hip_y(320.0, t=1.0), frame_height=FRAME_H, now=1.0)
    assert res.zone == Zone.DANGER
    assert res.alert is not None
    assert "낙상 위험 구역 진입" in res.alert


def test_cooldown_suppresses_repeat_alert():
    det = FallPreventionDetector()
    det.update(_pose_with_hip_y(100.0, t=0.0), frame_height=FRAME_H, now=0.0)
    first = det.update(_pose_with_hip_y(320.0, t=1.0), frame_height=FRAME_H, now=1.0)
    assert first.alert is not None

    # Briefly leave the zone and re-enter within the cooldown window
    det.update(_pose_with_hip_y(100.0, t=2.0), frame_height=FRAME_H, now=2.0)
    second = det.update(_pose_with_hip_y(320.0, t=3.0), frame_height=FRAME_H, now=3.0)
    assert second.zone == Zone.DANGER
    assert second.alert is None  # cooldown active


def test_alert_fires_again_after_cooldown():
    det = FallPreventionDetector()
    det.update(_pose_with_hip_y(100.0, t=0.0), frame_height=FRAME_H, now=0.0)
    first = det.update(_pose_with_hip_y(320.0, t=1.0), frame_height=FRAME_H, now=1.0)
    assert first.alert is not None

    det.update(_pose_with_hip_y(100.0, t=2.0), frame_height=FRAME_H, now=2.0)
    later = config.ALERT_COOLDOWN_SEC + 10.0
    second = det.update(_pose_with_hip_y(320.0, t=later), frame_height=FRAME_H, now=later)
    assert second.alert is not None
