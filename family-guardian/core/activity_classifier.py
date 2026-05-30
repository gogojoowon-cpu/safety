"""Stateless activity classifier — STANDING / SITTING / LYING / UNKNOWN.

가장 단순하면서도 신뢰도 높은 방식: 몸통 각도(``torso_angle_deg``)만으로 분류.
- 65도 이상 → STANDING
- 30~65도 → SITTING
- 30도 미만 → LYING
- pose 없음 → UNKNOWN

이 신호는 ``CardiacEmergencyDetector`` 의 입력 중 하나로 쓰이고, UI 에서도 사용자가
인식 결과를 확인할 수 있도록 표시된다.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

import config
from core.pose_detector import PoseFrame


class Activity(str, Enum):
    STANDING = "STANDING"
    SITTING = "SITTING"
    LYING = "LYING"
    UNKNOWN = "UNKNOWN"


def classify(pose: Optional[PoseFrame]) -> Activity:
    if pose is None or not pose.visibility_ok:
        return Activity.UNKNOWN
    torso = pose.torso_angle_deg()
    if torso >= config.ACTIVITY_STANDING_MIN_DEG:
        return Activity.STANDING
    if torso <= config.ACTIVITY_LYING_MAX_DEG:
        return Activity.LYING
    return Activity.SITTING
