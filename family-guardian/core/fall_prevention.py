"""Fall prevention — y-coordinate based pre-fall warning.

기존 ``FallDetector`` 는 머리가 *떨어진 뒤* + 몸통이 *누운 뒤* 에 SUSPECTED/CONFIRMED
로 전이되는 **사후 감지**기다. 본 모듈은 그 전에 동작하는 **사전 경고**기로,
hip_mid 의 y 좌표가 프레임 하단의 "위험 구역"으로 진입하기 시작하면 보호자에게
미리 알린다.

배치 예시:
- 카메라가 침대 옆에서 비스듬히 바라봄
- WARNING 라인(기본 55%): 침대 가장자리쯤
- DANGER 라인(기본 70%): 침대 밖 바닥쯤
- 어르신이 침대에서 일어서다 미끄러져 hip 이 DANGER 라인 아래로 떨어지면
  실제 낙상 충격이 일어나기 *전에* "낙상 위험 구역 진입" 경고가 발화한다.

라인 위치는 ``config.FALL_PREVENTION_*_Y_RATIO`` 로 조정하거나, 향후 UI 에서
클릭으로 직접 지정할 수 있게 확장 가능하다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import config
from core.logger import get_logger
from core.pose_detector import PoseFrame

log = get_logger(__name__)


class Zone(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    DANGER = "DANGER"


@dataclass
class FallPreventionResult:
    zone: Zone
    hip_y: Optional[float]
    warning_y: float
    danger_y: float
    alert: Optional[str]


class FallPreventionDetector:
    """Watches hip_mid y-coordinate against configurable horizontal danger lines."""

    def __init__(self) -> None:
        self._zone: Zone = Zone.SAFE
        self._last_alert_at: float = -math.inf
        self._frame_height: Optional[int] = None
        self._override_warning_y: Optional[float] = None
        self._override_danger_y: Optional[float] = None

    def set_lines(self, warning_y: float, danger_y: float) -> None:
        """Override the warning / danger y-coordinates explicitly (UI calibration).

        Pass two pixel y-values (image coordinate system, y=0 at top).
        Raises ValueError if the danger line isn't strictly below the warning line.
        """
        if not warning_y < danger_y:
            raise ValueError(
                f"warning_y ({warning_y}) must be strictly less than danger_y ({danger_y})"
            )
        self._override_warning_y = float(warning_y)
        self._override_danger_y = float(danger_y)
        log.info("Fall prevention lines overridden: warning=%.1f danger=%.1f",
                 warning_y, danger_y)

    def clear_overrides(self) -> None:
        self._override_warning_y = None
        self._override_danger_y = None

    def _lines_for(self, frame_height: int) -> tuple[float, float]:
        if self._override_warning_y is not None and self._override_danger_y is not None:
            return self._override_warning_y, self._override_danger_y
        return (
            frame_height * config.FALL_PREVENTION_WARNING_Y_RATIO,
            frame_height * config.FALL_PREVENTION_DANGER_Y_RATIO,
        )

    def update(
        self,
        pose: Optional[PoseFrame],
        frame_height: int,
        now: float,
    ) -> FallPreventionResult:
        if self._frame_height is None or self._frame_height != frame_height:
            self._frame_height = frame_height
        warning_y, danger_y = self._lines_for(frame_height)

        if pose is None or not pose.visibility_ok:
            return FallPreventionResult(
                zone=self._zone, hip_y=None,
                warning_y=warning_y, danger_y=danger_y, alert=None,
            )

        hip_y = pose.hip_mid[1]
        if hip_y >= danger_y:
            new_zone = Zone.DANGER
        elif hip_y >= warning_y:
            new_zone = Zone.WARNING
        else:
            new_zone = Zone.SAFE

        alert: Optional[str] = None
        # 위험 구역으로 *진입* 한 순간에만 알림 (구역 안에서 머무르는 동안 반복 X)
        if new_zone == Zone.DANGER and self._zone != Zone.DANGER:
            if now - self._last_alert_at >= config.ALERT_COOLDOWN_SEC:
                self._last_alert_at = now
                ts = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
                alert = (
                    f"⚠️ 낙상 위험 구역 진입 ({ts}) — hip y={hip_y:.0f}px "
                    f"(위험선 {danger_y:.0f}px). 즉시 확인 바랍니다."
                )
                log.warning("Fall prevention DANGER zone entered (hip_y=%.0f, danger_y=%.0f)",
                            hip_y, danger_y)

        if new_zone != self._zone:
            log.info("Fall prevention zone: %s → %s", self._zone.value, new_zone.value)
        self._zone = new_zone

        return FallPreventionResult(
            zone=new_zone, hip_y=hip_y,
            warning_y=warning_y, danger_y=danger_y, alert=alert,
        )
