"""Per-run spending cap. Thread-safe: reasoning agents run in parallel."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from bioverdict.llm.errors import BudgetExceededError, RunTimeoutError

_NO_RUN = "-"


class Budget:
    def __init__(self, cap_usd: float) -> None:
        self._cap = cap_usd
        self._spent: dict[str, float] = {}
        self._held: dict[str, float] = {}  # worst case of the calls that have not answered yet
        self._lock = threading.Lock()

    def spent(self, run_id: str | None) -> float:
        with self._lock:
            return self._spent.get(run_id or _NO_RUN, 0.0)

    def check(self, run_id: str | None) -> None:
        """Raise before a call when the run has already reached its cap."""
        spent = self.spent(run_id)
        if spent >= self._cap:
            raise BudgetExceededError(
                f"run {run_id or '(none)'} spent ${spent:.4f} of its ${self._cap:.2f} cap"
            )

    def charge(self, run_id: str | None, usd: float) -> None:
        with self._lock:
            key = run_id or _NO_RUN
            self._spent[key] = self._spent.get(key, 0.0) + usd

    @contextmanager
    def hold(self, run_id: str | None, worst_case_usd: float) -> Iterator[None]:
        """Admit one call and set aside what it may cost until it has been charged.

        Calls of one run are made in parallel. Checking only what is already spent lets every
        call that starts before the first answer through, and together they can pass the cap by
        the cost of all of them. Here a call starts only while the money spent plus the money
        the calls in flight may still cost is under the cap, so a run passes its cap by at most
        one call. Charge the real cost inside the block; the hold is dropped when it ends.
        """
        key = run_id or _NO_RUN
        with self._lock:
            spent, held = self._spent.get(key, 0.0), self._held.get(key, 0.0)
            if spent + held >= self._cap:
                raise BudgetExceededError(
                    f"run {run_id or '(none)'} spent ${spent:.4f} and has ${held:.4f} in calls "
                    f"under way, of its ${self._cap:.2f} cap"
                )
            self._held[key] = held + worst_case_usd
        try:
            yield
        finally:
            with self._lock:
                self._held[key] = max(self._held.get(key, 0.0) - worst_case_usd, 0.0)


class Deadline:
    """Wall-clock limit per run, counted from the run's first model call.

    Per-call timeouts and retries add up; this is the guarantee that a run still ends in time.
    """

    def __init__(self, limit_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit_s
        self._clock = clock
        self._started: dict[str, float] = {}
        self._lock = threading.Lock()

    def remaining(self, run_id: str | None) -> float:
        with self._lock:
            started = self._started.setdefault(run_id or _NO_RUN, self._clock())
        return self._limit - (self._clock() - started)

    def check(self, run_id: str | None) -> float:
        """Seconds left, or raise when there are none."""
        left = self.remaining(run_id)
        if left <= 0:
            raise RunTimeoutError(
                f"run {run_id or '(none)'} exceeded its {self._limit:.0f} s limit"
            )
        return left
