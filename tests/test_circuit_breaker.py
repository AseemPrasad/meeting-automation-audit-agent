"""Tests for the LLM circuit breaker (no external calls)."""

import time

from worker.services.llm.circuit_breaker import CircuitBreaker


def test_allows_initial_requests():
    cb = CircuitBreaker()
    assert cb.allow_request() is True
    assert cb.state == "CLOSED"


def test_trips_open_above_error_threshold():
    cb = CircuitBreaker(error_threshold=0.5, window_seconds=60)
    # Two failures out of two calls -> 100% error -> trip open
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False


def test_does_not_trip_below_threshold():
    cb = CircuitBreaker(error_threshold=0.5, window_seconds=60)
    # 1 failure, 3 successes -> 25% error -> stays CLOSED
    cb.record_success()
    cb.record_success()
    cb.record_success()
    cb.record_failure()
    assert cb.state == "CLOSED"


def test_half_open_after_cooldown():
    cb = CircuitBreaker(
        error_threshold=0.5, window_seconds=60, cooldown_seconds=0.1
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    time.sleep(0.2)
    # After cooldown, first probe is allowed (HALF_OPEN path)
    assert cb.allow_request() is True
    assert cb.state == "HALF_OPEN"


def test_success_closes_half_open():
    cb = CircuitBreaker(
        error_threshold=0.5, window_seconds=60, cooldown_seconds=0.1
    )
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.2)
    cb.allow_request()  # transitions to HALF_OPEN
    cb.record_success()  # probe succeeds -> back to CLOSED
    assert cb.state == "CLOSED"


def test_expired_window_resets_error_rate():
    cb = CircuitBreaker(
        error_threshold=0.5, window_seconds=0.1, cooldown_seconds=0.1
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    time.sleep(0.3)
    # Old failures age out of the 60s window, allowing requests again
    assert cb.allow_request() is True

