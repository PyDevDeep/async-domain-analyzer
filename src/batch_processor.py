import asyncio
from typing import Any

import aiohttp

from src.cache import cache_manager
from src.config import config
from src.domain_analyzer import analyze_domain
from src.logger import logger


async def process_single_domain(
    session: aiohttp.ClientSession, domain: str, semaphore: asyncio.Semaphore
) -> dict[str, Any]:
    """
    Processes a single domain with concurrency control (via a semaphore),
    using SQLite cache and a strict per-domain timeout.
    """
    async with semaphore:
        # 1. Cache check
        cached_data = cache_manager.get(domain)
        if cached_data:
            logger.info("Cache hit", domain=domain)
            return cached_data

        # 2. Executing the pipeline (Pass 1 -> Pass 2 -> Scoring)
        logger.info("Processing domain", domain=domain)
        try:
            # RISK 5 Mitigation: Timeout budget per domain (30s)
            result = await asyncio.wait_for(analyze_domain(session, domain, config), timeout=30.0)
        except TimeoutError:
            logger.error("Domain processing timed out completely", domain=domain)
            result = {
                "domain": domain,
                "status": "error",
                "score": 0,
                "reason": "Critical failure: Per-domain processing timeout (30s)",
                "priority": "Low",
                "next_action": "Retry",
            }

        # 3. Saving the result to the SQLite cache
        cache_manager.set(domain, result)
        return result


async def process_domains_batch(
    domains: list[str], max_workers: int = config.DEFAULT_WORKERS
) -> list[dict[str, Any]]:
    """
    Asynchronously processes a list of domains with a specified concurrency level.
    Catches global exceptions at the task level.
    """
    logger.info("Starting batch processing", total_domains=len(domains), max_workers=max_workers)

    # The semaphore limits the number of concurrent active tasks
    semaphore = asyncio.Semaphore(max_workers)

    # Limiting the aiohttp connection pool size according to max_workers
    connector = aiohttp.TCPConnector(limit=max_workers)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [process_single_domain(session, domain, semaphore) for domain in domains]

        # return_exceptions=True ensures that the failure of one task does not cancel the entire batch
        results = await asyncio.gather(*tasks, return_exceptions=True)

    final_results: list[dict[str, Any]] = []

    for domain, res in zip(domains, results, strict=True):
        if isinstance(res, BaseException):
            logger.critical("Unexpected batch exception", domain=domain, error=str(res))
            final_results.append(
                {
                    "domain": domain,
                    "status": "error",
                    "score": 0,
                    "reason": f"Critical batch error: {type(res).__name__}",
                    "priority": "Low",
                    "next_action": "Retry",
                }
            )
        else:
            final_results.append(res)

    logger.info("Batch processing completed", total_processed=len(final_results))
    return final_results
