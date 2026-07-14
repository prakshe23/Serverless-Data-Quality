"""Validates an incoming file against the dataset's schema contract.

Contracts are JSON documents stored at ``schemas/<dataset>.json`` in the
config bucket, e.g.::

    {
      "columns": [
        {"name": "customer_id", "type": "integer", "required": true},
        {"name": "email",       "type": "string",  "required": true},
        {"name": "signup_date", "type": "date",    "required": false}
      ],
      "allow_extra_columns": false
    }
"""

import os
import re

from dq_common import read_csv_sample, read_json_object

CONFIG_BUCKET = os.environ["CONFIG_BUCKET"]

_TYPE_PATTERNS = {
    "integer": re.compile(r"^-?\d+$"),
    "number": re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$"),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "timestamp": re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"),
    "boolean": re.compile(r"^(true|false|0|1)$", re.IGNORECASE),
}


def validate_schema(contract: dict, header: list, rows: list) -> dict:
    """Pure validation logic, unit-testable without AWS."""
    violations = []
    expected = {c["name"]: c for c in contract.get("columns", [])}

    missing = [name for name in expected if name not in header]
    for name in missing:
        violations.append({"type": "missing_column", "column": name})

    if not contract.get("allow_extra_columns", True):
        for name in header:
            if name not in expected:
                violations.append({"type": "unexpected_column", "column": name})

    type_errors = {}
    required_nulls = {}
    for row in rows:
        for name, spec in expected.items():
            if name not in row:
                continue
            value = (row.get(name) or "").strip()
            if not value:
                if spec.get("required"):
                    required_nulls[name] = required_nulls.get(name, 0) + 1
                continue
            pattern = _TYPE_PATTERNS.get(spec.get("type", "string"))
            if pattern and not pattern.match(value):
                type_errors[name] = type_errors.get(name, 0) + 1

    for name, count in required_nulls.items():
        violations.append({"type": "required_null", "column": name, "count": count})
    for name, count in type_errors.items():
        violations.append(
            {
                "type": "type_mismatch",
                "column": name,
                "expected": expected[name].get("type"),
                "count": count,
            }
        )

    checked = len(expected) * max(len(rows), 1)
    error_cells = sum(v.get("count", len(rows)) for v in violations)
    score = max(0.0, 1.0 - (error_cells / checked)) if checked else 1.0

    return {
        "dimension": "schema",
        "score": round(score, 4),
        "passed": not violations,
        "violations": violations,
        "sampled_rows": len(rows),
    }


def lambda_handler(event, _context):
    dataset, bucket, key = event["dataset"], event["bucket"], event["key"]
    try:
        contract = read_json_object(CONFIG_BUCKET, f"schemas/{dataset}.json")
    except Exception:
        # No contract registered: treat as advisory pass so new datasets
        # aren't blocked, but flag it in the report.
        return {
            "dimension": "schema",
            "score": 1.0,
            "passed": True,
            "violations": [{"type": "no_contract", "column": None}],
            "sampled_rows": 0,
        }

    header, rows, _ = read_csv_sample(bucket, key)
    return validate_schema(contract, header, rows)
