from conftest import load_handler

handler = load_handler("schema_validator")

CONTRACT = {
    "columns": [
        {"name": "customer_id", "type": "integer", "required": True},
        {"name": "email", "type": "string", "required": True},
        {"name": "signup_date", "type": "date", "required": False},
    ],
    "allow_extra_columns": False,
}

HEADER = ["customer_id", "email", "signup_date"]


def _rows(*triples):
    return [dict(zip(HEADER, t)) for t in triples]


def test_clean_file_passes():
    rows = _rows(
        ("1", "a@example.com", "2026-01-01"),
        ("2", "b@example.com", "2026-01-02"),
    )
    result = handler.validate_schema(CONTRACT, HEADER, rows)
    assert result["passed"] is True
    assert result["score"] == 1.0
    assert result["violations"] == []


def test_missing_column_is_reported():
    result = handler.validate_schema(CONTRACT, ["customer_id", "email"], _rows())
    types = [v["type"] for v in result["violations"]]
    assert "missing_column" in types


def test_unexpected_column_rejected_when_strict():
    header = HEADER + ["debug"]
    rows = [dict(zip(header, ("1", "a@example.com", "2026-01-01", "x")))]
    result = handler.validate_schema(CONTRACT, header, rows)
    assert {"type": "unexpected_column", "column": "debug"} in result["violations"]


def test_type_mismatch_lowers_score():
    rows = _rows(
        ("not-a-number", "a@example.com", "2026-01-01"),
        ("2", "b@example.com", "01/02/2026"),
    )
    result = handler.validate_schema(CONTRACT, HEADER, rows)
    assert result["passed"] is False
    assert result["score"] < 1.0
    by_type = {v["type"]: v for v in result["violations"]}
    assert by_type["type_mismatch"]["count"] >= 1


def test_required_null_is_reported():
    rows = _rows(("1", "", "2026-01-01"))
    result = handler.validate_schema(CONTRACT, HEADER, rows)
    assert {"type": "required_null", "column": "email", "count": 1} in result["violations"]
