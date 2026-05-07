import pytest

from src.retry import async_retry


async def test_retry_success_first_try() -> None:
    """Verifies that the function executes successfully on the first attempt without retries."""
    attempts = 0

    @async_retry(max_retries=3, base_delay=0.01)
    async def dummy_func() -> str:
        nonlocal attempts
        attempts += 1
        return "success"

    result = await dummy_func()
    assert result == "success"
    assert attempts == 1


async def test_retry_success_after_failures() -> None:
    """Verifies that the function retries on a specified error and returns a result."""
    attempts = 0

    @async_retry(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
    async def dummy_func() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("Temporary failure")
        return "success"

    result = await dummy_func()
    assert result == "success"
    assert attempts == 3


async def test_retry_max_retries_exceeded() -> None:
    """Verifies that after max retries are exceeded, the error propagates upwards."""
    attempts = 0

    @async_retry(max_retries=2, base_delay=0.01, exceptions=(ValueError,))
    async def dummy_func() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("Persistent failure")

    with pytest.raises(ValueError, match="Persistent failure"):
        await dummy_func()

    assert attempts == 2


async def test_retry_unhandled_exception() -> None:
    """Verifies that errors not in the exceptions tuple do not trigger retry (Fail-fast)."""
    attempts = 0

    @async_retry(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
    async def dummy_func() -> None:
        nonlocal attempts
        attempts += 1
        raise TypeError("Unexpected error")

    with pytest.raises(TypeError, match="Unexpected error"):
        await dummy_func()

    assert attempts == 1
