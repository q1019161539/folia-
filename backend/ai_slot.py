"""One slot for the work that needs the big models.

This box has 16GB. The kernel OOM dump from 2026-09-17 caught two of these jobs
together: the ASR subprocess at 7.7GB beside the model container at 3.9GB, 14.4GB
of process memory in total, and the ASR was killed. Nothing stopped them
overlapping -- the per-job task registry is per job, so an alignment started from
the web UI, or by a job re-queued after a container restart, lands straight on
top of a running ASR. The transcriber does unload the models before ASR begins,
but that is one moment at the start; the half hour that follows is wide open.

Everything that loads Whisper or the Qwen aligner takes this slot: the pipeline's
whole-recording ASR, per-song forced alignment, and manual recognition from the
UI. Waiting here is ordinary queueing, so it is surfaced through job status and
the queue view -- never as a push notification, which for a run with a dozen
songs would mean a dozen messages.
"""
from __future__ import annotations

import contextlib
import threading
import time
import uuid
from typing import Any, Callable

WAIT_NOTICE_SECONDS = 60
# How often a waiter wakes to re-check. The notice can only fire on one of these
# wake-ups, so a coarse interval would push a "60 second" notice out past 65.
POLL_SECONDS = 1.0

_lock = threading.Lock()
_state: dict[str, Any] = {"holder": "", "since": 0.0, "waiting": {}}


def busy() -> bool:
    return _lock.locked()


def snapshot() -> dict[str, Any]:
    """Who holds the slot and who is behind them, for the queue view."""
    now = time.time()
    waiting = [
        {"label": item["label"], "seconds": round(now - item["since"])}
        for item in list(_state["waiting"].values())
    ]
    waiting.sort(key=lambda item: -item["seconds"])
    held = _state["since"]
    return {
        "busy": _lock.locked(),
        "holder": _state["holder"],
        "held_seconds": round(now - held) if held else 0,
        "waiting": waiting,
    }


@contextlib.contextmanager
def occupy(label: str = "", on_wait: Callable[[float], None] | None = None):
    """Take the slot, waiting as long as necessary. Yields how long it waited.

    on_wait fires once, after WAIT_NOTICE_SECONDS, so a caller can show that it
    is queueing rather than stuck. A failing callback must not cost the caller
    its turn, so it is swallowed.
    """
    started = time.time()
    ticket = uuid.uuid4().hex[:8]
    _state["waiting"][ticket] = {"label": label, "since": started}
    announced = False
    try:
        while not _lock.acquire(timeout=POLL_SECONDS):
            if on_wait and not announced and time.time() - started >= WAIT_NOTICE_SECONDS:
                announced = True
                try:
                    on_wait(time.time() - started)
                except Exception:
                    pass
    finally:
        _state["waiting"].pop(ticket, None)
    _state["holder"], _state["since"] = label, time.time()
    try:
        yield round(time.time() - started, 1)
    finally:
        _state["holder"], _state["since"] = "", 0.0
        _lock.release()
