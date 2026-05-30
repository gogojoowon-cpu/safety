"""FastAPI web demo: browser uploads JPEG frames, server runs the pipeline.

브라우저가 `getUserMedia` 로 캡쳐한 프레임을 ~100ms 마다 POST /frame 으로 보내면,
서버가 기존 ``PoseDetector → FallDetector → (BabyRecorder|IncidentRecorder)`` 흐름에
그대로 흘려 넣고 상태를 JSON 으로 돌려준다.

Railway 같은 ephemeral 컨테이너에서 돌리는 게 전제다 — 녹화 파일은 영구 저장
되지 않으니, 알림 영상을 보관하려면 ``CLOUD_UPLOAD_ENABLED=true`` 로 S3 업로드를
켜야 한다.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from core.breathing_detector import BreathingDetector
from core.event_state import State
from core.fall_detector import FallDetector
from core.fall_prevention import FallPreventionDetector
from core.heart_rate_detector import HeartRateDetector
from core.incident_recorder import IncidentRecorder
from core.logger import get_logger
from core.pose_detector import PoseDetector
from core.recorder import BabyRecorder
from notifiers import build_notifier
from storage.cloud_uploader import CloudUploader

log = get_logger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


class Pipeline:
    """Per-process singleton wrapping the existing detection pipeline."""

    def __init__(self) -> None:
        self.pose = PoseDetector()
        self.fall = FallDetector(frame_height=config.FRAME_HEIGHT)
        self.notifier = build_notifier()
        self.uploader = CloudUploader()
        self.lock = asyncio.Lock()

        # Heart-rate detector runs in BOTH modes — face landmarks are needed,
        # so it self-degrades to None when the user is not facing the camera.
        self.heart_rate = HeartRateDetector()

        # Pre-fall warning based on hip y-coordinate vs configurable danger lines.
        # Runs in both modes; fires alerts BEFORE the FallDetector state machine
        # would have triggered, so caregivers can intervene early.
        self.fall_prevention = FallPreventionDetector()

        self.mode: str = "elder"
        self.baby_rec: Optional[BabyRecorder] = None
        self.incident_rec: Optional[IncidentRecorder] = None
        self.breathing: Optional[BreathingDetector] = None
        self.prev_state: State = State.NORMAL
        self.last_confirmed_path: Optional[str] = None
        self.last_alert: Optional[str] = None
        self.last_alert_at: float = 0.0
        self.last_result: dict = {}
        self.frame_count: int = 0

        initial = config.MODE if config.MODE in ("elder", "baby") else "elder"
        self._configure_mode(initial)

    def _on_confirmed(self, path: str) -> None:
        self.last_confirmed_path = path
        self.uploader.upload_async(path)

    def _configure_mode(self, mode: str) -> None:
        if self.baby_rec is not None:
            try:
                self.baby_rec.close()
            except Exception:  # noqa: BLE001
                log.exception("baby_rec.close failed during mode switch")
            self.baby_rec = None
        if self.incident_rec is not None:
            try:
                self.incident_rec.close()
            except Exception:  # noqa: BLE001
                log.exception("incident_rec.close failed during mode switch")
            self.incident_rec = None
        self.breathing = None

        self.mode = mode
        if mode == "baby":
            try:
                self.baby_rec = BabyRecorder()
            except Exception:  # noqa: BLE001
                log.exception("BabyRecorder init failed (continuing without disk recording)")
            self.breathing = BreathingDetector()
        else:
            try:
                self.incident_rec = IncidentRecorder(on_confirmed=self._on_confirmed)
            except Exception:  # noqa: BLE001
                log.exception("IncidentRecorder init failed (continuing without disk recording)")

        # Reset state machine so a mode flip doesn't carry stale history
        self.fall = FallDetector(frame_height=config.FRAME_HEIGHT)
        self.prev_state = State.NORMAL
        log.info("Pipeline mode set to %s", mode)

    async def process(self, frame_bgr: np.ndarray) -> dict:
        async with self.lock:
            return await asyncio.to_thread(self._process_sync, frame_bgr)

    def _process_sync(self, frame_bgr: np.ndarray) -> dict:
        now = time.time()
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        try:
            pose = self.pose.process(frame_rgb, now)
        except Exception:  # noqa: BLE001
            log.exception("pose_detector.process failed")
            pose = None

        alert_msg = self.fall.update(pose)
        new_state = self.fall.state
        torso_deg = (
            pose.torso_angle_deg() if pose is not None and pose.visibility_ok else None
        )

        bpm: Optional[float] = None
        bpm_conf: Optional[float] = None
        apnea_msg: Optional[str] = None

        hr_bpm: Optional[float] = None
        hr_conf: Optional[float] = None
        hr_roi: Optional[tuple] = None
        try:
            hr_result = self.heart_rate.update(frame_bgr, pose)
            hr_bpm = hr_result.bpm
            hr_conf = hr_result.confidence
            hr_roi = hr_result.roi
        except Exception:  # noqa: BLE001
            log.exception("heart_rate.update failed")

        fp_zone = "SAFE"
        fp_hip_y: Optional[float] = None
        fp_warning_y = 0.0
        fp_danger_y = 0.0
        fp_alert: Optional[str] = None
        try:
            fp_result = self.fall_prevention.update(
                pose, frame_height=frame_bgr.shape[0], now=now
            )
            fp_zone = fp_result.zone.value
            fp_hip_y = fp_result.hip_y
            fp_warning_y = fp_result.warning_y
            fp_danger_y = fp_result.danger_y
            fp_alert = fp_result.alert
        except Exception:  # noqa: BLE001
            log.exception("fall_prevention.update failed")

        if fp_alert:
            try:
                self.notifier.send(fp_alert, video_path=None)
            except Exception:  # noqa: BLE001
                log.exception("fall_prevention notifier.send failed")
            self.last_alert = fp_alert
            self.last_alert_at = now

        if self.mode == "baby":
            if self.baby_rec is not None:
                try:
                    self.baby_rec.write(frame_bgr, now)
                except Exception:  # noqa: BLE001
                    log.exception("baby_rec.write failed")
            if self.breathing is not None:
                try:
                    br = self.breathing.update(frame_bgr, pose)
                    bpm = br.bpm
                    bpm_conf = br.confidence
                    apnea_msg = self.breathing.build_alert(now)
                except Exception:  # noqa: BLE001
                    log.exception("breathing.update failed")
                if apnea_msg:
                    try:
                        self.notifier.send(apnea_msg, video_path=None)
                    except Exception:  # noqa: BLE001
                        log.exception("apnea notifier.send failed")
        elif self.incident_rec is not None:
            try:
                if (
                    self.prev_state != State.SUSPECTED_FALL
                    and new_state == State.SUSPECTED_FALL
                ):
                    self.incident_rec.start_on_suspected(now)
                elif (
                    self.prev_state == State.SUSPECTED_FALL
                    and new_state == State.NORMAL
                ):
                    self.incident_rec.discard()
                elif (
                    self.prev_state != State.CONFIRMED_FALL
                    and new_state == State.CONFIRMED_FALL
                ):
                    saved = self.incident_rec.confirm()
                    if saved:
                        self.last_confirmed_path = saved

                if self.incident_rec.state.value == "IDLE":
                    self.incident_rec.feed_idle_frame(frame_bgr, now)
                else:
                    self.incident_rec.feed_recording_frame(frame_bgr, now)
            except Exception:  # noqa: BLE001
                log.exception("incident_rec update failed")

        if alert_msg:
            try:
                self.notifier.send(alert_msg, video_path=self.last_confirmed_path)
            except Exception:  # noqa: BLE001
                log.exception("fall notifier.send failed")
            self.last_alert = alert_msg
            self.last_alert_at = now
            self.last_confirmed_path = None
        elif apnea_msg:
            self.last_alert = apnea_msg
            self.last_alert_at = now

        self.prev_state = new_state
        self.frame_count += 1
        self.last_result = {
            "mode": self.mode,
            "state": new_state.value,
            "torso_deg": torso_deg,
            "bpm": bpm,
            "bpm_confidence": bpm_conf,
            "hr_bpm": hr_bpm,
            "hr_confidence": hr_conf,
            "hr_roi": list(hr_roi) if hr_roi else None,
            "face_visible": pose.face_visibility_ok if pose is not None else False,
            "fp_zone": fp_zone,
            "fp_hip_y": fp_hip_y,
            "fp_warning_y": fp_warning_y,
            "fp_danger_y": fp_danger_y,
            "last_alert": self.last_alert,
            "last_alert_at": self.last_alert_at,
            "frame_count": self.frame_count,
            "ts": now,
        }
        return self.last_result


_pipeline: Optional[Pipeline] = None
_pipeline_lock = asyncio.Lock()


async def get_pipeline_async() -> Pipeline:
    """Lazy-init the pipeline. MediaPipe load is offloaded to a worker thread
    so the event loop (and /healthz) stays responsive during startup."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    async with _pipeline_lock:
        if _pipeline is None:
            log.info("Initializing pipeline (lazy)")
            _pipeline = await asyncio.to_thread(_build_pipeline)
            log.info("Pipeline ready")
    return _pipeline


