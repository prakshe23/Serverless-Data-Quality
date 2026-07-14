from conftest import load_handler

handler = load_handler("pii_detector")


def test_no_pii_scores_full():
    result = handler.summarize_findings({"notes": []}, allowed=set())
    assert result["score"] == 1.0
    assert result["passed"] is True
    assert result["findings"] == []


def test_allowed_pii_column_passes():
    entities = {"email": [{"Type": "EMAIL", "Score": 0.99}]}
    result = handler.summarize_findings(entities, allowed={"email"})
    assert result["passed"] is True
    assert result["findings"][0]["allowed"] is True


def test_unexpected_pii_penalized():
    entities = {"comments": [{"Type": "EMAIL", "Score": 0.95}]}
    result = handler.summarize_findings(entities, allowed=set())
    assert result["passed"] is False
    assert result["score"] == 0.7


def test_high_risk_pii_zeroes_score():
    entities = {"notes": [{"Type": "SSN", "Score": 0.99}]}
    result = handler.summarize_findings(entities, allowed=set())
    assert result["score"] == 0.0
    assert result["findings"][0]["high_risk"] is True


def test_regex_mode_finds_common_pii():
    document = "\n".join(
        [
            "contact: alice@example.com",
            "ssn on file 123-45-6789",
            "call (555) 123-4567",
        ]
    )
    types = {e["Type"] for e in handler.detect_pii_regex(document)}
    assert {"EMAIL", "SSN", "PHONE"} <= types


def test_regex_mode_validates_card_numbers_with_luhn():
    valid = handler.detect_pii_regex("card 4111 1111 1111 1111 ok")
    assert any(e["Type"] == "CREDIT_DEBIT_NUMBER" for e in valid)

    invalid = handler.detect_pii_regex("card 4111 1111 1111 1112 ok")
    assert not any(e["Type"] == "CREDIT_DEBIT_NUMBER" for e in invalid)


def test_regex_mode_ignores_plain_numbers():
    document = "order 1001 amount 49.00 qty 3"
    assert handler.detect_pii_regex(document) == []


def test_low_confidence_entities_ignored():
    entities = {"notes": [{"Type": "SSN", "Score": 0.3}]}
    result = handler.summarize_findings(entities, allowed=set())
    assert result["score"] == 1.0
    assert result["findings"] == []
