"""MediaPipe Pose wrapper.

순수 데이터 구조 ``PoseFrame`` 과 카메라 의존 wrapper ``PoseDetector`` 를 분리해서,
테스트는 ``PoseFrame`` 만 합성해 돌릴 수 있도록 한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

Point = Tuple[float, float]


@dataclass
class PoseFrame:
    """단일 프레임에서 뽑은 키포인트.

    좌표는 픽셀 단위. ``visibility_ok=False`` 면 다운스트림은 이 프레임을 무시한다.
    """
    nose: Point
    left_shoulder: Point
    right_shoulder: Point
    left_hip: Point
    right_hip: Point
    visibility_ok: bool
    timestamp: float

    @property
    def shoulder_mid(self) -> Point:
        return (
            (self.left_shoulder[0] + self.right_shoulder[0]) / 2.0,
            (self.left_shoulder[1] + self.right_shoulder[1]) / 2.0,
        )

    @property
    def hip_mid(self) -> Point:
        return (
            (self.left_hip[0] + self.right_hip[0]) / 2.0,
            (self.left_hip[1] + self.right_hip[1]) / 2.0,
        )

    def torso_angle_deg(self) -> float:
        """어깨중점→엉덩이중점 벡터가 수평선과 이루는 각도.

        90도면 직립, 0도면 수평. 영상 좌표계에서 y 축은 아래로 증가하므로
        절대값을 취해 단방향으로 환산한다.
        """
        sx, sy = self.shoulder_mid
        hx, hy = self.hip_mid
        dx = hx - sx
        dy = hy - sy
        if dx == 0 and dy == 0:
            return 90.0
        angle = math.degrees(math.atan2(abs(dy), abs(dx)))
        return angle


class PoseDetector:
    """MediaPipe Pose 인스턴스 wrapper.

    mediapipe 패키지가 없거나 import 가 실패해도 데모 코드를 깨뜨리지 않도록
    `lazy import` 처리한다.
    """

    _MIN_VISIBILITY = 0.5

    def __init__(self, model_complexity: int = 1) -> None:
        from mediapipe.python.solutions import pose as mp_pose  # type: ignore

        self._mp_pose = mp_pose
        self._pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def process(self, frame_rgb, timestamp: float) -> Optional[PoseFrame]:
        """RGB 프레임에서 PoseFrame 추출. landmark 부족 시 None."""
        result = self._pose.process(frame_rgb)
        if not result.pose_landmarks:
            return None

        lm = result.pose_landmarks.landmark
        h, w = frame_rgb.shape[:2]
        LM = self._mp_pose.PoseLandmark

        def pt(idx: int) -> Point:
            p = lm[idx]
            return (p.x * w, p.y * h)

        def vis(idx: int) -> float:
            return lm[idx].visibility

        key_indices = [
            LM.NOSE,
            LM.LEFT_SHOULDER,
            LM.RIGHT_SHOULDER,
            LM.LEFT_HIP,
            LM.RIGHT_HIP,
        ]
        visibility_ok = all(vis(i) > self._MIN_VISIBILITY for i in key_indices)

        return PoseFrame(
            nose=pt(LM.NOSE),
            left_shoulder=pt(LM.LEFT_SHOULDER),
            right_shoulder=pt(LM.RIGHT_SHOULDER),
            left_hip=pt(LM.LEFT_HIP),
            right_hip=pt(LM.RIGHT_HIP),
            visibility_ok=visibility_ok,
            timestamp=timestamp,
        )

    def close(self) -> None:
        try:
            self._pose.close()
        except Exception:  # noqa: BLE001
            # MediaPipe occasionally raises during teardown; best-effort cleanup only.
            from core.logger import get_logger
            get_logger(__name__).debug("PoseDetector.close raised; ignoring", exc_info=True)
