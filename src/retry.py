import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import aiohttp

from src.logger import logger

# TypeVar to preserve the types of the original function
T = TypeVar("T")


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple[type[Exception], ...] = (
        aiohttp.ClientError,
        asyncio.TimeoutError,
    ),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for asynchronous functions that implements exponential backoff retry.

    Args:
        max_retries: Maximum number of retries.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds (to avoid excessively long pauses).
        exceptions: Tuple of exceptions for which retry occurs.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            "Max retries reached, failing",
                            func=func.__name__,
                            attempt=attempt,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        raise

                    logger.warning(
                        "Function execution failed, retrying",
                        func=func.__name__,
                        attempt=attempt,
                        delay=delay,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

                    await asyncio.sleep(delay)
                    # Exponential backoff with max_delay limit
                    delay = min(delay * 2, max_delay)

            # Theoretically unreachable code due to raise in the loop,
            # but necessary for the type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry state")

        return wrapper

    return decorator
