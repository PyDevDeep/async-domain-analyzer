import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from src.config import config
from src.logger import logger


class CacheManager:
    """
    SQLite-based Cache Manager for temporary storage of scraping results.
    Uses WAL mode to ensure concurrent I/O
    """

    def __init__(self, db_path: str = config.CACHE_DB_PATH):
        self.db_path = db_path
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        # timeout=30.0 prevents lock contention during concurrent writes
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # WAL mode allows concurrent reads during writes
                cursor.execute("PRAGMA journal_mode=WAL;")

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS domains_cache (
                        domain TEXT PRIMARY KEY,
                        scraped_at TIMESTAMP NOT NULL,
                        metadata JSON NOT NULL
                    )
                    """
                )
                conn.commit()
                logger.info("SQLite schema initialized", db_path=self.db_path)
        except sqlite3.Error as e:
            logger.error("Failed to initialize database schema", error=str(e))
            raise

    def get(self, domain: str) -> dict[str, Any] | None:
        """
        Returns cached metadata for the domain if it is not stale.
        TTL is checked according to config.CACHE_TTL_DAYS (7 days).
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT scraped_at, metadata FROM domains_cache WHERE domain = ?",
                    (domain,),
                )
                row = cursor.fetchone()

                if not row:
                    return None

                # Parsing ISO timestamp from the DB
                scraped_at = datetime.fromisoformat(row["scraped_at"])
                ttl_limit = datetime.now(UTC) - timedelta(days=config.CACHE_TTL_DAYS)

                if scraped_at < ttl_limit:
                    logger.debug(
                        "Cache entry stale", domain=domain, scraped_at=scraped_at.isoformat()
                    )
                    self.delete(domain)
                    return None

                logger.debug("Cache hit", domain=domain)
                return json.loads(row["metadata"])

        except sqlite3.Error as e:
            logger.error("Failed to get cache entry", domain=domain, error=str(e))
            return None

    def set(self, domain: str, metadata: dict[str, Any]) -> None:
        """
        Saves or updates metadata for the domain.
        """
        now = datetime.now(UTC).isoformat()
        metadata_json = json.dumps(metadata)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO domains_cache (domain, scraped_at, metadata)
                    VALUES (?, ?, ?)
                    ON CONFLICT(domain) DO UPDATE SET
                        scraped_at=excluded.scraped_at,
                        metadata=excluded.metadata
                    """,
                    (domain, now, metadata_json),
                )
                conn.commit()
                logger.debug("Cache set", domain=domain)
        except sqlite3.Error as e:
            logger.error("Failed to set cache entry", domain=domain, error=str(e))

    def delete(self, domain: str) -> None:
        """
        Deletes the domain record from the cache (used when clearing stale records).
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM domains_cache WHERE domain = ?", (domain,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to delete cache entry", domain=domain, error=str(e))


cache_manager = CacheManager()
