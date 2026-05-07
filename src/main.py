import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

import aiohttp

from src.cache import cache_manager
from src.config import config
from src.domain_analyzer import analyze_domain
from src.exporter import export_to_csv
from src.logger import logger


async def process_single_domain(
    session: aiohttp.ClientSession, domain: str, semaphore: asyncio.Semaphore
) -> dict[str, Any]:
    """
    Processes a single domain with cache checking and concurrency control.
    """
    async with semaphore:
        # SQLite cache check
        cached_data = cache_manager.get(domain)
        if cached_data:
            logger.info("Cache hit", domain=domain)
            return cached_data

        logger.info("Processing domain", domain=domain)
        try:
            # Single domain processing time limit
            result = await asyncio.wait_for(analyze_domain(session, domain, config), timeout=30.0)
        except TimeoutError:
            logger.error("Domain processing timed out", domain=domain)
            result = {
                "domain": domain,
                "status": "error",
                "score": 0,
                "reason": "Critical failure: Per-domain processing timeout (30s)",
                "priority": "Low",
                "next_action": "Retry",
            }
        except Exception as e:
            logger.error("Domain processing failed unexpectedly", domain=domain, error=str(e))
            result = {
                "domain": domain,
                "status": "error",
                "score": 0,
                "reason": f"Critical error: {type(e).__name__}",
                "priority": "Low",
                "next_action": "Retry",
            }

        # Writing the result to the cache
        cache_manager.set(domain, result)
        return result


async def process_domains_batch(domains: list[str], max_workers: int) -> list[dict[str, Any]]:
    """
    Parallel processing of domains via asyncio.gather.
    """
    logger.info("Starting batch processing", total_domains=len(domains), max_workers=max_workers)

    semaphore = asyncio.Semaphore(max_workers)
    connector = aiohttp.TCPConnector(limit=max_workers)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [process_single_domain(session, domain, semaphore) for domain in domains]
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
                    "reason": f"Batch exception: {type(res).__name__}",
                    "priority": "Low",
                    "next_action": "Retry",
                }
            )
        else:
            final_results.append(res)

    return final_results


def parse_arguments() -> argparse.Namespace:
    """
    Argparse CLI with parameters.
    """
    parser = argparse.ArgumentParser(description="Domain Triaging System CLI")
    parser.add_argument(
        "--input", type=str, required=True, help="Path to input CSV file containing domains"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=config.DEFAULT_WORKERS,
        help="Number of concurrent asynchronous workers",
    )
    return parser.parse_args()


def load_domains(input_path: Path) -> list[str]:
    """Synchronous file reading to avoid blocking operations in an async context."""
    if not input_path.exists():
        logger.critical("Input file not found", filepath=str(input_path))
        sys.exit(1)

    raw_domains: list[str] = []
    try:
        with open(input_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                domain = row.get("domain", "").strip().lower()
                if domain:
                    raw_domains.append(domain)
    except Exception as e:
        logger.critical("Failed to read input CSV", error=str(e))
        sys.exit(1)

    return raw_domains


def main() -> None:
    args = parse_arguments()
    input_path = Path(args.input)

    # Synchronous loading and filtering
    raw_domains = load_domains(input_path)
    unique_domains = list(set(raw_domains))

    if not unique_domains:
        logger.warning("No valid domains found in input file")
        sys.exit(0)

    # Asynchronous pipeline execution
    processed_results = asyncio.run(process_domains_batch(unique_domains, max_workers=args.workers))

    # Synchronous export of results
    output_file = export_to_csv(processed_results)

    logger.info(
        "Triaging completed successfully",
        total_processed=len(processed_results),
        output_file=output_file,
    )


if __name__ == "__main__":
    main()
