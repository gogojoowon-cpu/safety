"""Unit tests for ring buffer + incident recorder.

VideoWriter 가 호스트 환경(코덱 부재 등)에 따라 실패할 수 있으므로,
`confirm`/`discard` 의 부수효과만 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from core.incident_recorder import IncidentRecorder, IncidentRecState  # noqa: E402
from core.ring_buffer import FrameRingBuffer  # noqa: E402


def _blank_frame() -> np.ndarray:
    return np.zeros((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), dtype=np.uint8)


def test_ring_buffer_keeps_recent():
    rb = FrameRingBuffer(seconds=2.0, fps=10)  # capacity = 20
    for i in range(50):
        rb.push(_blank_frame(), timestamp=float(i))
    assert len(rb) <= rb.capacity == 20
    snap = rb.snapshot()
    assert len(snap) == 20
    assert snap[-1].timestamp == 49.0


def test_discard_on_false_alarm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECORD_DIR", str(tmp_path))

    rec = IncidentRecorder()
    # Feed a few idle frames into the prebuffer so the writer has something to flush.
    for i in range(5):
        rec.feed_idle_frame(_blank_frame(), now=float(i))

    rec.start_on_suspected(now=5.0)
    if rec.state != IncidentRecState.RECORDING:
        pytest.skip("VideoWriter unavailable in this environment (missing codec)")

    rec.feed_recording_frame(_blank_frame(), now=5.1)
    path = rec._current_path
    assert path is not None
    assert path.exists()

    rec.discard()

    assert rec.state == IncidentRecState.IDLE
    assert not path.exists()


def test_keep_on_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECORD_DIR", str(tmp_path))

    captured = {}

    def cb(p: str) -> None:
        captured["path"] = p

    rec = IncidentRecorder(on_confirmed=cb)
    for i in range(5):
        rec.feed_idle_frame(_blank_frame(), now=float(i))

    rec.start_on_suspected(now=5.0)
    if rec.state != IncidentRecState.RECORDING:
        pytest.skip("VideoWriter unavailable in this environment (missing codec)")

    expected = str(rec._current_path)
    rec.feed_recording_frame(_blank_frame(), now=5.1)
    saved = rec.confirm()

    assert saved == expected
    assert captured.get("path") == expected
    assert Path(expected).exists()
    assert rec.state == IncidentRecState.IDLE
