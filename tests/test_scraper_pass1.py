import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
from aioresponses import aioresponses

from src.scraper_pass1 import (
    analyze_html_content,
    check_ssl_certificate,
    fetch_url,
    get_domain_age,
    get_final_url,
)


async def test_fetch_url_success() -> None:
    """Verifies successful HTTP request and return of status, body, and latency."""
    url = "http://test-fetch.com"
    with aioresponses() as m:
        m_api: Any = m
        m_api.get(url, body="<html>Success</html>", status=200)
        async with aiohttp.ClientSession() as session:
            status, body, latency = await fetch_url(session, url, req_timeout=5)

    assert status == 200
    assert "Success" in body
    assert isinstance(latency, float)


async def test_fetch_url_timeout() -> None:
    """Verifies interception of asyncio.TimeoutError and return of None."""
    url = "http://test-timeout.com"
    async with aiohttp.ClientSession() as session:
        with patch.object(session, "get", side_effect=asyncio.TimeoutError):
            status, body, latency = await fetch_url(session, url, req_timeout=1)

    assert status is None
    assert body == ""
    assert latency is None


async def test_fetch_url_connection_error() -> None:
    """Verifies interception of aiohttp.ClientConnectorError."""
    url = "http://test-conn-error.com"
    async with aiohttp.ClientSession() as session:
        # Simulate a connection error
        error = aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError("Mock Error")
        )
        with patch.object(session, "get", side_effect=error):
            status, _, _ = await fetch_url(session, url, req_timeout=1)

    assert status is None


async def test_get_final_url_https_success() -> None:
    """Verifies determination of the final URL via HTTPS."""
    domain = "secure-site.com"
    with aioresponses() as m:
        m_api: Any = m
        m_api.head(f"https://{domain}", status=200)
        async with aiohttp.ClientSession() as session:
            result = await get_final_url(session, domain)

    assert result == f"https://{domain}"


def test_analyze_html_content_live() -> None:
    """Verifies correct determination of live content (many words + forms/images)."""
    # Generate more than 100 words
    words = " ".join(["word"] * 150)
    html = f"<html><head><title>Live Site</title></head><body><form></form><p>{words}</p></body></html>"

    result = analyze_html_content(html)
    assert result["has_live_content"] is True
    assert result["title"] == "Live Site"
    assert result["has_forms"] is True
    assert result["word_count"] >= 150


def test_analyze_html_content_dead() -> None:
    """Verifies determination of a dead site (few words, no forms/images)."""
    html = "<html><head><title>Parked</title></head><body><p>Domain for sale</p></body></html>"

    result = analyze_html_content(html)
    assert result["has_live_content"] is False
    assert result["title"] == "Parked"
    assert result["has_forms"] is False
    assert result["word_count"] == 4


@patch("src.scraper_pass1.whois.whois")
def test_get_domain_age_success(mock_whois: MagicMock) -> None:
    """Verifies domain age calculation based on WHOIS creation_date."""
    mock_data = MagicMock()
    # Simulate domain creation 500 days ago
    mock_data.creation_date = datetime.now(UTC) - timedelta(days=500)
    mock_whois.return_value = mock_data

    age = get_domain_age("old-domain.com")
    assert age is not None
    assert 499 <= age <= 501


@patch("src.scraper_pass1.socket.create_connection")
@patch("src.scraper_pass1.ssl.create_default_context")
def test_check_ssl_certificate_valid(mock_ssl_context: MagicMock, mock_socket: MagicMock) -> None:
    """Verifies parsing of a valid SSL certificate."""
    future_date = (datetime.now(UTC) + timedelta(days=45)).strftime("%b %d %H:%M:%S %Y %Z")
    mock_cert = {"notAfter": future_date, "issuer": ((("organizationName", "Test CA"),),)}

    mock_ssl_sock = MagicMock()
    mock_ssl_sock.getpeercert.return_value = mock_cert

    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value.__enter__.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    result = check_ssl_certificate("secure.com")
    assert result["valid"] is True
    assert result["issuer"] == "Test CA"
    assert result["days_until_expiry"] >= 44
