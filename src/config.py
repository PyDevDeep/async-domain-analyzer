import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Automatically load variables from the .env file into the current environment
load_dotenv()


@dataclass(frozen=True)
class Config:
    """
    Configuration data class for the application settings.
    """

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
    EXPORT_SORT_BY_RELEVANCE: bool = (
        os.getenv("EXPORT_SORT_BY_RELEVANCE", "false").lower() == "true"
    )


config = Config()
