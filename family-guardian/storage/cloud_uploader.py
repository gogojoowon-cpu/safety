"""Asynchronous S3 uploader.

boto3 가 없거나 CLOUD_UPLOAD_ENABLED=false 면 graceful degrade — 호출만 받고 NoOp.
업로드 실패해도 로컬 파일은 절대 지우지 않는다 (데이터 손실 방지).
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import config
from core.logger import get_logger

log = get_logger(__name__)


class CloudUploader:
    def __init__(self) -> None:
        self.enabled: bool = False
        self._client = None

        if not config.CLOUD_UPLOAD_ENABLED:
            log.info("CloudUploader disabled (CLOUD_UPLOAD_ENABLED=false)")
            return
        if not config.S3_BUCKET:
            log.warning("CloudUploader disabled: S3_BUCKET is empty")
            return

        try:
            import boto3  # type: ignore
        except ImportError:
            log.warning("CloudUploader disabled: boto3 not installed")
            return

        try:
            self._client = boto3.client("s3", region_name=config.AWS_REGION)
        except Exception:  # noqa: BLE001
            log.exception("CloudUploader disabled: boto3 client init failed")
            return

        self.enabled = True
        log.info("CloudUploader enabled (bucket=%s region=%s)",
                 config.S3_BUCKET, config.AWS_REGION)

    def upload_async(self, local_path: str, key: Optional[str] = None) -> None:
        if not self.enabled:
            return
        if not os.path.exists(local_path):
            log.warning("upload_async: file not found %s", local_path)
            return
        key = key or f"incidents/{os.path.basename(local_path)}"
        t = threading.Thread(
            target=self._upload,
            args=(local_path, key),
            name=f"s3-upload-{os.path.basename(local_path)}",
            daemon=True,
        )
        t.start()

    def _upload(self, local_path: str, key: str) -> None:
        try:
            self._client.upload_file(local_path, config.S3_BUCKET, key)
            log.info("Uploaded %s → s3://%s/%s", local_path, config.S3_BUCKET, key)
        except Exception:  # noqa: BLE001
            log.exception("S3 upload failed for %s (local file kept)", local_path)
