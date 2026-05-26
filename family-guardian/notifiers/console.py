"""Console notifier: simply prints alerts. Useful for dev / debug."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from core.logger import get_logger
from notifiers.base import Notifier

log = get_logger(__name__)


class ConsoleNotifier(Notifier):
    def send(self, message: str, video_path: Optional[str] = None) -> bool:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[ALERT {ts}]\n{message}")
        if video_path:
            print(f"[video] {video_path}")
        log.info("ConsoleNotifier sent alert (video=%s)", video_path)
        return True
