import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # API Credentials
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")

    # Processing limits
    DEFAULT_WORKERS: int = 5

    # SQLite Cache config
    CACHE_DB_PATH: str = "data/cache.db"
    CACHE_TTL_DAYS: int = 7

    # HTTP Client Timeout settings (aiohttp)
    HTTP_TIMEOUT_TOTAL: int = 10
    HTTP_TIMEOUT_CONNECT: int = 3
    HTTP_TIMEOUT_SOCK_READ: int = 5

    # I/O Directories
    OUTPUT_DIR: str = "data"


config = Config()
