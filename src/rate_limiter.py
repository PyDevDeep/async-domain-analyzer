import asyncio
import time

from src.logger import logger


class SerperRateLimiter:
    """
    Rate limiter with Token Bucket algorithm for QPS control
    and Circuit Breaker for API budget protection.
    """

    def __init__(self, max_qps: float = 2.0, max_credits: int = 2000):
        self.max_qps: float = max_qps
        self.max_credits: int = max_credits
        self.tokens: float = max_qps
        self.last_refill: float = time.monotonic()

        self.credits_used: int = 0
        self.circuit_breaker_tripped: bool = False
        self.lock: asyncio.Lock = asyncio.Lock()

    def _refill(self) -> None:
        """Replenishes tokens based on the elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_qps, self.tokens + elapsed * self.max_qps)
        self.last_refill = now

    async def acquire(self, estimated_cost: int = 5) -> bool:
        """
        Acquires a token to execute the request.
        Returns False if the budget is exhausted (Circuit Breaker tripped).
        """
        async with self.lock:
            if self.circuit_breaker_tripped:
                return False

            if self.credits_used + estimated_cost > self.max_credits:
                logger.critical(
                    "Serper budget near exhaustion, circuit breaker tripped",
                    credits_used=self.credits_used,
                    max_credits=self.max_credits,
                    attempted_cost=estimated_cost,
                )
                self.circuit_breaker_tripped = True
                return False

            while self.tokens < 1.0:
                self._refill()
                if self.tokens < 1.0:
                    # Yielding control to the event loop for a short pause
                    await asyncio.sleep(0.1)

            self.tokens -= 1.0
            self.credits_used += estimated_cost
            return True

    async def record_actual_cost(self, actual_cost: int, estimated_cost: int = 5) -> None:
        """
        Adjusts actual costs after request execution,
        if the Serper API returned a different cost.
        """
        async with self.lock:
            difference = actual_cost - estimated_cost
            self.credits_used += difference


# Global limiter instance for use in workers
serper_limiter = SerperRateLimiter()
