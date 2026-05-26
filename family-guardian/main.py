"""family-guardian — entry point.

영유아 / 노인 안전 모니터링 데모. 의료기기가 아니며, 보호자의 직접 감독을
대체하지 않는다.
"""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime
from typing import Optional

import cv2

import config
from core.breathing_detector import BreathingDetector
from core.event_state import State
from core.fall_detector import FallDetector
from core.incident_recorder import IncidentRecorder
from core.logger import get_logger
from core.pose_detector import PoseDetector
from core.recorder import BabyRecorder
from notifiers import build_notifier
from storage.cloud_uploader import CloudUploader

log = get_logger(__name__)

_should_stop = False
_MAX_CONSECUTIVE_READ_FAILURES = 30


def _install_signal_handlers() -> None:
    def _handle(signum, _frame):
        global _should_stop
        log.info("Signal %s received — graceful shutdown", signum)
        _should_stop = True

    signal.signal(signal.SIGINT, _handle)
    try:
        signal.signal(signal.SIGTERM, _handle)
    except (AttributeError, ValueError):
        # SIGTERM not available on some platforms (e.g., Windows non-console).
        log.debug("SIGTERM handler not installed (unavailable on this platform)")


def open_camera() -> Optional[cv2.VideoCapture]:
    """Open camera with exponential-backoff retry. Returns None only if asked to stop."""
    backoff = config.CAMERA_RECONNECT_BACKOFF_SEC
    while not _should_stop:
        cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
            log.info("Camera opened (index=%s)", config.CAMERA_INDEX)
            return cap
        cap.release()
        log.warning("Camera open failed; retrying in %.1fs", backoff)
        _interruptible_sleep(backoff)
        backoff = min(backoff * 2.0, config.CAMERA_RECONNECT_MAX_BACKOFF)
    return None


def _interruptible_sleep(seconds: float) -> None:
    end = time.time() + seconds
    while not _should_stop and time.time() < end:
        time.sleep(min(0.2, end - time.time()))


def draw_overlay(
    frame_bgr,
    *,
    mode: str,
    state: State,
    torso_deg: Optional[float],
    bpm: Optional[float] = None,
    bpm_conf: Optional[float] = None,
) -> None:
    color = (0, 200, 0)
    if state == State.SUSPECTED_FALL:
        color = (0, 165, 255)
    elif state == State.CONFIRMED_FALL:
        color = (0, 0, 255)

    lines = [
        f"Mode: {mode}",
        f"State: {state.value}",
        f"Torso: {torso_deg:.1f} deg" if torso_deg is not None else "Torso: --",
    ]
    if mode == "baby":
        bpm_str = f"{bpm:.0f}" if bpm is not None else "--"
        conf_str = f"{bpm_conf:.2f}" if bpm_conf is not None else "--"
        lines.append(f"BPM: {bpm_str}  conf: {conf_str}")

    y = 22
    for line in lines:
        cv2.putText(frame_bgr, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, color, 2, cv2.LINE_AA)
        y += 24


