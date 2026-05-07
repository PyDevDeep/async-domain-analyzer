import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.cache import CacheManager


@pytest.fixture
def test_db_path(tmp_path: Path) -> str:
    """Generates a temporary path to the database."""
    return str(tmp_path / "test_cache.db")


@pytest.fixture
def temp_cache(test_db_path: str) -> CacheManager:
    """Creates a temporary SQLite database for tests."""
    manager = CacheManager(db_path=test_db_path)
    return manager


def test_cache_set_and_get(temp_cache: CacheManager) -> None:
    """Verifies that set() stores data and get() returns it."""
    test_domain = "example.com"
    test_data = {"score": 100, "status": "success", "priority": "High"}

    temp_cache.set(test_domain, test_data)
    cached = temp_cache.get(test_domain)

    assert cached is not None
    assert cached["score"] == 100
    assert cached["status"] == "success"
    assert cached["priority"] == "High"


def test_cache_is_stale(temp_cache: CacheManager, test_db_path: str) -> None:
    """Verifies that records older than TTL are considered stale and ignored."""
    test_domain = "stale.com"
    test_data = {"score": 50}

    temp_cache.set(test_domain, test_data)

    # Using closing to explicitly close the connection and avoid ResourceWarning
    with closing(sqlite3.connect(test_db_path)) as conn:
        old_time = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        conn.execute(
            "UPDATE domains_cache SET scraped_at = ? WHERE domain = ?", (old_time, test_domain)
        )
        conn.commit()

    cached = temp_cache.get(test_domain)
    assert cached is None


def test_cache_hit_performance(temp_cache: CacheManager) -> None:
    """Verifies cache read performance."""
    test_domain = "perf.com"
    temp_cache.set(test_domain, {"data": "test payload", "score": 90})

    start_time = time.perf_counter()
    cached = temp_cache.get(test_domain)
    duration_ms = (time.perf_counter() - start_time) * 1000

    assert cached is not None
    # Increased to 50ms to avoid flaky tests on Windows/CI
    assert duration_ms < 50.0


def test_cache_delete(temp_cache: CacheManager) -> None:
    """Verifies the record deletion logic (required for rerun-failed)."""
    test_domain = "delete.com"
    temp_cache.set(test_domain, {"status": "error"})
    assert temp_cache.get(test_domain) is not None

    temp_cache.delete(test_domain)
    assert temp_cache.get(test_domain) is None
