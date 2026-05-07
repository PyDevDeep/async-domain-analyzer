from src.scorer import calculate_score


def test_calculate_score_live_site() -> None:
    """Verifies that a domain with SSL, old age, and live content receives a score of 80-100 and High priority."""
    mock_data = {
        "domain": "live-site.com",
        "ssl_valid": True,
        "domain_age_days": 1000,
        "has_live_content": True,
        "word_count": 500,
        "error": None,
        "status_code": 200,
    }

    result = calculate_score(mock_data)

    assert result["status"] == "success"
    assert result["score"] >= 80
    assert result["priority"] == "High"
    assert result["next_action"] == "Manual Review"


def test_calculate_score_parked_domain() -> None:
    """Verifies that a domain without SSL, young age, and no content receives a score of 0-20 and Low priority."""
    mock_data = {
        "domain": "parked-domain.xyz",
        "ssl_valid": False,
        "domain_age_days": 15,
        "has_live_content": False,
        "word_count": 10,
        "error": None,
        "status_code": 200,
    }

    result = calculate_score(mock_data)

    assert result["status"] == "success"
    assert result["score"] <= 20
    assert result["priority"] == "Low"
    assert result["next_action"] == "Discard"


def test_assign_priority_medium() -> None:
    """Verifies correct assignment of Medium priority for partially valid data."""
    mock_data = {
        "domain": "average-site.net",
        "ssl_valid": True,
        "domain_age_days": 40,
        "has_live_content": False,
        "word_count": 60,
        "error": None,
        "status_code": 200,
    }

    result = calculate_score(mock_data)

    mock_data["domain_age_days"] = 400
    result = calculate_score(mock_data)

    assert result["priority"] == "Medium"
    assert result["next_action"] == "Monitor"


def test_assign_next_action_error() -> None:
    """Verifies that a domain with an error receives next_action='Retry' and score=0."""
    mock_data = {
        "domain": "failed.com",
        "status_code": None,
        "error": "Failed to resolve domain via HTTP/HTTPS",
    }

    result = calculate_score(mock_data)

    assert result["status"] == "error"
    assert result["score"] == 0
    assert result["priority"] == "Low"
    assert result["next_action"] == "Retry"
    assert "Critical failure" in result["reason"]
