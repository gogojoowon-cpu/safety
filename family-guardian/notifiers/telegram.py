"""Telegram bot notifier.

5초 타임아웃으로 sendMessage 호출, 영상은 50MB 이하일 때만 sendVideo 첨부.
모든 예외는 잡아 False 만 돌려준다 — 메인 루프가 알림 실패로 멈추면 안 된다.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

import config
from core.logger import get_logger
from notifiers.base import Notifier

log = get_logger(__name__)

_TELEGRAM_VIDEO_LIMIT_BYTES = 50 * 1024 * 1024
_TIMEOUT_SEC = 5.0


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str, video_path: Optional[str] = None) -> bool:
        if not self.bot_token or not self.chat_id:
            log.error("Telegram not configured (missing token or chat_id)")
            return False

        ok = self._send_text(message)

        if ok and video_path and config.TELEGRAM_ATTACH_VIDEO:
            self._maybe_send_video(video_path)
        return ok

    def _send_text(self, message: str) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                data={"chat_id": self.chat_id, "text": message},
                timeout=_TIMEOUT_SEC,
            )
            if resp.status_code != 200:
                log.error("Telegram sendMessage failed: %s %s", resp.status_code, resp.text)
                return False
            return True
        except requests.RequestException:
            log.exception("Telegram sendMessage exception")
            return False
        except Exception:  # noqa: BLE001
            log.exception("Telegram sendMessage unexpected error")
            return False

    def _maybe_send_video(self, video_path: str) -> None:
        try:
            size = os.path.getsize(video_path)
        except OSError:
            log.exception("Could not stat video %s", video_path)
            return

        if size > _TELEGRAM_VIDEO_LIMIT_BYTES:
            log.warning(
                "Skipping Telegram video attach: %s is %.1f MB (>50MB)",
                video_path,
                size / 1024 / 1024,
            )
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendVideo"
        try:
            with open(video_path, "rb") as fh:
                resp = requests.post(
                    url,
                    data={"chat_id": self.chat_id},
                    files={"video": fh},
                    timeout=30.0,
                )
            if resp.status_code != 200:
                log.error("Telegram sendVideo failed: %s %s", resp.status_code, resp.text)
        except (OSError, requests.RequestException):
            log.exception("Telegram sendVideo exception")
        except Exception:  # noqa: BLE001
            log.exception("Telegram sendVideo unexpected error")
