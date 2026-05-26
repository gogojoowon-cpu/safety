"""Shared event state primitives for the fall-detection state machine."""
from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Deque, List, Optional

from core.pose_detector import PoseFrame


class State(str, Enum):
    NORMAL = "NORMAL"
    SUSPECTED_FALL = "SUSPECTED_FALL"
    CONFIRMED_FALL = "CONFIRMED_FALL"


class PoseHistory:
    """타임스탬프 기반 짧은 시계열 버퍼.

    낙상 판정에 쓸 최근 ~수 초의 PoseFrame 을 보관한다. 메모리 한도는 ``maxlen``
    으로 고정하고, 시간 윈도우 질의는 ``frames_within`` 으로 한다.
    """

    def __init__(self, maxlen: int = 256) -> None:
        self._buf: Deque[PoseFrame] = deque(maxlen=maxlen)

    def push(self, frame: PoseFrame) -> None:
        self._buf.append(frame)

    def frames_within(self, seconds: float, now: float) -> List[PoseFrame]:
        cutoff = now - seconds
        return [f for f in self._buf if f.timestamp >= cutoff]

    def latest(self) -> Optional[PoseFrame]:
        return self._buf[-1] if self._buf else None

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)
