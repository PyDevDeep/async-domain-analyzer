import os
from datetime import UTC, datetime
from typing import Any

from src.logger import logger


def generate_summary_report(results: list[dict[str, Any]], csv_path: str) -> str:
    """
    Генерує аналітичний звіт у форматі Markdown (контент англійською).
    """
    total = len(results)
    success = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")

    # Пріоритети
    high = sum(1 for r in results if r.get("priority") == "High")
    medium = sum(1 for r in results if r.get("priority") == "Medium")
    low = sum(1 for r in results if r.get("priority") == "Low")

    # Витрати
    total_credits = sum(r.get("credits_used", 0) for r in results)
    fallbacks = sum(1 for r in results if r.get("fallback_used", False))

    # Формування шляху (той самий, що у CSV, але .md)
    report_path = csv_path.replace(".csv", "_summary.md")

    now_str = datetime.now(UTC).strftime(format="%Y-%m-%d %H:%M:%S")

    md_content = f"""# Domain Triaging Executive Summary
Generated on: {now_str}
Input source: `{os.path.basename(csv_path)}`

## 📊 Processing Statistics
| Metric | Value |
| :--- | :--- |
| **Total Domains Processed** | {total} |
| **Successful Scrapes** | {success} |
| **Failed / Inaccessible** | {errors} |
| **Fallback API (Serper) Used** | {fallbacks} |
| **Total Serper Credits Consumed** | {total_credits} |

## 🎯 Triage Results (Prioritization)
- **🔴 High Priority (Manual Review):** {high}
- **🟡 Medium Priority (Monitor):** {medium}
- **🟢 Low Priority (Discard/Archive):** {low}

## 🔍 Top Interesting Domains
"""
    # Додаємо топ-5 доменів за рейтингом
    top_domains = sorted(
        [r for r in results if r.get("score")], key=lambda x: x.get("score", 0), reverse=True
    )[:5]

    if top_domains:
        md_content += "| Domain | Score | Next Action |\n| :--- | :--- | :--- |\n"
        for d in top_domains:
            md_content += f"| {d['domain']} | {d['score']} | {d['next_action']} |\n"
    else:
        md_content += "_No high-score domains found in this batch._\n"

    md_content += (
        f"\n\n--- \n*Full data available in the associated CSV file: {os.path.basename(csv_path)}*"
    )

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info("Summary report generated", path=report_path)
        return report_path
    except Exception as e:
        logger.error("Failed to generate summary report", error=str(e))
        return ""
