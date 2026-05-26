"""Remote-PPG style breathing rate estimation.

가슴 영역(ROI)의 녹색 채널 평균 휘도를 시간에 따라 샘플링하고, 등간격으로 리샘플 후
FFT 를 적용해 [BREATHING_MIN_BPM, BREATHING_MAX_BPM] 대역에서 dominant frequency 를
찾는다.

⚠️ 본 기능은 **참고용 데모**이며 의료기기가 아니다. 실제 환자 모니터링이나 진단에는
사용하지 말 것. 카메라 화이트밸런스, 조명, 의류 색상, ROI 흔들림 등 외부 요인에
크게 좌우되므로 ±5~10 BPM 의 오차가 정상이다.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Optional, Tuple

import numpy as np
from scipy.signal import detrend

import config
from core.logger import get_logger
from core.pose_detector import PoseFrame

log = get_logger(__name__)


@dataclass
class BreathingResult:
    bpm: Optional[float]
    confidence: float
    apnea_suspected: bool
    last_update: float


class BreathingDetector:
    _RESAMPLE_FS = 10.0  # Hz
    _MIN_DURATION_SEC = 4.0

    def __init__(self) -> None:
        self._samples: Deque[Tuple[float, float]] = deque()
        self._last_good_at: Optional[float] = None
        self._last_alert_at: float = -math.inf
        self._last_result: Optional[BreathingResult] = None

    def update(self, frame_bgr: np.ndarray, pose: Optional[PoseFrame]) -> BreathingResult:
        now = time.time()

        green_mean = self._extract_chest_roi(frame_bgr, pose)
        if green_mean is not None:
            self._samples.append((now, green_mean))
            cutoff = now - config.BREATHING_ROI_SEC * 1.5
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

        bpm, confidence = self._estimate_bpm()
        if bpm is not None and confidence >= 0.3:
            self._last_good_at = now

        apnea = self._detect_apnea(now, bpm, confidence)
        result = BreathingResult(bpm=bpm, confidence=confidence,
                                 apnea_suspected=apnea, last_update=now)
        self._last_result = result
        return result

    # -- ROI ------------------------------------------------------------------

    @staticmethod
    def _extract_chest_roi(frame_bgr: np.ndarray, pose: Optional[PoseFrame]) -> Optional[float]:
        if frame_bgr is None or frame_bgr.size == 0:
            return None
        h, w = frame_bgr.shape[:2]
        if pose is not None and pose.visibility_ok:
            sx, sy = pose.shoulder_mid
            hx, hy = pose.hip_mid
            cx, cy = (sx + hx) / 2.0, (sy + hy) / 2.0
            shoulder_w = abs(pose.right_shoulder[0] - pose.left_shoulder[0])
            side = max(8.0, shoulder_w * 0.4)
        else:
            # 자세 추정 실패 시: 프레임 중앙 ROI 로 graceful fallback
            cx, cy = w / 2.0, h / 2.0
            side = min(h, w) * 0.2

        half = side / 2.0
        x0 = int(max(0, cx - half))
        y0 = int(max(0, cy - half))
        x1 = int(min(w, cx + half))
        y1 = int(min(h, cy + half))
        if x1 <= x0 or y1 <= y0:
            return None
        roi = frame_bgr[y0:y1, x0:x1, 1]  # green channel
        if roi.size == 0:
            return None
        return float(roi.mean())

    # -- estimation -----------------------------------------------------------

    def _estimate_bpm(self) -> Tuple[Optional[float], float]:
        samples = list(self._samples)
        if len(samples) < 5:
            return None, 0.0

        ts = np.array([s[0] for s in samples], dtype=np.float64)
        vals = np.array([s[1] for s in samples], dtype=np.float64)

        duration = float(ts[-1] - ts[0])
        if duration < self._MIN_DURATION_SEC:
            return None, 0.0
        if float(np.std(vals)) < config.BREATHING_SIGNAL_MIN_STD:
            return None, 0.0

        n = max(int(duration * self._RESAMPLE_FS), 16)
        t_uniform = np.linspace(ts[0], ts[-1], n)
        v_uniform = np.interp(t_uniform, ts, vals)

        try:
            v_dt = detrend(v_uniform)
        except ValueError as exc:
            log.debug("detrend failed (n=%d): %s", n, exc)
            return None, 0.0

        spectrum = np.abs(np.fft.rfft(v_dt))
        freqs = np.fft.rfftfreq(n, d=1.0 / self._RESAMPLE_FS)

        min_hz = config.BREATHING_MIN_BPM / 60.0
        max_hz = config.BREATHING_MAX_BPM / 60.0
        mask = (freqs >= min_hz) & (freqs <= max_hz)
        if not np.any(mask):
            return None, 0.0

        band = spectrum[mask]
        band_freqs = freqs[mask]
        peak_idx = int(np.argmax(band))
        peak_power = float(band[peak_idx])
        total_power = float(band.sum())
        if total_power <= 0.0:
            return None, 0.0

        confidence = min(peak_power / total_power * 3.0, 1.0)
        bpm = float(band_freqs[peak_idx] * 60.0)
        return bpm, confidence

    # -- apnea / alert --------------------------------------------------------

    def _detect_apnea(self, now: float, bpm: Optional[float], conf: float) -> bool:
        is_bad = bpm is None or bpm < config.BREATHING_MIN_BPM or conf < 0.2
        if not is_bad:
            return False
        if self._last_good_at is None:
            return False
        return (now - self._last_good_at) >= config.BREATHING_APNEA_SEC

    def build_alert(self, now: float) -> Optional[str]:
        if self._last_result is None or not self._last_result.apnea_suspected:
            return None
        if now - self._last_alert_at < config.ALERT_COOLDOWN_SEC:
            return None
        self._last_alert_at = now
        ts = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        last_bpm = self._last_result.bpm
        bpm_str = f"{last_bpm:.0f}" if last_bpm is not None else "측정불가"
        return (
            f"⚠️ 호흡 신호 이상 의심 ({ts}) — 마지막 BPM: {bpm_str}.\n"
            "본 알림은 카메라 기반 추정치로 **참고용**입니다. "
            "의료기기가 아니므로 즉시 직접 확인해 주세요."
        )
