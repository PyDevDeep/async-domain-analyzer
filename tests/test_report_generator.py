import os
from pathlib import Path

from src.report_generator import generate_summary_report


def test_generate_summary_report(tmp_path: Path) -> None:
    """Verifies the correctness of Markdown report generation and statistics calculation."""
    csv_path = str(tmp_path / "output_test.csv")
    expected_md_path = str(tmp_path / "output_test_summary.md")

    mock_results = [
        {
            "domain": "site1.com",
            "status": "success",
            "priority": "High",
            "score": 90,
            "credits_used": 0,
            "fallback_used": False,
            "next_action": "Manual Review",
        },
        {
            "domain": "site2.com",
            "status": "success",
            "priority": "Medium",
            "score": 60,
            "credits_used": 2,
            "fallback_used": True,
            "next_action": "Monitor",
        },
        {
            "domain": "site3.com",
            "status": "error",
            "priority": "Low",
            "score": 0,
            "credits_used": 0,
            "fallback_used": True,
            "next_action": "Retry",
        },
    ]

    result_path = generate_summary_report(mock_results, csv_path)

    assert result_path == expected_md_path
    assert os.path.exists(expected_md_path)

    with open(expected_md_path, encoding="utf-8") as f:
        content = f.read()

    # Verify the presence of correct statistics in the text
    assert "**Total Domains Processed** | 3" in content
    assert "**Successful Scrapes** | 2" in content
    assert "**Failed / Inaccessible** | 1" in content
    assert "**Fallback API (Serper) Used** | 2" in content
    assert "**Total Serper Credits Consumed** | 2" in content

    # Verify priorities
    assert "High Priority (Manual Review):** 1" in content
    assert "Medium Priority (Monitor):** 1" in content
    assert "Low Priority (Discard/Archive):** 1" in content

    # Verify top domains
    assert "site1.com" in content
    assert "site2.com" in content


def test_generate_summary_report_empty(tmp_path: Path) -> None:
    """Verifies report generation for an empty array."""
    csv_path = str(tmp_path / "empty.csv")
    result_path = generate_summary_report([], csv_path)

    with open(result_path, encoding="utf-8") as f:
        content = f.read()

    assert "**Total Domains Processed** | 0" in content
    assert "_No high-score domains found in this batch._" in content
