"""Continuous segmented recorder for the baby (영유아) mode.

30분 단위로 mp4 분할 저장, 보존 기간 (BABY_RETENTION_HOURS) 초과 파일은 자동 삭제.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

import config
from core.logger import get_logger

log = get_logger(__name__)


class BabyRecorder:
    def __init__(self, fps: int = None, frame_size: Optional[tuple] = None) -> None:
        self.fps = int(fps) if fps else int(config.TARGET_FPS)
        self.frame_size = frame_size or (config.FRAME_WIDTH, config.FRAME_HEIGHT)
        self._writer: Optional[cv2.VideoWriter] = None
        self._segment_started_at: float = 0.0
        self._current_path: Optional[Path] = None
        self._last_cleanup_at: float = 0.0
        self._dir = Path(config.RECORD_DIR) / "baby"
        self._dir.mkdir(parents=True, exist_ok=True)

    def write(self, frame_bgr: np.ndarray, now: Optional[float] = None) -> None:
        ts = now if now is not None else time.time()
        if self._writer is None or self._should_rotate(ts):
            self._rotate(ts, frame_bgr.shape[:2])
        if self._writer is not None:
            self._writer.write(frame_bgr)

        if ts - self._last_cleanup_at >= 3600.0:
            self._last_cleanup_at = ts
            self._cleanup_old_files(ts)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            log.info("Baby segment closed: %s", self._current_path)

    # -- internals ------------------------------------------------------------

    def _should_rotate(self, now: float) -> bool:
        return (now - self._segment_started_at) >= config.BABY_SEGMENT_MINUTES * 60.0

    def _rotate(self, now: float, shape_hw) -> None:
        self.close()
        ts_str = datetime.fromtimestamp(now).strftime("%Y%m%d_%H%M%S")
        path = self._dir / f"baby_{ts_str}.{config.VIDEO_EXT}"
        fourcc = cv2.VideoWriter_fourcc(*config.VIDEO_FOURCC)
        h, w = shape_hw
        writer = cv2.VideoWriter(str(path), fourcc, float(self.fps), (int(w), int(h)))
        if not writer.isOpened():
            log.error("Failed to open VideoWriter for %s", path)
            return
        self._writer = writer
        self._segment_started_at = now
        self._current_path = path
        log.info("Baby segment started: %s", path)

    def _cleanup_old_files(self, now: float) -> None:
        cutoff = now - config.BABY_RETENTION_HOURS * 3600.0
        removed = 0
        try:
            for entry in self._dir.iterdir():
                if not entry.is_file() or entry.suffix != f".{config.VIDEO_EXT}":
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError as exc:
                    log.warning("Stat failed for %s: %s", entry, exc)
                    continue
                if mtime < cutoff:
                    try:
                        entry.unlink()
                        removed += 1
                    except OSError as exc:
                        log.warning("Failed to delete %s: %s", entry, exc)
        except OSError as exc:
            log.error("Cleanup scan failed: %s", exc)
            return
        if removed:
            log.info("Removed %d expired baby segments (>%dh)", removed, config.BABY_RETENTION_HOURS)