def _build_pipeline() -> Pipeline:
    config.ensure_dirs()
    return Pipeline()


app = FastAPI(title="family-guardian web demo")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = _STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/healthz")
async def healthz() -> dict:
    # Must NOT touch the pipeline: Railway's healthcheck has to succeed
    # before MediaPipe finishes its first-load (which can take 10+ seconds).
    return {"ok": True, "pipeline_ready": _pipeline is not None}


@app.get("/state")
async def state() -> dict:
    if _pipeline is None:
        return {"mode": config.MODE, "state": "NORMAL", "pipeline_ready": False}
    return _pipeline.last_result or {"mode": _pipeline.mode, "state": "NORMAL"}


@app.post("/mode/{mode}")
async def set_mode(mode: str) -> dict:
    mode_l = mode.lower()
    if mode_l not in ("elder", "baby"):
        raise HTTPException(status_code=400, detail="mode must be 'elder' or 'baby'")
    pipe = await get_pipeline_async()
    async with pipe.lock:
        pipe._configure_mode(mode_l)
    return {"ok": True, "mode": mode_l}


@app.post("/frame")
async def frame(file: UploadFile = File(...)) -> JSONResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty frame")
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="could not decode frame")
    pipe = await get_pipeline_async()
    result = await pipe.process(img)
    return JSONResponse(result)
