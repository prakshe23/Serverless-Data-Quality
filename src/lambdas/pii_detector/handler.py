"""AI-powered PII detection using Amazon Comprehend.

Samples free-text cells from the file, batches them into Comprehend
``detect_pii_entities`` calls and reports which columns leak personally
identifiable information. Datasets can whitelist columns that are *expected*
to hold PII (e.g. an email column in a CRM extract) via the schema contract's
``pii_allowed`` list.
"""

import os

import boto3

from dq_common import read_csv_sample, read_json_object

_comprehend = boto3.client("comprehend")

CONFIG_BUCKET = os.environ["CONFIG_BUCKET"]

# Comprehend limits: 100KB per document. We pack one document per column
# from a bounded sample of cells to keep the call count deterministic.
MAX_CELLS_PER_COLUMN = 40
MAX_DOC_BYTES = 90_000
HIGH_RISK_TYPES = {"SSN", "CREDIT_DEBIT_NUMBER", "BANK_ACCOUNT_NUMBER", "PASSPORT_NUMBER",
                   "DRIVER_ID", "PIN", "PASSWORD", "AWS_SECRET_KEY"}


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

    column_entities = {}
    for column in header:
        document = _column_document(rows, column)
        if len(document) < 20:
            continue
        language = "en"
        try:
            langs = _comprehend.detect_dominant_language(Text=document[:5000])["Languages"]
            if langs:
                language = langs[0]["LanguageCode"]
        except Exception:
            pass
        result = _comprehend.detect_pii_entities(Text=document, LanguageCode=language)
        column_entities[column] = result.get("Entities", [])

    return summarize_findings(column_entities, allowed)
