from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import psutil


@dataclass
class Benchmark:
    stages: dict[str, float] = field(default_factory=dict)
    peak_rss_bytes: int = 0
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample_memory, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _sample_memory(self) -> None:
        process = psutil.Process(os.getpid())
        while not self._stop.wait(0.2):
            try:
                processes = [process, *process.children(recursive=True)]
                rss = sum(item.memory_info().rss for item in processes if item.is_running())
                self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
            except (psutil.Error, OSError):
                pass

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + time.perf_counter() - started

