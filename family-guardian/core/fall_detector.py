"""Rule-based fall detector.

상태머신:
- NORMAL → SUSPECTED_FALL : 머리(nose) y 좌표가 HEAD_DROP_WINDOW_SEC 내에
  ``HEAD_DROP_RATIO * frame_height`` 이상 하강하고 동시에 몸통이 수평에 가까움.
- SUSPECTED_FALL → CONFIRMED_FALL : SUSPECTED 진입 후 IMMOBILE_AFTER_FALL_SEC 이상
  경과했고, 직전 1초 동안 어깨중점의 평균 이동량이 IMMOBILE_PIXEL_THRESHOLD 미만.
- SUSPECTED_FALL / CONFIRMED_FALL → NORMAL : 몸통 각도가 임계값 + 15도 초과
  (다시 일어선 것으로 간주).

알림 메시지는 CONFIRMED 진입 시 1회만 반환되며, ALERT_COOLDOWN_SEC 동안은
재발화하지 않는다.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

import config
from core.event_state import PoseHistory, State
from core.logger import get_logger
from core.pose_detector import PoseFrame

log = get_logger(__name__)


class FallDetector:
    def __init__(self, frame_height: int = None) -> None:
        self.frame_height = int(frame_height) if frame_height else int(config.FRAME_HEIGHT)
        self.state: State = State.NORMAL
        self.history = PoseHistory(maxlen=512)
        self._suspected_at: Optional[float] = None
        self._last_alert_at: float = -math.inf

    def update(self, frame: Optional[PoseFrame]) -> Optional[str]:
        """Push frame, evaluate transitions, return alert message on CONFIRMED."""
        if frame is None or not frame.visibility_ok:
            return None

        self.history.push(frame)
        now = frame.timestamp
        torso = frame.torso_angle_deg()
        recovery_angle = config.TORSO_HORIZONTAL_THRESHOLD_DEG + 15.0

        if self.state in (State.SUSPECTED_FALL, State.CONFIRMED_FALL):
            if torso > recovery_angle:
                log.info("Fall state cleared (torso=%.1f deg)", torso)
                self.state = State.NORMAL
                self._suspected_at = None
                return None

        if self.state == State.NORMAL:
            if self._detect_head_drop(now) and torso < config.TORSO_HORIZONTAL_THRESHOLD_DEG:
                self.state = State.SUSPECTED_FALL
                self._suspected_at = now
                log.warning("Suspected fall (torso=%.1f deg)", torso)
            return None

        if self.state == State.SUSPECTED_FALL:
            assert self._suspected_at is not None
            elapsed = now - self._suspected_at
            if elapsed >= config.IMMOBILE_AFTER_FALL_SEC and self._is_immobile(now):
                self.state = State.CONFIRMED_FALL
                log.error("Confirmed fall after %.1fs immobility", elapsed)
                if now - self._last_alert_at >= config.ALERT_COOLDOWN_SEC:
                    self._last_alert_at = now
                    return self._build_message(now)
            return None

        return None

    def _detect_head_drop(self, now: float) -> bool:
        frames = self.history.frames_within(config.HEAD_DROP_WINDOW_SEC, now)
        if len(frames) < 2:
            return False
        nose_ys = [f.nose[1] for f in frames]
        drop = nose_ys[-1] - min(nose_ys)
        threshold = config.HEAD_DROP_RATIO * self.frame_height
        return drop >= threshold

    def _is_immobile(self, now: float) -> bool:
        frames = self.history.frames_within(1.0, now)
        if len(frames) < 2:
            return False
        movements = []
        for prev, curr in zip(frames, frames[1:]):
            px, py = prev.shoulder_mid
            cx, cy = curr.shoulder_mid
            movements.append(math.hypot(cx - px, cy - py))
        avg = sum(movements) / len(movements)
        return avg < config.IMMOBILE_PIXEL_THRESHOLD

    @staticmethod
    def _build_message(now: float) -> str:
        ts = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"🚨 낙상 감지 ({ts}) — 상태: CONFIRMED_FALL.\n"
            "대상자가 쓰러진 후 일정 시간 움직임이 없습니다. 즉시 확인해 주세요."
        )
