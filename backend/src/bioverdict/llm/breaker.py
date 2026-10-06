"""Circuit breaker per provider: stop calling a provider that keeps failing, for a few minutes."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 3,
        cooldown_s: float = 180.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_open(self, provider: str) -> bool:
        """True while the provider is skipped. After the cooldown it gets one trial call."""
        with self._lock:
            opened = self._opened_at.get(provider)
            if opened is None:
                return False
            if self._clock() - opened >= self._cooldown_s:
                del self._opened_at[provider]  # half-open: allow a trial
                self._failures[provider] = self._threshold - 1  # one more failure reopens it
                return False
            return True

    def record_failure(self, provider: str) -> None:
        with self._lock:
            count = self._failures.get(provider, 0) + 1
            self._failures[provider] = count
            if count >= self._threshold:
                self._opened_at[provider] = self._clock()

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._failures.pop(provider, None)
            self._opened_at.pop(provider, None)
