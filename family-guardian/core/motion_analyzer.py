"""Frame-difference based motion analyzer.

자세 인식이 실패해도 ("가림, 어둠, 옷의 모양 등") 동작하는 기초 신호. 그레이스케일
다운샘플 프레임의 절대 차분 평균(0~255 단위)을 모션 강도로 노출한다.

이 값은 ``CardiacEmergencyDetector`` / ``InactivityDetector`` 가 임계값 비교에
쓴다.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

import config


class MotionAnalyzer:
    def __init__(self) -> None:
        self._prev: Optional[np.ndarray] = None

    def update(self, frame_bgr: np.ndarray) -> float:
        if frame_bgr is None or frame_bgr.size == 0:
            return 0.0
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(
            gray,
            (config.MOTION_DOWNSAMPLE_W, config.MOTION_DOWNSAMPLE_H),
            interpolation=cv2.INTER_AREA,
        )
        if self._prev is None:
            self._prev = small
            return 0.0
        diff = cv2.absdiff(small, self._prev)
        self._prev = small
        return float(diff.mean())

    def reset(self) -> None:
        self._prev = None
