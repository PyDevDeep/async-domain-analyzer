import os
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from src.config import config
from src.exporter import export_to_csv, generate_output_filename


def test_generate_output_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the correctness of filename generation with a timestamp."""
    # Create a config copy with a modified OUTPUT_DIR
    new_config = replace(config, OUTPUT_DIR="mock_data_dir")

    # Replace config in the exporter namespace
    monkeypatch.setattr("src.exporter.config", new_config)

    filename = generate_output_filename()
    assert filename.startswith(f"mock_data_dir{os.sep}output_")
    assert filename.endswith(".csv")


def test_export_to_csv_empty() -> None:
    """Verifies behavior with an empty list of results."""
    result = export_to_csv([])
    assert result == ""


def test_export_to_csv_success(tmp_path: Path) -> None:
    """Verifies successful data export to CSV with required columns."""
    output_file = tmp_path / "test_output.csv"

    mock_results = [
        {
            "domain": "google.com.ua",
            "final_url": "https://www.google.com.ua/",
            "status": "success",
            "fallback_used": False,
            "score": 100,
        },
        {
            "domain": "failed.org",
            "final_url": None,
            "status": "error",
            "fallback_used": True,
            "score": 40,
        },
    ]

    # Perform export
    result_path = export_to_csv(mock_results, output_path=str(output_file))

    assert result_path == str(output_file)
    assert output_file.exists()

    # Verify CSV content via pandas
    df = pd.read_csv(output_file)

    # Verify presence of required columns
    assert "domain" in df.columns
    assert "server_country" in df.columns
    assert "scrape_method" in df.columns

    # Verify post-processing logic (server_country via tldextract)
    assert df.loc[0, "server_country"] == "UA"
    assert df.loc[1, "server_country"] == "UNKNOWN"

    # Verify scrape_method and notes
    assert df.loc[0, "scrape_method"] == "bs4"
    assert df.loc[1, "scrape_method"] == "serper"
    assert "Fallback to Serper.dev" in str(df.loc[1, "notes"])
