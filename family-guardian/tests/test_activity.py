"""Tests for the activity classifier."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.activity_classifier import Activity, classify  # noqa: E402
from core.pose_detector import PoseFrame  # noqa: E402


def _pose(torso_horizontal: bool, visible: bool = True) -> PoseFrame:
    if torso_horizontal:
        ls, rs = (200.0, 200.0), (260.0, 200.0)
        lh, rh = (400.0, 205.0), (460.0, 205.0)
    else:
        ls, rs = (300.0, 200.0), (340.0, 200.0)
        lh, rh = (305.0, 380.0), (335.0, 380.0)
    return PoseFrame(
        nose=(320.0, 100.0),
        left_shoulder=ls, right_shoulder=rs,
        left_hip=lh, right_hip=rh,
        visibility_ok=visible, timestamp=0.0,
    )


def _sitting_pose() -> PoseFrame:
    # torso angle around 45 degrees
    return PoseFrame(
        nose=(320.0, 100.0),
        left_shoulder=(280.0, 200.0), right_shoulder=(340.0, 200.0),
        left_hip=(370.0, 260.0), right_hip=(430.0, 260.0),
        visibility_ok=True, timestamp=0.0,
    )


def test_classify_standing():
    assert classify(_pose(torso_horizontal=False)) == Activity.STANDING


def test_classify_lying():
    assert classify(_pose(torso_horizontal=True)) == Activity.LYING


def test_classify_sitting():
    assert classify(_sitting_pose()) == Activity.SITTING


def test_classify_unknown_when_no_pose():
    assert classify(None) == Activity.UNKNOWN


def test_classify_unknown_when_visibility_bad():
    assert classify(_pose(torso_horizontal=False, visible=False)) == Activity.UNKNOWN
