import json
from typing import Any, cast

import aiohttp

from src.config import config
from src.logger import logger
from src.rate_limiter import serper_limiter
from src.retry import async_retry


def parse_serper_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """
    Defensive parsing of Serper.dev API response.
    """
    text: str = str(data.get("text", ""))

    raw_metadata = data.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata = cast(dict[str, Any], raw_metadata)
    else:
        metadata = cast(dict[str, Any], {})

    title_val = metadata.get("title") or metadata.get("og:title")
    title: str | None = str(title_val) if title_val else None

    desc_val = metadata.get("description") or metadata.get("og:description")
    meta_description: str | None = str(desc_val) if desc_val else None

    word_count = len(text.split())
    has_live_content = word_count > 50

    return {
        "has_live_content": has_live_content,
        "title": title,
        "meta_description": meta_description,
        "word_count": word_count,
    }


@async_retry(max_retries=2, base_delay=1.0)
async def scrape_with_serper(session: aiohttp.ClientSession, domain: str) -> dict[str, Any]:
    """
    Executes a request to the Serper.dev API with budget control via rate_limiter.
    """
    api_url = "https://scrape.serper.dev"
    target_url = f"https://{domain}"

    result: dict[str, Any] = {
        "domain": domain,
        "status": "success",
        "reason": "",
        "has_live_content": False,
        "title": None,
        "word_count": 0,
        "credits_used": 0,
    }

    # Circuit breaker & Rate limiter pre-check
    estimated_cost = 5
    is_allowed = await serper_limiter.acquire(estimated_cost=estimated_cost)
    if not is_allowed:
        result["status"] = "error"
        result["reason"] = "Budget limit reached or Circuit breaker tripped"
        return result

    headers = {"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"}
    payload = json.dumps({"url": target_url})

    try:
        async with session.post(
            api_url, headers=headers, data=payload, timeout=aiohttp.ClientTimeout(total=15)
        ) as response:
            if response.status != 200:
                result["status"] = "error"
                result["reason"] = f"Serper HTTP Error: {response.status}"
                # Refunding the budget if the request failed (credits were not deducted)
                await serper_limiter.record_actual_cost(0, estimated_cost=estimated_cost)
                return result

            data = await response.json()

            # Schema validation
            required_fields = ["text", "metadata", "credits"]
            if not all(field in data for field in required_fields):
                logger.error("Serper response schema mismatch", response=data)
                result["status"] = "error"
                result["reason"] = "Invalid API response schema"
                await serper_limiter.record_actual_cost(0, estimated_cost=estimated_cost)
                return result

            # Adjusting the actual scraping cost
            actual_cost = data.get("credits", 1)
            result["credits_used"] = actual_cost
            await serper_limiter.record_actual_cost(actual_cost, estimated_cost=estimated_cost)

            # Safe metadata parsing
            parsed_data = parse_serper_metadata(data)
            result.update(parsed_data)

            logger.info("Serper fallback successful", domain=domain, cost=actual_cost)

    except Exception as e:
        logger.warning("Serper API request failed", domain=domain, error=str(e))
        result["status"] = "error"
        result["reason"] = f"Serper Exception: {type(e).__name__} - {e!s}"
        await serper_limiter.record_actual_cost(0, estimated_cost=estimated_cost)

    return result
