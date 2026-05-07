import time

import pytest

from src.rate_limiter import SerperRateLimiter


async def test_limiter_acquire_success() -> None:
    """Verifies basic token acquisition and credit deduction."""
    limiter = SerperRateLimiter(max_qps=10.0, max_credits=100)

    result = await limiter.acquire(estimated_cost=5)

    assert result is True
    assert limiter.credits_used == 5
    assert limiter.circuit_breaker_tripped is False
    assert limiter.tokens < 10.0


async def test_limiter_circuit_breaker() -> None:
    """Verifies that the circuit breaker trips when the budget limit is exhausted."""
    limiter = SerperRateLimiter(max_qps=10.0, max_credits=10)

    res1 = await limiter.acquire(estimated_cost=5)
    assert res1 is True

    res2 = await limiter.acquire(estimated_cost=5)
    assert res2 is True

    res3 = await limiter.acquire(estimated_cost=5)
    assert res3 is False
    assert limiter.circuit_breaker_tripped is True

    res4 = await limiter.acquire(estimated_cost=1)
    assert res4 is False


async def test_limiter_record_actual_cost() -> None:
    """Verifies the compensation (refund) logic if the actual API cost was lower."""
    limiter = SerperRateLimiter(max_qps=10.0, max_credits=100)

    await limiter.acquire(estimated_cost=5)
    assert limiter.credits_used == 5

    await limiter.record_actual_cost(actual_cost=2, estimated_cost=5)
    assert limiter.credits_used == 2


async def test_limiter_refill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies token refill logic over time without breaking encapsulation."""
    limiter = SerperRateLimiter(max_qps=10.0, max_credits=100)

    # Artificially empty the bucket
    limiter.tokens = 0.0

    original_monotonic = time.monotonic

    class TimeMock:
        def __init__(self) -> None:
            self.current = original_monotonic()

        def __call__(self) -> float:
            return self.current

    tm = TimeMock()
    monkeypatch.setattr(time, "monotonic", tm)

    limiter.last_refill = tm.current

    # Simulate passage of 0.5 seconds (at 10 QPS this adds 5 tokens).
    tm.current += 0.5

    # Legal call to a public method, which internally calls _refill()
    await limiter.acquire(estimated_cost=1)

    # Was 0, 5 tokens added, 1 token spent on acquire. Remaining: 4.0.
    assert limiter.tokens == 4.0
