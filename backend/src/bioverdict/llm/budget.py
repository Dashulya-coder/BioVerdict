"""Per-run spending cap. Thread-safe: reasoning agents run in parallel."""

from __future__ import annotations

import threading

from bioverdict.llm.errors import BudgetExceededError

_NO_RUN = "-"


class Budget:
    def __init__(self, cap_usd: float) -> None:
        self._cap = cap_usd
        self._spent: dict[str, float] = {}
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
