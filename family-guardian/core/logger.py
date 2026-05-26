"""Unified logger: console + 일자별 회전 파일.

다른 모듈은 ``from core.logger import get_logger`` 후 ``get_logger(__name__)`` 만
호출한다. 동일 이름으로 여러 번 호출해도 핸들러 중복 없이 같은 인스턴스를 돌려준다.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import config

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to both console and a daily-rotating file.

    파일은 ``logs/guardian.log`` 한 개로 모이고, 자정마다 회전되어 14개까지 보존된다.
    """
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        logger.addHandler(stream)

    log_dir = Path(config.LOG_DIR)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / "guardian.log"
        if not any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers):
            file_handler = TimedRotatingFileHandler(
                file_path,
                when="midnight",
                interval=1,
                backupCount=14,
                encoding="utf-8",
                utc=False,
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    except OSError as exc:
        # 로그 디렉토리 생성 실패는 치명적이지 않음 - 콘솔 핸들러만 사용
        logger.warning("File log disabled (%s): %s", file_path if 'file_path' in locals() else log_dir, exc)

    _configured.add(name)
    return logger
