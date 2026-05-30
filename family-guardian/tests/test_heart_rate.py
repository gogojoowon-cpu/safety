"""Tests for the rPPG heart-rate estimator.

실제 환경에서는 ±10~15 BPM 오차가 정상이므로, 본 테스트는 합성 신호로 큰 흐름만
검증한다. 또한 얼굴 랜드마크가 없을 때 None 을 돌려주는지도 본다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.heart_rate_detector as hr_module  # noqa: E402
from core.heart_rate_detector import HeartRateDetector  # noqa: E402
from core.pose_detector import PoseFrame  # noqa: E402


FRAME_H, FRAME_W = 240, 320


def synth_hr_frame(bpm: float, t: float) -> np.ndarray:
    """이마 영역 녹색 채널이 sin 으로 진동하는 합성 프레임."""
    val = 130.0 + 20.0 * math.sin(2.0 * math.pi * (bpm / 60.0) * t)
    val_int = int(np.clip(val, 0, 255))
    frame = np.full((FRAME_H, FRAME_W, 3), 110, dtype=np.uint8)
    frame[:, :, 1] = val_int
    return frame


def _pose_with_face(t: float) -> PoseFrame:
    return PoseFrame(
        nose=(FRAME_W / 2, FRAME_H / 3),
        left_shoulder=(FRAME_W / 2 - 40, FRAME_H / 2),
        right_shoulder=(FRAME_W / 2 + 40, FRAME_H / 2),
        left_hip=(FRAME_W / 2 - 40, FRAME_H * 2 / 3),
        right_hip=(FRAME_W / 2 + 40, FRAME_H * 2 / 3),
        visibility_ok=True,
        timestamp=t,
        left_eye=(FRAME_W / 2 - 20, FRAME_H / 3 - 5),
        right_eye=(FRAME_W / 2 + 20, FRAME_H / 3 - 5),
        face_visibility_ok=True,
    )


def _pose_without_face(t: float) -> PoseFrame:
    return PoseFrame(
        nose=(FRAME_W / 2, FRAME_H / 3),
        left_shoulder=(FRAME_W / 2 - 40, FRAME_H / 2),
        right_shoulder=(FRAME_W / 2 + 40, FRAME_H / 2),
        left_hip=(FRAME_W / 2 - 40, FRAME_H * 2 / 3),
        right_hip=(FRAME_W / 2 + 40, FRAME_H * 2 / 3),
        visibility_ok=True,
        timestamp=t,
        left_eye=None,
        right_eye=None,
        face_visibility_ok=False,
    )


class _FakeTime:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t


def test_estimates_hr_close_to_truth(monkeypatch):
    fake = _FakeTime()
    monkeypatch.setattr(hr_module, "time", fake)

    detector = HeartRateDetector()
    target_bpm = 75.0
    dt = 1.0 / 15.0  # 15 Hz sampling
    duration = 12.0
    n = int(duration / dt)

    last = None
    for i in range(n):
        fake.t = i * dt
        frame = synth_hr_frame(target_bpm, fake.t)
        last = detector.update(frame, _pose_with_face(fake.t))

    assert last is not None
    assert last.bpm is not None, f"expected a bpm estimate, got {last}"
    assert abs(last.bpm - target_bpm) <= 15.0, f"bpm={last.bpm}"
    assert last.roi is not None


def test_returns_none_without_face(monkeypatch):
    fake = _FakeTime()
    monkeypatch.setattr(hr_module, "time", fake)

    detector = HeartRateDetector()
    for i in range(60):
        fake.t = i * 0.1
        frame = synth_hr_frame(75.0, fake.t)
        result = detector.update(frame, _pose_without_face(fake.t))

    assert result.bpm is None
    assert result.confidence == 0.0
    assert result.roi is None
