"""Camera-based cardiac emergency suspicion.

⚠️ 의료 진단 아님. 진짜 심정지 판정은 ECG/맥박 측정 없이 카메라만으로는 불가능.
본 모듈은 다음 신호가 동시에 만족될 때 "응급 의심" 알림을 격상하는 **screening**
이다 — false positive 가 와도 비용은 "확인 1회", 놓치면 사망이므로 recall 우선.

판정 조건 (모두 동시 만족):
  1. 모션 강도 < ``MOTION_QUIET_THRESHOLD`` 가 ``CARDIAC_IMMOBILITY_SEC`` 이상 지속
  2. ``BreathingDetector`` 의 ``apnea_suspected = True``
  3. 자세가 LYING 또는 자세 인식 실패 (collapsed 상태)

위 3 조건이 ``CARDIAC_CONFIRMATION_SEC`` 동안 유지되면 EMERGENCY 로 전이하고
알림 발화. 그 후 ``CARDIAC_ALERT_COOLDOWN_SEC`` 동안 중복 발화 차단.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import config
from core.activity_classifier import Activity
from core.logger import get_logger

log = get_logger(__name__)


class CardiacState(str, Enum):
    NORMAL = "NORMAL"
    SUSPECTED = "SUSPECTED"
    EMERGENCY = "EMERGENCY"


@dataclass
class CardiacResult:
    state: CardiacState
    immobile_seconds: float
    apnea: bool
    activity: Activity
    alert: Optional[str]


class CardiacEmergencyDetector:
    def __init__(self) -> None:
        self._state: CardiacState = CardiacState.NORMAL
        self._immobile_since: Optional[float] = None
        self._suspected_since: Optional[float] = None
        self._last_alert_at: float = -math.inf

    def update(
        self,
        motion_magnitude: float,
        apnea_suspected: bool,
        activity: Activity,
        now: float,
    ) -> CardiacResult:
        # 1) Track immobility timestamp
        if motion_magnitude >= config.MOTION_QUIET_THRESHOLD:
            self._immobile_since = None
            if self._state != CardiacState.NORMAL:
                log.info("Cardiac suspicion cleared (motion %.2f detected)", motion_magnitude)
            self._state = CardiacState.NORMAL
            self._suspected_since = None
            return CardiacResult(
                state=CardiacState.NORMAL, immobile_seconds=0.0,
                apnea=apnea_suspected, activity=activity, alert=None,
            )

        if self._immobile_since is None:
            self._immobile_since = now
        immobile_for = now - self._immobile_since

        # 2) Collapsed posture or pose lost?
        collapsed = activity in (Activity.LYING, Activity.UNKNOWN)

        # 3) All three criteria together?
        meets_criteria = (
            immobile_for >= config.CARDIAC_IMMOBILITY_SEC
            and apnea_suspected
            and collapsed
        )

        if not meets_criteria:
            if self._state == CardiacState.SUSPECTED:
                log.info("Cardiac suspicion downgraded (criteria no longer met)")
            self._state = CardiacState.NORMAL
            self._suspected_since = None
            return CardiacResult(
                state=CardiacState.NORMAL, immobile_seconds=immobile_for,
                apnea=apnea_suspected, activity=activity, alert=None,
            )

        # Criteria met — start or progress suspicion clock
        if self._suspected_since is None:
            self._suspected_since = now
            self._state = CardiacState.SUSPECTED
            log.warning(
                "Cardiac SUSPECTED (immobile %.0fs, apnea=True, activity=%s)",
                immobile_for, activity.value,
            )

        sustained = now - self._suspected_since
        alert: Optional[str] = None
        if sustained >= config.CARDIAC_CONFIRMATION_SEC:
            self._state = CardiacState.EMERGENCY
            if now - self._last_alert_at >= config.CARDIAC_ALERT_COOLDOWN_SEC:
                self._last_alert_at = now
                ts = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
                alert = (
                    f"🆘 응급 의심 ({ts}) — 호흡 신호 없음 + {immobile_for:.0f}초 미동 + "
                    f"자세 {activity.value}.\n"
                    "심정지 가능성을 배제할 수 없습니다. 즉시 확인 후 필요 시 119 신고하세요."
                )
                log.error("Cardiac EMERGENCY alert fired (sustained=%.0fs)", sustained)

        return CardiacResult(
            state=self._state, immobile_seconds=immobile_for,
            apnea=apnea_suspected, activity=activity, alert=alert,
        )