def run() -> int:
    config.ensure_dirs()
    _install_signal_handlers()

    mode = config.MODE
    if mode not in ("elder", "baby"):
        log.warning("Unknown MODE=%r — defaulting to 'elder'", mode)
        mode = "elder"

    log.info("Starting family-guardian (mode=%s, notifier=%s)", mode, config.NOTIFIER)

    notifier = build_notifier()
    uploader = CloudUploader()
    pose_detector = PoseDetector()
    fall_detector = FallDetector(frame_height=config.FRAME_HEIGHT)

    baby_rec: Optional[BabyRecorder] = None
    incident_rec: Optional[IncidentRecorder] = None
    breathing: Optional[BreathingDetector] = None
    last_confirmed_path: Optional[str] = None

    def _on_confirmed(path: str) -> None:
        nonlocal last_confirmed_path
        last_confirmed_path = path
        uploader.upload_async(path)

    if mode == "baby":
        baby_rec = BabyRecorder()
        breathing = BreathingDetector()
    else:
        incident_rec = IncidentRecorder(on_confirmed=_on_confirmed)

    cap = open_camera()
    if cap is None:
        log.warning("No camera available and stop requested — exiting")
        return 0

    consecutive_failures = 0
    last_health_log = time.time()
    frame_count = 0
    fps_window_start = time.time()
    measured_fps = 0.0
    prev_state = State.NORMAL

    try:
        while not _should_stop:
            ok, frame_bgr = cap.read()
            if not ok or frame_bgr is None:
                consecutive_failures += 1
                if consecutive_failures >= _MAX_CONSECUTIVE_READ_FAILURES:
                    log.warning("Camera read failed %d times — reopening",
                                consecutive_failures)
                    cap.release()
                    cap = open_camera()
                    if cap is None:
                        break
                    consecutive_failures = 0
                continue
            consecutive_failures = 0

            now = time.time()
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pose = pose_detector.process(frame_rgb, now)

            alert_msg = fall_detector.update(pose)
            new_state = fall_detector.state

            torso_deg = pose.torso_angle_deg() if pose is not None and pose.visibility_ok else None

            bpm = None
            bpm_conf = None
            if mode == "baby":
                assert baby_rec is not None and breathing is not None
                baby_rec.write(frame_bgr, now)
                br_result = breathing.update(frame_bgr, pose)
                bpm = br_result.bpm
                bpm_conf = br_result.confidence
                apnea_msg = breathing.build_alert(now)
                if apnea_msg:
                    try:
                        notifier.send(apnea_msg, video_path=None)
                    except Exception:  # noqa: BLE001
                        log.exception("Apnea notifier.send failed")
            else:
                assert incident_rec is not None
                # State transitions for incident recorder
                if prev_state != State.SUSPECTED_FALL and new_state == State.SUSPECTED_FALL:
                    incident_rec.start_on_suspected(now)
                elif prev_state == State.SUSPECTED_FALL and new_state == State.NORMAL:
                    incident_rec.discard()
                elif prev_state != State.CONFIRMED_FALL and new_state == State.CONFIRMED_FALL:
                    saved = incident_rec.confirm()
                    if saved:
                        last_confirmed_path = saved

                if incident_rec.state.value == "IDLE":
                    incident_rec.feed_idle_frame(frame_bgr, now)
                else:
                    incident_rec.feed_recording_frame(frame_bgr, now)

            if alert_msg:
                try:
                    notifier.send(alert_msg, video_path=last_confirmed_path)
                except Exception:  # noqa: BLE001
                    log.exception("Fall notifier.send failed")
                last_confirmed_path = None

            prev_state = new_state

            # Overlay + display
            draw_overlay(frame_bgr, mode=mode, state=new_state,
                         torso_deg=torso_deg, bpm=bpm, bpm_conf=bpm_conf)
            try:
                cv2.imshow("family-guardian", frame_bgr)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # ESC
                    log.info("ESC pressed — exiting")
                    break
            except cv2.error as exc:
                log.debug("cv2.imshow disabled (headless): %s", exc)

            # FPS metric
            frame_count += 1
            elapsed = now - fps_window_start
            if elapsed >= 1.0:
                measured_fps = frame_count / elapsed
                frame_count = 0
                fps_window_start = now

            # Health log
            if now - last_health_log >= config.HEALTH_LOG_INTERVAL_SEC:
                log.info("health: mode=%s state=%s fps=%.1f",
                         mode, new_state.value, measured_fps)
                last_health_log = now

    except Exception:  # noqa: BLE001
        log.exception("Fatal error in main loop")
        return 1
    finally:
        if cap is not None:
            cap.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error as exc:
            log.debug("cv2.destroyAllWindows skipped (headless): %s", exc)
        try:
            pose_detector.close()
        except Exception:  # noqa: BLE001
            log.exception("pose_detector.close failed")
        if baby_rec is not None:
            try:
                baby_rec.close()
            except Exception:  # noqa: BLE001
                log.exception("baby_rec.close failed")
        if incident_rec is not None:
            try:
                incident_rec.close()
            except Exception:  # noqa: BLE001
                log.exception("incident_rec.close failed")
        log.info("family-guardian stopped at %s",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return 0


if __name__ == "__main__":
    sys.exit(run())
