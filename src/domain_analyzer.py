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
from src.scraper_pass2 import scrape_with_serper


async def analyze_domain(
    session: aiohttp.ClientSession, domain: str, config: Config
) -> dict[str, Any]:
    """Оркеструє Pass 1 (BeautifulSoup) та Pass 2 (Serper API fallback)."""
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
        "meta_description": None,
        "word_count": 0,
        "error": None,
        "fallback_used": False,
        "credits_used": 0,
    }

    pass1_success = True

    # --- PASS 1: HTTP & BeautifulSoup ---
    try:
        loop = asyncio.get_running_loop()
        domain_age = await loop.run_in_executor(None, get_domain_age, domain)
        ssl_data = await loop.run_in_executor(None, check_ssl_certificate, domain)

        result["domain_age_days"] = domain_age
        result["ssl_valid"] = ssl_data.get("valid", False)
        result["ssl_days_until_expiry"] = ssl_data.get("days_until_expiry")

        final_url = await get_final_url(session, domain)
        if not final_url:
            raise Exception("Failed to resolve domain via HTTP/HTTPS")

        result["final_url"] = final_url

        status_code, html_body, latency = await fetch_url(
            session, final_url, req_timeout=config.HTTP_TIMEOUT_TOTAL
        )

        result["status_code"] = status_code
        result["response_time_ms"] = round(latency, 2)

        if status_code == 200:
            html_metadata = analyze_html_content(html_body)
            result["has_live_content"] = html_metadata["has_live_content"]
            result["html_title"] = html_metadata["title"]
            result["meta_description"] = html_metadata["meta_description"]
            result["word_count"] = html_metadata["word_count"]
        else:
            pass1_success = False

    except Exception as e:
        result["error"] = f"Pass1 {type(e).__name__}: {e!s}"
        logger.debug("Pass 1 failed or incomplete", domain=domain, error=str(e))
        pass1_success = False

    # --- PASS 2: Serper.dev Fallback ---
    # Trigger Pass 2 if Pass 1 had an exception, non-200 status, or found no live content
    needs_fallback = not pass1_success or not result["has_live_content"]

    if needs_fallback:
        logger.info("Triggering Serper.dev fallback", domain=domain)
        result["fallback_used"] = True

        fallback_res = await scrape_with_serper(session, domain)
        result["credits_used"] = fallback_res.get("credits_used", 0)

        if fallback_res["status"] == "success":
            # Override results with metadata from Serper
            result["has_live_content"] = fallback_res.get("has_live_content", False)
            result["html_title"] = fallback_res.get("title")
            result["meta_description"] = fallback_res.get("meta_description")
            result["word_count"] = fallback_res.get("word_count", 0)
        else:
            # Aggregate the error from Pass 2 for detailed logging
            err_msg = f"Pass2 Error: {fallback_res.get('reason')}"
            result["error"] = f"{result['error']} | {err_msg}" if result["error"] else err_msg

    return result
