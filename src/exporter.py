import os
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import tldextract

from src.config import config
from src.logger import logger


def generate_output_filename() -> str:
    """
    Generates a unique path to the output file with a timestamp.
    """
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    output_dir = config.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"output_{timestamp}.csv")


def export_to_csv(results: list[dict[str, Any]], output_path: str | None = None) -> str:
    """
    Exports results to a Google Sheets-compatible CSV with a clear
    column order and metadata post-processing.
    """
    if not results:
        logger.warning("No results to export")
        return ""

    if not output_path:
        output_path = generate_output_filename()

    # Post-processing of results to fill mandatory fields
    for row in results:
        # Logic for the 'status' field (safety check if it wasn't filled in the scorer)
        if row.get("error") and row.get("status") != "error":
            row["status"] = "error"
        elif not row.get("error") and not row.get("status"):
            row["status"] = "success"

        # Logic for 'scrape_method' and 'notes' fields
        fallback = row.get("fallback_used", False)
        row["scrape_method"] = "serper" if fallback else "bs4"

        if fallback:
            row["notes"] = "Fallback to Serper.dev (Pass 1 failed)"
        else:
            row["notes"] = ""

        # Logic for the 'server_country' field via tldextract
        final_url = row.get("final_url")
        if final_url:
            extracted = tldextract.extract(final_url)
            # tldextract returns a suffix (e.g., 'com', 'co.uk').
            # We take the last part to determine the country TLD.
            suffix = extracted.suffix
            row["server_country"] = suffix.split(".")[-1].upper() if suffix else "UNKNOWN"
        else:
            row["server_country"] = "UNKNOWN"

    # Exact list of columns according to the Roadmap
    expected_columns = [
        "domain",
        "score",
        "reason",
        "status",
        "priority",
        "next_action",
        "notes",
        "response_time_ms",
        "final_url",
        "ssl_valid",
        "ssl_days_until_expiry",
        "domain_age_days",
        "server_country",
        "has_live_content",
        "html_title",
        "word_count",
        "scrape_method",
        "credits_used",
        "error",
    ]

    df = pd.DataFrame(results)

    # Ensuring all mandatory columns are present
    for col in expected_columns:
        if col not in df.columns:
            df[col] = None

    # Discarding unnecessary columns (e.g., 'fallback_used') and aligning the order
    df = df[expected_columns]

    try:
        # Writing with utf-8-sig (BOM) for correct import
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info("CSV export complete", path=output_path, rows=len(df))
        return output_path
    except Exception as e:
        logger.error("Failed to export results to CSV", error=str(e), filepath=output_path)
        raise
