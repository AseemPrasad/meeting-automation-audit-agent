"""Circuit breaker for LLM providers.

Tracks success/failure outcomes over a rolling time window and opens the
circuit when the error rate exceeds the configured threshold, stopping
downstream traffic to the failing provider. After a cooldown the circuit
goes half-open and allows a single trial request to probe recovery.
"""

import threading
import time
from collections import deque


class CircuitOpenError(Exception):
    """Raised when a request is attempted while the circuit is open."""


class CircuitBreaker:
    """Thread-safe circuit breaker with a rolling error-rate window."""

    def __init__(
        self,
        error_threshold: float = 0.5,
        window_seconds: float = 60.0,
        cooldown_seconds: float = 30.0,
    ):
        self.error_threshold = error_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._outcomes: deque = deque()  # (timestamp, is_success)
        self._state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._last_failure_time: float | None = None

    # -- state helpers -------------------------------------------------
    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._outcomes and self._outcomes[0][0] < cutoff:
            self._outcomes.popleft()

    def _error_rate(self, now: float) -> float:
        self._prune(now)
        if not self._outcomes:
            return 0.0
        failures = sum(1 for _, ok in self._outcomes if not ok)
        return failures / len(self._outcomes)

    # -- public API ----------------------------------------------------
    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        """Return True if a request may proceed, False if circuit is open."""
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if self._state == "OPEN":
                # After cooldown, allow a single probe (half-open)
                if (
                    self._last_failure_time is not None
                    and now - self._last_failure_time >= self.cooldown_seconds
                ):
                    self._state = "HALF_OPEN"
                    return True
                return False
            if self._state == "HALF_OPEN":
                # Only one trial request is allowed at a time; once a
                # request is in flight we keep the state so subsequent
                # callers are blocked until the probe completes.
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._outcomes.append((now, True))
            self._prune(now)
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                self._last_failure_time = None

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._outcomes.append((now, False))
            self._prune(now)
            self._last_failure_time = now
            rate = self._error_rate(now)
            if rate > self.error_threshold or self._state == "HALF_OPEN":
                self._state = "OPEN"
            elif self._state == "CLOSED":
                self._state = "OPEN" if rate > self.error_threshold else "CLOSED"

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        with self._lock:
            return (
                f"CircuitBreaker(state={self._state}, "
                f"error_rate={self._error_rate(time.monotonic()):.2f})"
            )

