from typing import Any


def calculate_score(domain_data: dict[str, Any]) -> dict[str, Any]:
    """
    Calculates the score (0-100), priority, and next_action for a domain
    based on the gathered metadata.
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
    ssl_valid = domain_data.get("ssl_valid", False)
    days_expiry = domain_data.get("days_until_expiry", -999)

    if ssl_valid:
        score += 20
        reasons.append("Valid SSL")
    elif days_expiry > -90:
        score += 10
        reasons.append("SSL expired recently (<90 days)")
    else:
        reasons.append("No/Invalid SSL")

    # 3. Domain age (+20 points for > 730 days, +10 for > 365 days,)
    age = domain_data.get("domain_age_days")
    if age is None:
        reasons.append("Unknown age (WHOIS fail)")
        # score += 0 (вже за замовчуванням 0)
    elif age < 30:
        reasons.append(f"New domain ({age} days)")
        # score += 0
    elif age >= 730:
        score += 20
        reasons.append("Established domain (>= 2 years)")
    else:
        # Лінійна інтерполяція: ((age - 30) / (730 - 30)) * 20
        interpolation_score = ((age - 30) / 700) * 20
        score += round(interpolation_score, 2)
        reasons.append(f"Domain age: {age} days (linear score)")

    # 4. Presence of live content (+40 points)
    if domain_data.get("has_live_content"):
        score += 40
        reasons.append("Live content detected")
    else:
        reasons.append("No live content")

    # 5. Text volume (+20 points for > 100 words, +10 for > 50 words)
    words = domain_data.get("word_count", 0)
    if words >= 500:
        score += 20
        reasons.append(f"High word count ({words})")
    elif words >= 100:
        # Лінійна інтерполяція: ((words - 100) / 400) * 20
        v_score = ((words - 100) / 400) * 20
        score += round(v_score, 2)
        reasons.append(f"Medium word count ({words})")
    else:
        reasons.append(f"Low word count ({words})")

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
