import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import aiohttp
import pandas as pd  # type: ignore[reportMissingTypeStubs]

from src.cache import cache_manager
from src.config import config
from src.domain_analyzer import analyze_domain
from src.exporter import export_to_csv
from src.logger import logger
from src.report_generator import generate_summary_report


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
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help="Re-process only domains with status 'error' in the input CSV",
    )
    return parser.parse_args()


def load_domains(input_path: Path, rerun_failed: bool = False) -> list[str]:
    """
    Loads domains from the input file.
    Supports files with and without headers, handles BOM, and filters by status if rerun_failed is True.
    """
    try:
        # Read the first line using utf-8-sig to ignore BOM (\ufeff)
        with open(input_path, encoding="utf-8-sig") as f:
            first_line = f.readline().strip().lower()

        # Determine if there is a header (starts with 'domain')
        if first_line.startswith("domain"):
            df = pd.read_csv(input_path)

            if rerun_failed:
                if "status" not in df.columns:
                    logger.critical("Cannot rerun failed: 'status' column missing")
                    sys.exit(1)
                df = df[df["status"] != "success"]

            raw_domains = df["domain"].dropna().astype(str).tolist()
        else:
            # It's a file without headers (a simple list)
            if rerun_failed:
                logger.critical("Cannot rerun failed: input file lacks headers")
                sys.exit(1)

            df = pd.read_csv(input_path, header=None)
            raw_domains = df.iloc[:, 0].dropna().astype(str).tolist()

        # Clean spaces and empty strings
        raw_domains = [d.strip() for d in raw_domains if d.strip()]

    except Exception as e:
        logger.critical("Failed to read input file", file=str(input_path), error=str(e))
        sys.exit(1)

    return raw_domains


def main() -> None:
    """
    Entry point of the application. Parses arguments, loads domains, processes them, and exports results.
    """
    args = parse_arguments()
    input_path = Path(args.input)

    # Synchronous loading and filtering
    is_rerun: bool = getattr(args, "rerun_failed", False)
    workers_count: int = getattr(args, "workers", config.DEFAULT_WORKERS)

    raw_domains: list[str] = load_domains(input_path, rerun_failed=is_rerun)
    unique_domains: list[str] = list(set(raw_domains))

    if not unique_domains:
        logger.warning("No valid domains found to process")
        sys.exit(0)

    if is_rerun:
        logger.info(
            "Rerun failed mode active: clearing cache for target domains", count=len(unique_domains)
        )
        for domain in unique_domains:
            cache_manager.delete(domain)

    processed_results = asyncio.run(
        process_domains_batch(unique_domains, max_workers=workers_count)
    )

    output_file = export_to_csv(processed_results)

    if output_file:
        generate_summary_report(processed_results, output_file)

    logger.info(
        "Triaging completed successfully",
        total_processed=len(processed_results),
        output_file=output_file,
    )


if __name__ == "__main__":
    main()
