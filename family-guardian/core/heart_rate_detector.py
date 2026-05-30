"""Remote-PPG style heart-rate estimation.

이마(forehead) ROI 의 녹색 채널 평균 휘도를 ~15Hz 로 샘플링한 뒤, Hamming window
+ FFT 로 [HEART_RATE_MIN_BPM, HEART_RATE_MAX_BPM] 대역(0.67~3.0 Hz)에서 dominant
peak 를 찾는다. 심박에 의한 모세혈관 hemoglobin 흡수 변동을 측정하는 원리.

⚠️ rPPG 심박 추정은 호흡보다 신호 강도가 훨씬 약하다 (~0.5% 변동). 조명·움직임·
피부색·카메라 자동 노출에 매우 민감하며 ±10~15 BPM 오차는 정상이다. 의료기기가
아니므로 진단·응급 판단에 사용 금지.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

import numpy as np
from scipy.signal import detrend

import config
from core.logger import get_logger
from core.pose_detector import PoseFrame

log = get_logger(__name__)


@dataclass
class HeartRateResult:
    bpm: Optional[float]
    confidence: float
    last_update: float
    roi: Optional[Tuple[int, int, int, int]] = None  # (x0, y0, x1, y1) for UI overlay


class HeartRateDetector:
    _RESAMPLE_FS = 15.0  # Hz — 심박은 호흡보다 빠르므로 더 높게
    _MIN_DURATION_SEC = 5.0

    def __init__(self) -> None:
        self._samples: Deque[Tuple[float, float]] = deque()
        self._last_roi: Optional[Tuple[int, int, int, int]] = None
        self._last_result: Optional[HeartRateResult] = None

    def update(self, frame_bgr: np.ndarray, pose: Optional[PoseFrame]) -> HeartRateResult:
        now = time.time()

        green_mean, roi = self._extract_forehead_roi(frame_bgr, pose)
        if green_mean is not None:
            self._samples.append((now, green_mean))
            self._last_roi = roi
            cutoff = now - config.HEART_RATE_ROI_SEC * 1.5
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

        bpm, confidence = self._estimate_bpm()
        result = HeartRateResult(
            bpm=bpm, confidence=confidence, last_update=now, roi=self._last_roi
        )
        self._last_result = result
        return result

    # -- ROI ------------------------------------------------------------------

    @staticmethod
    def _extract_forehead_roi(
        frame_bgr: np.ndarray, pose: Optional[PoseFrame]
    ) -> Tuple[Optional[float], Optional[Tuple[int, int, int, int]]]:
        if frame_bgr is None or frame_bgr.size == 0:
            return None, None
        if pose is None or not pose.face_visibility_ok:
            return None, None
        if pose.left_eye is None or pose.right_eye is None:
            return None, None

        h, w = frame_bgr.shape[:2]
        ex_l, ey_l = pose.left_eye
        ex_r, ey_r = pose.right_eye
        eye_mid_x = (ex_l + ex_r) / 2.0
        eye_mid_y = (ey_l + ey_r) / 2.0
        inter_eye = ((ex_l - ex_r) ** 2 + (ey_l - ey_r) ** 2) ** 0.5
        if inter_eye < 6.0:
            return None, None

        # 이마: 두 눈 중점에서 위로 inter_eye 의 0.8배, 폭 1.2배, 높이 0.8배
        cx = eye_mid_x
        cy = eye_mid_y - inter_eye * 0.8
        half_w = inter_eye * 0.6
        half_h = inter_eye * 0.4

        x0 = int(max(0, cx - half_w))
        y0 = int(max(0, cy - half_h))
        x1 = int(min(w, cx + half_w))
        y1 = int(min(h, cy + half_h))
        if x1 <= x0 or y1 <= y0:
            return None, None

        roi = frame_bgr[y0:y1, x0:x1, 1]
        if roi.size == 0:
            return None, None
        return float(roi.mean()), (x0, y0, x1, y1)

    # -- estimation -----------------------------------------------------------

    def _estimate_bpm(self) -> Tuple[Optional[float], float]:
        samples = list(self._samples)
        if len(samples) < 10:
            return None, 0.0

        ts = np.array([s[0] for s in samples], dtype=np.float64)
        vals = np.array([s[1] for s in samples], dtype=np.float64)

        duration = float(ts[-1] - ts[0])
        if duration < self._MIN_DURATION_SEC:
            return None, 0.0
        if float(np.std(vals)) < config.HEART_RATE_SIGNAL_MIN_STD:
            return None, 0.0

        n = max(int(duration * self._RESAMPLE_FS), 32)
        t_uniform = np.linspace(ts[0], ts[-1], n)
        v_uniform = np.interp(t_uniform, ts, vals)

        try:
            v_dt = detrend(v_uniform)
        except ValueError as exc:
            log.debug("HR detrend failed (n=%d): %s", n, exc)
            return None, 0.0

        # Hamming window 으로 spectral leakage 억제 (호흡보다 peak 가 좁아서 중요)
        window = np.hamming(n)
        spectrum = np.abs(np.fft.rfft(v_dt * window))
        freqs = np.fft.rfftfreq(n, d=1.0 / self._RESAMPLE_FS)

        min_hz = config.HEART_RATE_MIN_BPM / 60.0
        max_hz = config.HEART_RATE_MAX_BPM / 60.0
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

        confidence = min(peak_power / total_power * 4.0, 1.0)
        bpm = float(band_freqs[peak_idx] * 60.0)
        return bpm, confidence
