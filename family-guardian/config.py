"""Central configuration for family-guardian.

모든 임계값과 정책을 한 곳에서 관리한다. 환경변수는 `.env` 파일에서 자동 로드되며,
이 모듈을 import 한 시점에 평가된 값이 그대로 상수로 노출된다.

다른 모듈에서는 ``import config`` 후 ``config.MODE`` 처럼 항상 attribute 접근으로
사용한다 (``from config import MODE`` 금지: 런타임에 .env 가 갱신되면 stale 값이 됨).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_str(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y", "t"}


# -----------------------------------------------------------------------------
# Mode
# -----------------------------------------------------------------------------
MODE: str = _get_str("MODE", "elder").lower()

# -----------------------------------------------------------------------------
# Camera
# -----------------------------------------------------------------------------
CAMERA_INDEX: int = _get_int("CAMERA_INDEX", 0)
FRAME_WIDTH: int = 640
FRAME_HEIGHT: int = 480
TARGET_FPS: int = 15

# -----------------------------------------------------------------------------
# Fall detection rules
# -----------------------------------------------------------------------------
HEAD_DROP_WINDOW_SEC: float = 1.0
HEAD_DROP_RATIO: float = 0.25
TORSO_HORIZONTAL_THRESHOLD_DEG: float = 35.0
IMMOBILE_AFTER_FALL_SEC: float = 5.0
IMMOBILE_PIXEL_THRESHOLD: float = 8.0
ALERT_COOLDOWN_SEC: float = 60.0

# -----------------------------------------------------------------------------
# Breathing detection (rPPG, 참고용)
# -----------------------------------------------------------------------------
BREATHING_ROI_SEC: float = 10.0
BREATHING_MIN_BPM: int = 15
BREATHING_MAX_BPM: int = 80
BREATHING_APNEA_SEC: float = 10.0
BREATHING_SIGNAL_MIN_STD: float = 0.3

# -----------------------------------------------------------------------------
# Heart rate detection (rPPG, 참고용 — 호흡보다 더 노이지)
# -----------------------------------------------------------------------------
# 이마 ROI 의 녹색 채널 변화로 추정. 신호 강도는 호흡보다 훨씬 약하고 (~0.5%)
# 조명·움직임·피부색에 매우 민감. ±10~15 BPM 오차는 정상이며 의료 판단 금지.
HEART_RATE_ROI_SEC: float = 10.0
HEART_RATE_MIN_BPM: int = 40
HEART_RATE_MAX_BPM: int = 180
HEART_RATE_SIGNAL_MIN_STD: float = 0.05

# -----------------------------------------------------------------------------
# Motion analyzer (frame difference)
# -----------------------------------------------------------------------------
# 다운샘플된 그레이스케일 프레임의 절대 차분 평균을 모션 강도로 쓴다.
# 자세 인식 실패 (가림, 야간, 자세 이상) 시에도 동작하는 기초 신호.
MOTION_DOWNSAMPLE_W: int = 160
MOTION_DOWNSAMPLE_H: int = 120
MOTION_QUIET_THRESHOLD: float = 0.6   # 평균 픽셀 차이 (0~255 단위). 미만이면 "조용함"

# -----------------------------------------------------------------------------
# Activity classification (자세 분류)
# -----------------------------------------------------------------------------
# torso_angle_deg 기반. 90도=직립, 0도=수평.
ACTIVITY_LYING_MAX_DEG: float = 30.0   # 이하면 LYING
ACTIVITY_STANDING_MIN_DEG: float = 65.0  # 이상이면 STANDING, 그 사이면 SITTING

# -----------------------------------------------------------------------------
# Prolonged inactivity (장시간 미동 — elder 모드 만성 무반응 감지)
# -----------------------------------------------------------------------------
# 의식 잃거나 못 일어나는 상황을 빠른 낙상 시퀀스가 아니라
# "오랫동안 움직임이 없음" 으로 잡는다.
INACTIVITY_THRESHOLD_MIN: int = 10        # 분
INACTIVITY_ALERT_COOLDOWN_SEC: float = 300.0  # 5분

# -----------------------------------------------------------------------------
# Cardiac emergency suspicion (심정지 의심)
# -----------------------------------------------------------------------------
# 의료 진단 아님 — 다음 신호를 동시에 만족하면 "응급 의심" 으로 격상한다:
#   1) 모션 강도가 CARDIAC_IMMOBILITY_SEC 이상 임계값 미만
#   2) BreathingDetector 의 apnea_suspected = True
#   3) 자세가 LYING / 인식 실패 (collapsed)
# 그 상태가 CARDIAC_CONFIRMATION_SEC 동안 유지되면 알림.
# 잘못 울려도 비용은 "한 번 확인" — 놓치면 사람이 죽으므로 false-positive 허용.
CARDIAC_IMMOBILITY_SEC: float = 30.0
CARDIAC_CONFIRMATION_SEC: float = 10.0
CARDIAC_ALERT_COOLDOWN_SEC: float = 120.0

# -----------------------------------------------------------------------------
# Fall prevention (낙상 예방 — 사후 감지가 아니라 사전 경고)
# -----------------------------------------------------------------------------
# 프레임 상단에서 아래로 몇 % 지점에 위험/경고선을 둘지. hip_mid 의 y 좌표가
# 이 선을 넘어가면 SAFE → WARNING → DANGER 순으로 전이된다.
# (영상 좌표계에서 y 는 위→아래 증가)
FALL_PREVENTION_WARNING_Y_RATIO: float = 0.55
FALL_PREVENTION_DANGER_Y_RATIO: float = 0.70

# -----------------------------------------------------------------------------
# Recording (공통)
# -----------------------------------------------------------------------------
RECORD_DIR: str = _get_str("RECORD_DIR", "./recordings")
VIDEO_FOURCC: str = "mp4v"
VIDEO_EXT: str = "mp4"

# -----------------------------------------------------------------------------
# Baby recording
# -----------------------------------------------------------------------------
BABY_SEGMENT_MINUTES: int = 30
BABY_RETENTION_HOURS: int = 72

# -----------------------------------------------------------------------------
# Elder incident recording
# -----------------------------------------------------------------------------
ELDER_PREBUFFER_SEC: float = 10.0
ELDER_POSTRECORD_MAX_SEC: float = 60.0
ELDER_INCIDENT_RETENTION_DAYS: int = 30

# -----------------------------------------------------------------------------
# Notifier
# -----------------------------------------------------------------------------
NOTIFIER: str = _get_str("NOTIFIER", "console").lower()
TELEGRAM_BOT_TOKEN: str = _get_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = _get_str("TELEGRAM_CHAT_ID", "")
TELEGRAM_ATTACH_VIDEO: bool = _get_bool("TELEGRAM_ATTACH_VIDEO", True)

# -----------------------------------------------------------------------------
# Cloud upload
# -----------------------------------------------------------------------------
CLOUD_UPLOAD_ENABLED: bool = _get_bool("CLOUD_UPLOAD_ENABLED", False)
AWS_REGION: str = _get_str("AWS_REGION", "ap-northeast-2")
S3_BUCKET: str = _get_str("S3_BUCKET", "")

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_DIR: str = _get_str("LOG_DIR", "./logs")
LOG_LEVEL: str = _get_str("LOG_LEVEL", "INFO").upper()

# -----------------------------------------------------------------------------
# Stability / runtime
# -----------------------------------------------------------------------------
CAMERA_RECONNECT_BACKOFF_SEC: float = 2.0
CAMERA_RECONNECT_MAX_BACKOFF: float = 30.0
HEALTH_LOG_INTERVAL_SEC: float = 60.0


def ensure_dirs() -> None:
    """Ensure runtime directories exist. Called once at startup."""
    Path(RECORD_DIR).mkdir(parents=True, exist_ok=True)
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
