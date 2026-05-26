"""Notifier factory."""
from __future__ import annotations

import config
from core.logger import get_logger
from notifiers.base import Notifier
from notifiers.console import ConsoleNotifier

log = get_logger(__name__)


def build_notifier() -> Notifier:
    kind = (config.NOTIFIER or "console").lower()
    if kind == "telegram":
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            log.warning("NOTIFIER=telegram but token/chat_id missing — falling back to console")
            return ConsoleNotifier()
        from notifiers.telegram import TelegramNotifier
        return TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    if kind != "console":
        log.warning("Unknown NOTIFIER=%r — falling back to console", kind)
    return ConsoleNotifier()


__all__ = ["Notifier", "ConsoleNotifier", "build_notifier"]
