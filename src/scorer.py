from typing import Any


def calculate_score(domain_data: dict[str, Any]) -> dict[str, Any]:
    """
    Обчислює score (0-100), priority та next_action для домену
    на основі зібраних метаданих.
    """
    # 1. Handling critical scraping errors
    # Keeping the requirement: failed domains have status="error" and score=0
    if domain_data.get("status_code") is None and domain_data.get("error"):
        domain_data["status"] = "error"
        domain_data["score"] = 0
        domain_data["reason"] = f"Critical failure: {domain_data.get('error')}"
        domain_data["priority"] = "Low"
        domain_data["next_action"] = "Retry"
        return domain_data

    domain_data["status"] = "success"
    score = 0
    reasons: list[str] = []

    # 2. SSL Validation (+20 points)
    if domain_data.get("ssl_valid"):
        score += 20
        reasons.append("Valid SSL")
    else:
        reasons.append("No/Invalid SSL")

    # 3. Domain age (+20 points for > 365 days, +10 for > 30 days)
    age = domain_data.get("domain_age_days")
    if age is not None:
        if age > 365:
            score += 20
            reasons.append("Age > 1 year")
        elif age > 30:
            score += 10
            reasons.append("Age > 30 days")
        else:
            reasons.append("New domain (< 30 days)")
    else:
        reasons.append("Unknown age")

    # 4. Presence of live content (+40 points)
    if domain_data.get("has_live_content"):
        score += 40
        reasons.append("Live content detected")
    else:
        reasons.append("No live content")

    # 5. Text volume (+20 points for > 100 words, +10 for > 50 words)
    words = domain_data.get("word_count", 0)
    if words > 100:
        score += 20
        reasons.append("High word count")
    elif words > 50:
        score += 10
        reasons.append("Medium word count")
    else:
        reasons.append("Low word count")

    domain_data["score"] = score
    domain_data["reason"] = " | ".join(reasons)

    # 6. Prioritization and further actions (Triaging)
    if score >= 80:
        domain_data["priority"] = "High"
        domain_data["next_action"] = "Manual Review"
    elif score >= 50:
        domain_data["priority"] = "Medium"
        domain_data["next_action"] = "Monitor"
    else:
        domain_data["priority"] = "Low"
        domain_data["next_action"] = "Discard"

    return domain_data
