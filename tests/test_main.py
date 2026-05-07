import runpy
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import config
from src.main import main


@pytest.fixture
def mock_seeds_csv(tmp_path: Path) -> Path:
    """Creates a test input file with domain names."""
    csv_path = tmp_path / "seeds.csv"
    csv_path.write_text("domain\ngoogle.com\nfailed-site.org", encoding="utf-8")
    return csv_path


@pytest.fixture
def mock_results_csv(tmp_path: Path) -> Path:
    """Creates a test input file simulating the results of a previous run."""
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "domain,status\ngoogle.com,success\nfailed-site.org,error", encoding="utf-8"
    )
    return csv_path


@patch("src.main.analyze_domain", new_callable=AsyncMock)
@patch("src.main.cache_manager", new_callable=MagicMock)
def test_main_e2e_success(
    mock_cache: MagicMock,
    mock_analyze: AsyncMock,
    mock_seeds_csv: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the full execution cycle for new domains (E2E Success)."""

    # Simulate that the cache is always empty
    mock_cache.get.return_value = None

    async def mock_analyze_side_effect(session: Any, domain: str, config: Any) -> dict[str, Any]:
        return {
            "domain": domain,
            "status": "success",
            "score": 100,
            "priority": "High",
            "next_action": "Manual Review",
            "fallback_used": False,
            "credits_used": 0,
            "error": None,
        }

    mock_analyze.side_effect = mock_analyze_side_effect

    new_config = replace(config, OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr("src.exporter.config", new_config)

    with (
        patch("src.report_generator.os.path.basename", return_value="seeds.csv"),
        patch.object(
            sys, "argv", ["src/main.py", "--input", str(mock_seeds_csv), "--workers", "2"]
        ),
    ):
        main()

    exported_csvs = list(tmp_path.glob("output_*.csv"))
    exported_mds = list(tmp_path.glob("output_*_summary.md"))

    assert len(exported_csvs) == 1
    assert len(exported_mds) == 1
    assert mock_analyze.call_count == 2


def test_main_missing_input_file() -> None:
    """Verifies that the script exits gracefully (sys.exit=1) when the file is missing."""
    with patch.object(sys, "argv", ["src/main.py", "--input", "non_existent_file.csv"]):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1


@patch("src.main.analyze_domain", new_callable=AsyncMock)
@patch("src.main.cache_manager", new_callable=MagicMock)
def test_main_rerun_failed(
    mock_cache: MagicMock,
    mock_analyze: AsyncMock,
    mock_results_csv: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the operation of the --rerun-failed flag (re-processing only errors)."""

    # Simulate cache using a dictionary
    fake_cache = {"google.com": {"status": "success"}, "failed-site.org": {"status": "error"}}

    def cache_get_side_effect(domain):
        return fake_cache.get(domain)

    def cache_delete_side_effect(domain):
        fake_cache.pop(domain, None)

    mock_cache.get.side_effect = cache_get_side_effect
    mock_cache.delete.side_effect = cache_delete_side_effect

    async def mock_analyze_side_effect(session: Any, domain: str, config: Any) -> dict[str, Any]:
        return {
            "domain": domain,
            "status": "success",
            "score": 50,
            "priority": "Medium",
            "next_action": "Monitor",
            "fallback_used": False,
            "credits_used": 0,
            "error": None,
        }

    mock_analyze.side_effect = mock_analyze_side_effect

    new_config = replace(config, OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr("src.exporter.config", new_config)

    with patch.object(
        sys, "argv", ["src/main.py", "--input", str(mock_results_csv), "--rerun-failed"]
    ):
        main()

    assert mock_analyze.call_count == 1
    # Verify that the delete method was called for the failed domain
    mock_cache.delete.assert_called_once_with("failed-site.org")


@patch("src.main.analyze_domain", new_callable=AsyncMock)
@patch("src.main.cache_manager", new_callable=MagicMock)
def test_main_domain_timeout_handling(
    mock_cache: MagicMock,
    mock_analyze: AsyncMock,
    mock_seeds_csv: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that unexpected timeouts (or crashes) in the process are isolated."""

    # Simulate an empty cache
    mock_cache.get.return_value = None

    # Simulate a timeout for each request
    mock_analyze.side_effect = TimeoutError("Global Timeout")

    new_config = replace(config, OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr("src.exporter.config", new_config)

    with patch.object(sys, "argv", ["src/main.py", "--input", str(mock_seeds_csv)]):
        main()

    exported_csvs = list(tmp_path.glob("output_*.csv"))
    assert len(exported_csvs) == 1

    content = exported_csvs[0].read_text(encoding="utf-8")
    assert "Critical failure: Per-domain processing timeout" in content


def test_main_empty_domains_list(tmp_path: Path) -> None:
    """Verifies that an empty file does not crash the system (sys.exit=0)."""
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("domain\n\n  \n", encoding="utf-8")

    with patch.object(sys, "argv", ["src/main.py", "--input", str(empty_csv)]):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 0


@patch("src.main.analyze_domain", new_callable=AsyncMock)
@patch("src.main.cache_manager", new_callable=MagicMock)
def test_main_cache_hit_and_unexpected_error(
    mock_cache: MagicMock,
    mock_analyze: AsyncMock,
    mock_seeds_csv: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the cache hit branch (lines 28-29) and unexpected error (lines 45-47)."""

    # For the first domain return a full dictionary from the cache, for the second — simulate a miss
    mock_cache.get.side_effect = [
        {
            "domain": "google.com",
            "status": "success",
            "score": 100,
            "priority": "High",
            "next_action": "Manual Review",
            "fallback_used": False,
            "credits_used": 0,
            "error": None,
        },  # Cache Hit
        None,  # Cache Miss
    ]

    # Simulate a hard analyzer crash for the second domain
    mock_analyze.side_effect = RuntimeError("Completely unexpected error")

    new_config = replace(config, OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr("src.exporter.config", new_config)

    with patch.object(sys, "argv", ["src/main.py", "--input", str(mock_seeds_csv)]):
        main()

    # Analyzer should have been called only once (due to cache miss)
    assert mock_analyze.call_count == 1

    exported_csvs = list(tmp_path.glob("output_*.csv"))
    content = exported_csvs[0].read_text(encoding="utf-8")

    # Verify that both scenarios successfully wrote to the results
    assert "google.com" in content
    assert "Critical error: RuntimeError" in content


@patch("src.main.process_single_domain", new_callable=AsyncMock)
def test_main_batch_exception(
    mock_process: AsyncMock, mock_seeds_csv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the aggregation of critical errors at the batch level (lines 77-78)."""
    # Simulate a crash of the worker function itself (which will return Exception due to return_exceptions=True)
    mock_process.side_effect = TypeError("Batch corruption")

    new_config = replace(config, OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr("src.exporter.config", new_config)

    with patch.object(sys, "argv", ["src/main.py", "--input", str(mock_seeds_csv)]):
        main()

    exported_csvs = list(tmp_path.glob("output_*.csv"))
    content = exported_csvs[0].read_text(encoding="utf-8")
    assert "Batch exception: TypeError" in content


def test_main_csv_read_error(tmp_path: Path) -> None:
    """Verifies interception of errors when reading CSV (lines 137-139)."""
    # Create a directory instead of a file to trigger PermissionError / IsADirectoryError
    bad_csv = tmp_path / "bad_dir.csv"
    bad_csv.mkdir()

    with patch.object(sys, "argv", ["src/main.py", "--input", str(bad_csv)]):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1


@patch("src.main.analyze_domain", new_callable=AsyncMock)
@patch("src.main.cache_manager", new_callable=MagicMock)
@pytest.mark.filterwarnings("ignore::RuntimeWarning")  # Add this line
def test_main_module_execution(
    mock_cache: MagicMock,
    mock_analyze: AsyncMock,
    mock_seeds_csv: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the entry point if __name__ == '__main__' (line 183)."""

    # Mock cache and analyzer so true main() runs without network requests
    mock_cache.get.return_value = None
    mock_analyze.return_value = {
        "domain": "google.com",
        "status": "success",
        "score": 100,
        "priority": "High",
        "next_action": "Manual Review",
        "fallback_used": False,
        "credits_used": 0,
        "error": None,
    }

    new_config = replace(config, OUTPUT_DIR=str(tmp_path))
    monkeypatch.setattr("src.exporter.config", new_config)

    with patch.object(sys, "argv", ["src/main.py", "--input", str(mock_seeds_csv)]):
        # Allow runpy to execute the file completely, including calling main()
        runpy.run_module("src.main", run_name="__main__")

    # If reached here without errors and CSV generated — __main__ block works
    exported_csvs = list(tmp_path.glob("output_*.csv"))
    assert len(exported_csvs) > 0
