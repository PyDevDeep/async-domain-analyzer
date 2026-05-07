from dataclasses import replace

import aiohttp
import pytest
from aioresponses import aioresponses

from src.config import config
from src.scraper_pass2 import scrape_with_serper


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch):
    """Creates a new instance of config and replaces it in the module."""
    # Create a copy of the object with a different key (legal way for frozen)
    new_config = replace(config, SERPER_API_KEY="test_key_123")

    # Replace config EXACTLY where it's imported (in the scraper)
    monkeypatch.setattr("src.scraper_pass2.config", new_config)


async def test_serper_success(mock_env: None) -> None:
    """Verifies successful parsing of valid JSON from Serper."""
    domain = "test-live.com"
    url = "https://scrape.serper.dev"

    mock_payload = {
        "text": "This is a simulated live content string with sufficient words. " * 10,
        "metadata": {"title": "Mock Title", "description": "Mock Description"},
        "credits": 2,
    }

    with aioresponses() as m:
        m.post(url, payload=mock_payload, status=200)  # type: ignore[reportUnknownMemberType]

        async with aiohttp.ClientSession() as session:
            result = await scrape_with_serper(session, domain)

    assert result["status"] == "success"
    assert result["has_live_content"] is True
    assert result["title"] == "Mock Title"
    assert result["credits_used"] == 2


async def test_serper_invalid_api_key_fail_fast(mock_env: None) -> None:
    """Verifies that HTTP 401 raises ValueError and crashes the script (Fail-fast)."""
    domain = "test-401.com"
    url = "https://scrape.serper.dev"

    with aioresponses() as m:
        m.post(url, status=401)  # type: ignore[reportUnknownMemberType]

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="Invalid Serper API key"):
                await scrape_with_serper(session, domain)


async def test_serper_rate_limit(mock_env: None) -> None:
    """Verifies that HTTP 429 returns an error without executing retry."""
    domain = "test-429.com"
    url = "https://scrape.serper.dev"

    with aioresponses() as m:
        m.post(url, status=429)  # type: ignore[reportUnknownMemberType]

        async with aiohttp.ClientSession() as session:
            result = await scrape_with_serper(session, domain)

    assert result["status"] == "error"
    assert result["reason"] == "Rate limit exceeded"
    assert result["credits_used"] == 0


async def test_serper_invalid_schema(mock_env: None) -> None:
    """Verifies handling of a response where required fields are missing."""
    domain = "test-schema.com"
    url = "https://scrape.serper.dev"

    invalid_payload = {"text": "Some text"}

    with aioresponses() as m:
        m.post(url, payload=invalid_payload, status=200)  # type: ignore[reportUnknownMemberType]

        async with aiohttp.ClientSession() as session:
            result = await scrape_with_serper(session, domain)

    assert result["status"] == "error"
    assert result["reason"] == "Invalid API response schema"
