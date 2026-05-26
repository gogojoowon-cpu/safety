"""Notifier abstract base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str, video_path: Optional[str] = None) -> bool:
        """Send `message`. Returns True if the message was accepted by the channel."""
        raise NotImplementedError
