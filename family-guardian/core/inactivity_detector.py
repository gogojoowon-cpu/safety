"""Long-term inactivity detector.

빠른 낙상 시퀀스가 아닌, "장시간 미동" 형태의 비상 상황 (의식 잃음, 깨지 못함,
침대에서 못 일어남) 을 잡는다. 모션 분석기의 강도가 ``MOTION_QUIET_THRESHOLD``
미만인 상태가 ``INACTIVITY_THRESHOLD_MIN`` 분 동안 유지되면 알림.

알림 후 ``INACTIVITY_ALERT_COOLDOWN_SEC`` (5분) 동안은 중복 발화 방지.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import config
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class InactivityResult:
    quiet_seconds: float
    threshold_seconds: float
    alert: Optional[str]


class InactivityDetector:
    def __init__(self) -> None:
        self._quiet_since: Optional[float] = None
        self._last_alert_at: float = -math.inf

    def update(self, motion_magnitude: float, now: float) -> InactivityResult:
        threshold_sec = config.INACTIVITY_THRESHOLD_MIN * 60.0

        is_quiet = motion_magnitude < config.MOTION_QUIET_THRESHOLD
        if not is_quiet:
            self._quiet_since = None
            return InactivityResult(quiet_seconds=0.0, threshold_seconds=threshold_sec, alert=None)

        if self._quiet_since is None:
            self._quiet_since = now
            return InactivityResult(quiet_seconds=0.0, threshold_seconds=threshold_sec, alert=None)

        quiet_for = now - self._quiet_since
        alert: Optional[str] = None
        if quiet_for >= threshold_sec and (now - self._last_alert_at) >= config.INACTIVITY_ALERT_COOLDOWN_SEC:
            self._last_alert_at = now
            minutes = quiet_for / 60.0
            ts = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
            alert = (
                f"⏰ 장시간 미동 감지 ({ts}) — {minutes:.0f}분간 큰 움직임이 없습니다.\n"
                "낮 시간대 평소와 다르다면 직접 확인이 필요합니다."
            )
            log.warning("Inactivity alert (%.0fs quiet)", quiet_for)

        return InactivityResult(quiet_seconds=quiet_for, threshold_seconds=threshold_sec, alert=alert)
