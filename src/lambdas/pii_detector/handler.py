"""AI-powered PII detection.

Two modes, selected with the PII_MODE environment variable:

- ``comprehend`` (default): batches sampled cell text into Amazon Comprehend
  ``detect_pii_entities`` calls. Free-tier eligible for 12 months
  (50K units/month); the sampling below stays well under that.
- ``regex``: built-in pattern matching with Luhn validation for card
  numbers. Less accurate, but costs nothing, forever.

Datasets can whitelist columns that are *expected* to hold PII (e.g. an
email column in a CRM extract) via the schema contract's ``pii_allowed``
list.
"""

import os
import re

import boto3

from dq_common import read_csv_sample, read_json_object

_comprehend = boto3.client("comprehend")

CONFIG_BUCKET = os.environ["CONFIG_BUCKET"]
PII_MODE = os.environ.get("PII_MODE", "comprehend")

# Comprehend limits: 100KB per document. We pack one document per column
# from a bounded sample of cells to keep the call count deterministic.
MAX_CELLS_PER_COLUMN = 40
MAX_DOC_BYTES = 90_000
HIGH_RISK_TYPES = {"SSN", "CREDIT_DEBIT_NUMBER", "BANK_ACCOUNT_NUMBER", "PASSPORT_NUMBER",
                   "DRIVER_ID", "PIN", "PASSWORD", "AWS_SECRET_KEY"}

_REGEX_PATTERNS = {
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(r"\b(?:\+?1[-. ])?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"),
    "CREDIT_DEBIT_NUMBER": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "IP_ADDRESS": re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
}


def _luhn_valid(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def detect_pii_regex(document: str) -> list:
    """Free-mode detector. Returns Comprehend-shaped entity dicts."""
    entities = []
    for entity_type, pattern in _REGEX_PATTERNS.items():
        for match in pattern.finditer(document):
            if entity_type == "CREDIT_DEBIT_NUMBER" and not _luhn_valid(match.group()):
                continue
            entities.append({"Type": entity_type, "Score": 1.0})
    return entities


def _detect_pii_comprehend(document: str) -> list:
    language = "en"
    try:
        langs = _comprehend.detect_dominant_language(Text=document[:5000])["Languages"]
        if langs:
            language = langs[0]["LanguageCode"]
    except Exception:
        pass
    result = _comprehend.detect_pii_entities(Text=document, LanguageCode=language)
    return result.get("Entities", [])


def _column_document(rows: list, column: str) -> str:
    cells = []
    size = 0
    for row in rows:
        value = (row.get(column) or "").strip()
        if not value:
            continue
        size += len(value) + 1
        if size > MAX_DOC_BYTES or len(cells) >= MAX_CELLS_PER_COLUMN:
            break
        cells.append(value)
    return "\n".join(cells)


def summarize_findings(column_entities: dict, allowed: set) -> dict:
    """Pure aggregation logic, unit-testable without AWS."""
    findings = []
    unexpected = 0
    high_risk = 0

    for column, entities in column_entities.items():
        types = sorted({e["Type"] for e in entities if e.get("Score", 0) >= 0.7})
        if not types:
            continue
        is_allowed = column in allowed
        finding = {
            "column": column,
            "entity_types": types,
            "allowed": is_allowed,
            "high_risk": bool(set(types) & HIGH_RISK_TYPES),
        }
        findings.append(finding)
        if not is_allowed:
            unexpected += 1
            if finding["high_risk"]:
                high_risk += 1

    # Any unexpected PII column costs 0.3; high-risk types fail the dimension.
    score = 0.0 if high_risk else max(0.0, 1.0 - 0.3 * unexpected)
    return {
        "dimension": "pii",
        "score": round(score, 4),
        "passed": unexpected == 0,
        "findings": findings,
    }


def lambda_handler(event, _context):
    dataset, bucket, key = event["dataset"], event["bucket"], event["key"]

    allowed = set()
    try:
        contract = read_json_object(CONFIG_BUCKET, f"schemas/{dataset}.json")
        allowed = set(contract.get("pii_allowed", []))
    except Exception:
        pass

    header, rows, _ = read_csv_sample(bucket, key, max_rows=200)

    detect = detect_pii_regex if PII_MODE == "regex" else _detect_pii_comprehend
    column_entities = {}
    for column in header:
        document = _column_document(rows, column)
        if len(document) < 20:
            continue
        column_entities[column] = detect(document)

    result = summarize_findings(column_entities, allowed)
    result["mode"] = PII_MODE
    return result
