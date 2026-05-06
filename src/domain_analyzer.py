import asyncio
from typing import Any

import aiohttp

from src.config import Config
from src.logger import logger
from src.scraper_pass1 import (
    analyze_html_content,
    check_ssl_certificate,
    fetch_url,
    get_domain_age,
    get_final_url,
)


async def analyze_domain(
    session: aiohttp.ClientSession, domain: str, config: Config
) -> dict[str, Any]:
    """Агрегує метадані з Pass 1 для вказаного домену."""
    result: dict[str, Any] = {
        "domain": domain,
        "final_url": None,
        "status_code": None,
        "response_time_ms": None,
        "ssl_valid": False,
        "ssl_days_until_expiry": None,
        "domain_age_days": None,
        "has_live_content": False,
        "html_title": None,
        "word_count": 0,
        "error": None,
    }

    try:
        # Starting asynchronous and synchronous tasks in parallel where possible
        # get_domain_age and check_ssl_certificate are blocking, so in production
        # it's better to offload them to ThreadPoolExecutor. For MVP, we call them synchronously.

        loop = asyncio.get_running_loop()
        domain_age = await loop.run_in_executor(None, get_domain_age, domain)
        ssl_data = await loop.run_in_executor(None, check_ssl_certificate, domain)

        result["domain_age_days"] = domain_age
        result["ssl_valid"] = ssl_data.get("valid", False)
        result["ssl_days_until_expiry"] = ssl_data.get("days_until_expiry")

        # Determining the final URL and fetching HTML
        final_url = await get_final_url(session, domain)
        if not final_url:
            raise Exception("Failed to resolve domain via HTTP/HTTPS")

        result["final_url"] = final_url

        status_code, html_body, latency = await fetch_url(
            session, final_url, req_timeout=config.HTTP_TIMEOUT_TOTAL
        )

        result["status_code"] = status_code
        result["response_time_ms"] = round(latency, 2)

        # HTML Analysis
        html_metadata = analyze_html_content(html_body)
        result["has_live_content"] = html_metadata["has_live_content"]
        result["html_title"] = html_metadata["title"]
        result["word_count"] = html_metadata["word_count"]

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e!s}"
        logger.warning("Domain analysis failed", domain=domain, error=str(e))

    return result
