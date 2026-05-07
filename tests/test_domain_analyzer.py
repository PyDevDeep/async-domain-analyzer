from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.config import config
from src.domain_analyzer import analyze_domain


@pytest.fixture
def mock_pass1():
    """Mocking all Pass 1 (Native Scraper) dependencies."""
    with (
        patch("src.domain_analyzer.get_final_url", new_callable=AsyncMock) as m_url,
        patch("src.domain_analyzer.fetch_url", new_callable=AsyncMock) as m_fetch,
        patch("src.domain_analyzer.get_domain_age") as m_age,
        patch("src.domain_analyzer.check_ssl_certificate") as m_ssl,
        patch("src.domain_analyzer.analyze_html_content") as m_html,
    ):
        yield m_url, m_fetch, m_age, m_ssl, m_html


@pytest.fixture
def mock_pass2():
    """Mocking Pass 2 (Serper Fallback) dependencies."""
    with patch("src.domain_analyzer.scrape_with_serper", new_callable=AsyncMock) as m_serper:
        yield m_serper


async def test_analyze_domain_pass1_success(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies successful execution of Pass 1 without triggering Pass 2."""
    m_url, m_fetch, m_age, m_ssl, m_html = mock_pass1
    m_serper = mock_pass2

    domain = "success.com"
    m_url.return_value = f"https://{domain}"
    m_fetch.return_value = (200, "<html>Mock</html>", 150.0)
    m_age.return_value = 500
    m_ssl.return_value = {"valid": True, "days_until_expiry": 30}
    m_html.return_value = {
        "has_live_content": True,
        "title": "Success",
        "meta_description": "Desc",
        "word_count": 200,
    }

    async with aiohttp.ClientSession() as session:
        result = await analyze_domain(session, domain, config)

    assert result["domain"] == domain
    assert result["fallback_used"] is False
    assert result["status"] == "success"
    assert result["has_live_content"] is True
    # Pass 2 should not be called
    m_serper.assert_not_called()


async def test_analyze_domain_pass1_fails_pass2_success(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies that the absence of live content in Pass 1 triggers Pass 2 (Fallback)."""
    m_url, m_fetch, m_age, m_ssl, m_html = mock_pass1
    m_serper = mock_pass2

    domain = "fallback.com"
    m_url.return_value = f"https://{domain}"

    # Simulating a successful HTTP request but an empty page (e.g., JS rendering)
    m_fetch.return_value = (200, "<html>JS Load</html>", 100.0)
    m_age.return_value = 100
    m_ssl.return_value = {"valid": True, "days_until_expiry": 30}
    m_html.return_value = {
        "has_live_content": False,
        "title": "Loading...",
        "meta_description": None,
        "word_count": 10,
    }

    m_serper.return_value = {
        "status": "success",
        "has_live_content": True,
        "title": "Fallback Title",
        "meta_description": "Fallback Desc",
        "word_count": 300,
        "credits_used": 2,
    }

    async with aiohttp.ClientSession() as session:
        result = await analyze_domain(session, domain, config)

    assert result["fallback_used"] is True
    assert result["has_live_content"] is True
    assert result["html_title"] == "Fallback Title"
    assert result["credits_used"] == 2
    assert result["status"] == "success"
    m_serper.assert_called_once()


async def test_analyze_domain_both_fail(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies error aggregation when both passes fail."""
    m_url, m_fetch, *_ = mock_pass1
    m_serper = mock_pass2

    domain = "fail.com"
    # Pass 1: Network timeout
    m_url.return_value = f"https://{domain}"
    m_fetch.return_value = (None, "", None)

    # Pass 2: API Failure
    m_serper.return_value = {"status": "error", "reason": "Serper Rate Limit"}

    async with aiohttp.ClientSession() as session:
        result = await analyze_domain(session, domain, config)

    assert result["fallback_used"] is True
    assert result["status"] == "error"
    assert "All scraping methods failed" in result["error"]
    assert "Network timeout" in result["error"]
    assert "Serper Rate Limit" in result["error"]


async def test_analyze_domain_resolution_failure(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies fail-fast for non-existent domains (NXDOMAIN)."""
    m_url, *_ = mock_pass1
    m_serper = mock_pass2

    domain = "nxdomain.local"
    # Simulating the inability to determine final_url
    m_url.return_value = None

    m_serper.return_value = {"status": "error", "reason": "Unreachable"}

    async with aiohttp.ClientSession() as session:
        result = await analyze_domain(session, domain, config)

    assert result["status"] == "error"
    assert "Failed to resolve domain" in result["error"]
    assert result["fallback_used"] is True


async def test_analyze_domain_serper_value_error(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies that ValueError (Invalid API Key) propagates upward and crashes the flow."""
    m_url, m_fetch, *_ = mock_pass1
    m_serper = mock_pass2

    domain = "fail-fast.com"
    m_url.return_value = f"https://{domain}"
    m_fetch.return_value = (None, "", None)

    # Pass 2 raises an error instead of returning a dictionary
    m_serper.side_effect = ValueError("Invalid Serper API key")

    async with aiohttp.ClientSession() as session:
        with pytest.raises(ValueError, match="Invalid Serper API key"):
            await analyze_domain(session, domain, config)


async def test_analyze_domain_no_api_key_graceful_degradation(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies that the absence of the Serper key ignores Pass 2 (Graceful Degradation)."""
    m_url, m_fetch, m_age, m_ssl, m_html = mock_pass1
    m_serper = mock_pass2

    domain = "no-key.com"
    m_url.return_value = f"https://{domain}"
    # Simulating an empty site that requires a fallback
    m_fetch.return_value = (200, "<html>Empty</html>", 100.0)
    m_age.return_value = 100
    m_ssl.return_value = {"valid": True, "days_until_expiry": 30}
    m_html.return_value = {
        "has_live_content": False,
        "title": None,
        "meta_description": None,
        "word_count": 0,
    }

    # Creating an isolated config with an empty key
    no_key_config = replace(config, SERPER_API_KEY="")

    async with aiohttp.ClientSession() as session:
        # Passing no_key_config instead of the global one
        result = await analyze_domain(session, domain, no_key_config)

    # Verifying that Serper was not called at all
    m_serper.assert_not_called()
    assert result["fallback_used"] is False
    assert "Pass2 Skipped: No API Key" in result["error"]


async def test_analyze_domain_no_api_key_and_pass1_fails(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies graceful degradation when Pass 1 also fails (lines 106-107)."""

    m_url, m_fetch, *_ = mock_pass1
    m_serper = mock_pass2

    domain = "total-fail-no-key.com"
    m_url.return_value = f"https://{domain}"

    # Pass 1 fails (e.g., timeout or connection drop)
    m_fetch.return_value = (None, "", None)

    # Creating an isolated config with an empty key
    no_key_config = replace(config, SERPER_API_KEY="")

    async with aiohttp.ClientSession() as session:
        result = await analyze_domain(session, domain, no_key_config)

    # Verifying that Serper was not called, but the error was recorded correctly
    m_serper.assert_not_called()
    assert result["fallback_used"] is False
    assert "All scraping methods failed" in result["error"]
    assert "Pass2 Skipped: No API Key" in result["error"]


async def test_analyze_domain_pass2_generic_exception(
    mock_pass1: tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, MagicMock],
    mock_pass2: AsyncMock,
) -> None:
    """Verifies catching unexpected errors in Pass 2 (lines 136-140)."""
    m_url, m_fetch, m_age, m_ssl, m_html = mock_pass1
    m_serper = mock_pass2

    domain = "pass2-boom.com"
    m_url.return_value = f"https://{domain}"

    # Pass 1 finished (HTTP 200), but with empty content (trigger for Pass 2)
    m_fetch.return_value = (200, "<html>Empty</html>", 100.0)
    m_age.return_value = 100
    m_ssl.return_value = {"valid": True, "days_until_expiry": 30}
    m_html.return_value = {
        "has_live_content": False,
        "title": None,
        "meta_description": None,
        "word_count": 0,
    }

    # Pass 2 throws an unexpected error instead of a standard ValueError
    m_serper.side_effect = TypeError("Unexpected data structure")

    async with aiohttp.ClientSession() as session:
        result = await analyze_domain(session, domain, config)

    # Verifying that the script did not crash and correctly saved the Exception
    assert result["fallback_used"] is True

    # Status "success" because Pass 1 returned HTTP 200 (scorer does not consider this a critical failure)
    assert result["status"] == "success"

    # Key point: Pass 2 error successfully logged in the error field
    assert "Pass2 Exception: TypeError" in result["error"]
