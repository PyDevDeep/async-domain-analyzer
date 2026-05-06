import ssl
from typing import Any

import aiohttp
import certifi
import chardet
from bs4 import BeautifulSoup

from src.config import config
from src.logger import logger
from src.retry import async_retry

# SSL/TLS verification using certifi
ssl_context = ssl.create_default_context(cafile=certifi.where())

# Timeouts are initialized according to the configuration
client_timeout = aiohttp.ClientTimeout(
    total=config.HTTP_TIMEOUT_TOTAL,
    connect=config.HTTP_TIMEOUT_CONNECT,
    sock_read=config.HTTP_TIMEOUT_SOCK_READ,
)


@async_retry(max_retries=2, base_delay=1.0)
async def fetch_url(session: aiohttp.ClientSession, url: str) -> tuple[int, bytes, str]:
    """Performs an HTTP GET request with retry support and configured timeouts."""
    logger.debug("Fetching URL via Pass 1", url=url)
    async with session.get(
        url, timeout=client_timeout, ssl=ssl_context, allow_redirects=True
    ) as response:
        status = response.status
        content_type = response.headers.get("Content-Type", "").lower()
        content = await response.read()
        return status, content, content_type


def analyze_html_content(raw_bytes: bytes, url: str) -> dict[str, Any]:
    """Аналізує HTML контент, обробляє кодування та витягує метадані."""
    try:
        # Automatic encoding detection
        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding") or "utf-8"
        html_text = raw_bytes.decode(encoding, errors="ignore")

        soup = BeautifulSoup(html_text, "html.parser")

        title_tag = soup.find("title")
        title = title_tag.text.strip() if title_tag else ""

        text_content = soup.get_text(separator=" ", strip=True)
        word_count = len(text_content.split())

        return {
            "title": title,
            "word_count": word_count,
            "has_live_content": word_count > 50,
        }
    except Exception as e:
        logger.warning("HTML parsing failed", url=url, error=str(e))
        return {"title": "", "word_count": 0, "has_live_content": False, "parse_error": str(e)}


async def scrape_domain_pass1(domain: str) -> dict[str, Any]:
    """Orchestrates Pass 1 of scraping for a given domain."""
    url = f"https://{domain}"
    result = {
        "domain": domain,
        "final_url": url,
        "status": "success",
        "reason": "",
        "title": "",
        "word_count": 0,
        "has_live_content": False,
    }

    try:
        async with aiohttp.ClientSession() as session:
            status_code, raw_bytes, content_type = await fetch_url(session, url)

            if status_code != 200:
                result["status"] = "error"
                result["reason"] = f"Non-200 status code: {status_code}"
                return result

            if "text/html" not in content_type:
                result["status"] = "error"
                result["reason"] = f"Invalid Content-Type: {content_type}"
                return result

            parsed_data = analyze_html_content(raw_bytes, url)
            result.update(parsed_data)

    except aiohttp.ClientError as e:
        result["status"] = "error"
        result["reason"] = f"ClientError: {type(e).__name__}"
        logger.warning("Pass 1 failed due to network error", domain=domain, error=str(e))
    except Exception as e:
        result["status"] = "error"
        result["reason"] = f"Exception: {type(e).__name__} - {e!s}"
        logger.error("Pass 1 unexpected failure", domain=domain, error=str(e))

    return result
