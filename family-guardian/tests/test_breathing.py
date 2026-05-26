"""Tests for the rPPG breathing estimator.

FFT 해상도 한계로 ±5~10 BPM 의 오차는 정상이다. 본 테스트는 합성 신호로
큰 흐름이 맞는지만 검증한다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.breathing_detector as breathing_module  # noqa: E402
from core.breathing_detector import BreathingDetector  # noqa: E402
from core.pose_detector import PoseFrame  # noqa: E402


FRAME_H, FRAME_W = 120, 160


def synth_breathing_frame(bpm: float, t: float) -> np.ndarray:
    """가슴 영역 녹색 채널이 sin 으로 진동하는 합성 프레임."""
    val = 128.0 + 40.0 * math.sin(2.0 * math.pi * (bpm / 60.0) * t)
    val_int = int(np.clip(val, 0, 255))
    frame = np.full((FRAME_H, FRAME_W, 3), 128, dtype=np.uint8)
    frame[:, :, 1] = val_int
    return frame


def _pose(t: float) -> PoseFrame:
    return PoseFrame(
        nose=(FRAME_W / 2, FRAME_H / 4),
        left_shoulder=(FRAME_W / 2 - 20, FRAME_H / 3),
        right_shoulder=(FRAME_W / 2 + 20, FRAME_H / 3),
        left_hip=(FRAME_W / 2 - 20, FRAME_H * 2 / 3),
        right_hip=(FRAME_W / 2 + 20, FRAME_H * 2 / 3),
        visibility_ok=True,
        timestamp=t,
    )


class _FakeTime:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t


def test_estimates_bpm_close_to_truth(monkeypatch):
    fake = _FakeTime()
    monkeypatch.setattr(breathing_module, "time", fake)

    detector = BreathingDetector()
    target_bpm = 40.0
    dt = 0.1
    duration = 12.0
    n = int(duration / dt)

    last = None
    for i in range(n):
        fake.t = i * dt
        frame = synth_breathing_frame(target_bpm, fake.t)
        last = detector.update(frame, _pose(fake.t))

    assert last is not None
    assert last.bpm is not None, f"expected a bpm estimate, got {last}"
    assert abs(last.bpm - target_bpm) <= 10.0, f"bpm={last.bpm}"
