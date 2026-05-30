"""Tests for the frame-difference motion analyzer."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.motion_analyzer import MotionAnalyzer  # noqa: E402


def _frame(value: int, shape=(240, 320, 3)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint8)


def test_first_frame_returns_zero():
    m = MotionAnalyzer()
    assert m.update(_frame(100)) == 0.0


def test_identical_frames_have_no_motion():
    m = MotionAnalyzer()
    m.update(_frame(100))
    assert m.update(_frame(100)) == 0.0
    assert m.update(_frame(100)) == 0.0


def test_changing_frames_have_motion():
    m = MotionAnalyzer()
    m.update(_frame(100))
    mag = m.update(_frame(180))
    # Big intensity change → big average diff
    assert mag > 50.0


def test_reset_clears_history():
    m = MotionAnalyzer()
    m.update(_frame(100))
    m.reset()
    # First frame after reset must again return zero.
    assert m.update(_frame(200)) == 0.0
