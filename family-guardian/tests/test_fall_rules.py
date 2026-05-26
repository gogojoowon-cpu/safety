"""Unit tests for FallDetector state machine.

카메라/MediaPipe 없이 합성 PoseFrame 만으로 상태머신을 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `import config`, `from core...` when running pytest directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.event_state import State  # noqa: E402
from core.fall_detector import FallDetector  # noqa: E402
from core.pose_detector import PoseFrame  # noqa: E402

FRAME_HEIGHT = 480


def make_pose(nose_y: float, torso_horizontal: bool, t: float) -> PoseFrame:
    """Synthetic PoseFrame.

    torso_horizontal=False  → 직립 (어깨 위, 엉덩이 아래)
    torso_horizontal=True   → 수평 (어깨와 엉덩이 거의 같은 높이, 좌우로 떨어짐)
    """
    if torso_horizontal:
        left_shoulder = (200.0, nose_y + 40.0)
        right_shoulder = (260.0, nose_y + 40.0)
        left_hip = (400.0, nose_y + 45.0)
        right_hip = (460.0, nose_y + 45.0)
    else:
        left_shoulder = (300.0, nose_y + 40.0)
        right_shoulder = (340.0, nose_y + 40.0)
        left_hip = (305.0, nose_y + 200.0)
        right_hip = (335.0, nose_y + 200.0)
    return PoseFrame(
        nose=(320.0, nose_y),
        left_shoulder=left_shoulder,
        right_shoulder=right_shoulder,
        left_hip=left_hip,
        right_hip=right_hip,
        visibility_ok=True,
        timestamp=t,
    )


def test_normal_no_alert():
    detector = FallDetector(frame_height=FRAME_HEIGHT)
    for i in range(30):
        msg = detector.update(make_pose(nose_y=100.0, torso_horizontal=False, t=i * 0.1))
        assert msg is None
    assert detector.state == State.NORMAL


def test_fall_then_immobile(monkeypatch):
    detector = FallDetector(frame_height=FRAME_HEIGHT)

    # 1) Upright baseline: 1 second at nose_y = 80
    t = 0.0
    for _ in range(10):
        assert detector.update(make_pose(80.0, torso_horizontal=False, t=t)) is None
        t += 0.1

    # 2) Sudden drop + horizontal torso → SUSPECTED
    fall_msg = detector.update(make_pose(nose_y=380.0, torso_horizontal=True, t=t))
    assert fall_msg is None
    assert detector.state == State.SUSPECTED_FALL
    t += 0.1

    # 3) 6 seconds of near-zero movement → CONFIRMED at some point
    confirmed_msg = None
    for _ in range(60):
        msg = detector.update(make_pose(nose_y=380.0, torso_horizontal=True, t=t))
        t += 0.1
        if msg is not None:
            confirmed_msg = msg
            break

    assert detector.state == State.CONFIRMED_FALL
    assert confirmed_msg is not None
    assert "CONFIRMED_FALL" in confirmed_msg
    assert "🚨" in confirmed_msg


def test_recovers_when_standing():
    detector = FallDetector(frame_height=FRAME_HEIGHT)

    t = 0.0
    for _ in range(10):
        detector.update(make_pose(80.0, torso_horizontal=False, t=t))
        t += 0.1

    detector.update(make_pose(nose_y=380.0, torso_horizontal=True, t=t))
    assert detector.state == State.SUSPECTED_FALL
    t += 0.1

    # 일어남 (torso 직립 복귀)
    msg = detector.update(make_pose(nose_y=80.0, torso_horizontal=False, t=t))
    assert msg is None
    assert detector.state == State.NORMAL
