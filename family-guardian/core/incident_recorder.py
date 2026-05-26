"""Incident-only recorder for the elder (노인) mode.

평시에는 디스크에 아무것도 쓰지 않고 ELDER_PREBUFFER_SEC 초 길이의 메모리 링버퍼만
유지한다. 낙상 의심 시 프리버퍼를 디스크에 flush 하고 이후 프레임도 라이브로 기록한다.
ELDER_POSTRECORD_MAX_SEC 도달 시 자동으로 보존(confirm) 처리한다.
"""
from __future__ import annotations

import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

import config
from core.logger import get_logger
from core.ring_buffer import FrameRingBuffer

log = get_logger(__name__)


class IncidentRecState(str, Enum):
    IDLE = "IDLE"
    RECORDING = "RECORDING"


class IncidentRecorder:
    def __init__(
        self,
        fps: int = None,
        frame_size: Optional[Tuple[int, int]] = None,
        on_confirmed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.fps = int(fps) if fps else int(config.TARGET_FPS)
        self.frame_size = frame_size or (config.FRAME_WIDTH, config.FRAME_HEIGHT)
        self.on_confirmed = on_confirmed
        self.state: IncidentRecState = IncidentRecState.IDLE
        self._prebuffer = FrameRingBuffer(config.ELDER_PREBUFFER_SEC, self.fps)
        self._writer: Optional[cv2.VideoWriter] = None
        self._current_path: Optional[Path] = None
        self._record_started_at: float = 0.0
        self._dir = Path(config.RECORD_DIR) / "incidents"
        self._dir.mkdir(parents=True, exist_ok=True)

    # -- frame ingestion ------------------------------------------------------

    def feed_idle_frame(self, frame_bgr: np.ndarray, now: float) -> None:
        if self.state != IncidentRecState.IDLE:
            return
        self._prebuffer.push(frame_bgr, now)

    def feed_recording_frame(self, frame_bgr: np.ndarray, now: float) -> Optional[str]:
        """Write frame to live file. Returns saved path if auto-confirmed."""
        if self.state != IncidentRecState.RECORDING or self._writer is None:
            return None
        self._writer.write(frame_bgr)
        if now - self._record_started_at >= config.ELDER_POSTRECORD_MAX_SEC:
            log.info("Post-record window reached; auto-confirming")
            return self.confirm()
        return None

    # -- transitions ----------------------------------------------------------

    def start_on_suspected(self, now: float, shape_hw: Optional[tuple] = None) -> None:
        if self.state == IncidentRecState.RECORDING:
            log.debug("start_on_suspected called while already RECORDING")
            return

        ts_str = datetime.fromtimestamp(now).strftime("%Y%m%d_%H%M%S")
        path = self._dir / f"incident_{ts_str}.{config.VIDEO_EXT}"

        snapshot = self._prebuffer.snapshot()
        if snapshot:
            sample = snapshot[0].frame_bgr
            h, w = sample.shape[:2]
        elif shape_hw is not None:
            h, w = shape_hw
        else:
            w, h = self.frame_size

        fourcc = cv2.VideoWriter_fourcc(*config.VIDEO_FOURCC)
        writer = cv2.VideoWriter(str(path), fourcc, float(self.fps), (int(w), int(h)))
        if not writer.isOpened():
            log.error("Failed to open incident writer at %s", path)
            return

        for tf in snapshot:
            writer.write(tf.frame_bgr)
        self._prebuffer.clear()

        self._writer = writer
        self._current_path = path
        self._record_started_at = now
        self.state = IncidentRecState.RECORDING
        log.warning("Incident recording started: %s (prebuffer=%d frames)", path, len(snapshot))

    def confirm(self) -> Optional[str]:
        if self.state != IncidentRecState.RECORDING or self._writer is None or self._current_path is None:
            return None
        self._writer.release()
        path_str = str(self._current_path)
        log.error("Incident confirmed and preserved: %s", path_str)
        self._writer = None
        saved = self._current_path
        self._current_path = None
        self.state = IncidentRecState.IDLE
        if self.on_confirmed is not None:
            try:
                self.on_confirmed(path_str)
            except Exception:  # noqa: BLE001
                log.exception("on_confirmed callback failed")
        return str(saved)

    def discard(self) -> None:
        if self.state != IncidentRecState.RECORDING:
            return
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        if self._current_path is not None and self._current_path.exists():
            try:
                self._current_path.unlink()
                log.info("False alarm: deleted %s", self._current_path)
            except OSError as exc:
                log.warning("Failed to delete %s: %s", self._current_path, exc)
        self._current_path = None
        self.state = IncidentRecState.IDLE

    def close(self) -> None:
        if self.state == IncidentRecState.RECORDING:
            log.info("Closing with active recording; preserving file")
            self.confirm()
