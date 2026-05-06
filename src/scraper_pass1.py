import socket
import ssl
import time
from datetime import UTC, datetime
from typing import Any, cast

import aiohttp
import certifi
import chardet
import whois  # type: ignore[reportMissingTypeStubs]
from bs4 import BeautifulSoup

from src.logger import logger
from src.retry import async_retry


async def fetch_url(
    session: aiohttp.ClientSession, url: str, req_timeout: int
) -> tuple[int, str, float]:
    """Performs an HTTP GET request, returns status, body, and latency"""
    start_time = time.perf_counter()
    client_timeout = aiohttp.ClientTimeout(total=req_timeout)

    try:
        async with session.get(url, timeout=client_timeout) as response:
            status_code = response.status
            raw_bytes = await response.read()

            # Auto-detect encoding
            detected = chardet.detect(raw_bytes)
            encoding = detected.get("encoding") or "utf-8"
            html_body = raw_bytes.decode(encoding, errors="ignore")

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info("HTTP fetch complete", url=url, status=status_code, latency_ms=latency_ms)

            return status_code, html_body, latency_ms
    except Exception as e:
        logger.error("HTTP fetch failed", url=url, error=str(e))
        raise


def check_ssl_certificate(domain: str) -> dict[str, Any]:
    """Checks the validity of the SSL certificate."""
    result: dict[str, Any] = {
        "valid": False,
        "issuer": None,
        "expires_at": None,
        "days_until_expiry": None,
    }
    context = ssl.create_default_context(cafile=certifi.where())
    context.check_hostname = True

    try:
        with (
            socket.create_connection((domain, 443), timeout=5) as sock,
            context.wrap_socket(sock, server_hostname=domain) as ssl_sock,
        ):
            cert = ssl_sock.getpeercert()
            if cert:
                # Parse issuer
                issuer_tuples = cert.get("issuer", ())
                for item in issuer_tuples:
                    for key, value in item:
                        if key == "organizationName":
                            result["issuer"] = value

                # Parse expiry
                not_after_str = cert.get("notAfter")
                if isinstance(not_after_str, str):
                    # Format: 'Jan 15 12:00:00 2025 GMT'
                    expires_at = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(
                        tzinfo=UTC
                    )
                    result["expires_at"] = expires_at.isoformat()
                    days_until_expiry = (expires_at - datetime.now(UTC)).days
                    result["days_until_expiry"] = days_until_expiry
                    result["valid"] = days_until_expiry > 0

    except (OSError, ssl.SSLError, Exception) as e:
        logger.debug("SSL check failed", domain=domain, error=str(e))

    return result


def get_domain_age(domain: str) -> int | None:
    """Retrieves domain age in days via WHOIS."""
    try:
        whois_data: Any = whois.whois(domain)
        raw_date: Any = getattr(whois_data, "creation_date", None)

        if not raw_date:
            return None

        dates: list[Any] = cast(list[Any], raw_date) if isinstance(raw_date, list) else [raw_date]
        # Concise search for the first datetime object
        creation_date: datetime | None = next(
            (item for item in dates if isinstance(item, datetime)), None
        )

        if creation_date is None:
            return None

        # Converting to a unified timezone-aware format (UTC) to avoid logical bugs
        if creation_date.tzinfo is None:
            creation_date = creation_date.replace(tzinfo=UTC)

        # datetime.now(timezone.utc) is guaranteed to be aware, subtracting aware from aware
        age_days = (datetime.now(UTC) - creation_date).days
        return age_days

    except Exception as e:
        logger.warning("WHOIS lookup failed", domain=domain, error=str(e))
        return None


def analyze_html_content(html: str) -> dict[str, Any]:
    """Parses HTML, extracts SEO metrics and the presence of live content."""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_desc_tag = soup.find("meta", {"name": "description"})
    meta_description = meta_desc_tag.get("content") if meta_desc_tag else None

    word_count = len(soup.get_text(separator=" ", strip=True).split())
    has_forms = len(soup.find_all("form")) > 0
    has_images = len(soup.find_all("img")) > 0

    has_live_content = (word_count > 100) and (has_forms or has_images)

    return {
        "has_live_content": has_live_content,
        "title": title,
        "meta_description": meta_description,
        "word_count": word_count,
        "has_forms": has_forms,
        "has_images": has_images,
    }


@async_retry(max_retries=2, base_delay=1.0)
async def get_final_url(session: aiohttp.ClientSession, domain: str) -> str | None:
    """Determines the final URL after redirects, starting with HTTPS"""
    head_timeout = aiohttp.ClientTimeout(total=5)
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            async with session.head(url, allow_redirects=True, timeout=head_timeout) as resp:
                return str(resp.url)
        except Exception as e:
            logger.debug("Head request failed", url=url, error=str(e))
            continue
    return None
