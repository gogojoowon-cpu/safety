"""Fixed-capacity ring buffer for BGR frames + timestamps.

영상은 OpenCV 가 내부 버퍼를 재사용하므로 ``push`` 시 반드시 ``frame.copy()`` 한다.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List

import numpy as np


@dataclass
class TimedFrame:
    frame_bgr: np.ndarray
    timestamp: float


class FrameRingBuffer:
    def __init__(self, seconds: float, fps: int) -> None:
        self.seconds = float(seconds)
        self.fps = int(fps) if fps > 0 else 1
        self.capacity = max(1, int(self.seconds * self.fps))
        self._buf: Deque[TimedFrame] = deque(maxlen=self.capacity)

    def push(self, frame_bgr: np.ndarray, timestamp: float) -> None:
        # OpenCV reuses the underlying buffer; copy or our snapshot would change.
        self._buf.append(TimedFrame(frame_bgr=frame_bgr.copy(), timestamp=timestamp))

    def snapshot(self) -> List[TimedFrame]:
        return list(self._buf)

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)
