"""Aggregates the parallel check results into a single quality verdict.

Receives the Step Functions parallel-state output (schema, profile, PII and
anomaly results), computes a weighted overall score, emits CloudWatch
metrics, and returns the verdict that drives the workflow's Choice state.
"""

import os

from dq_common import emit_quality_metric

WEIGHTS = {
    "schema": 0.35,
    "profile": 0.20,
    "pii": 0.25,
    "anomaly": 0.20,
}

PASS_THRESHOLD = float(os.environ.get("PASS_THRESHOLD", "0.8"))
WARN_THRESHOLD = float(os.environ.get("WARN_THRESHOLD", "0.6"))

# Each metric name x dataset dimension counts against CloudWatch's 10
# always-free custom metrics, so per-dimension scores are opt-in.
EMIT_DIMENSION_METRICS = (
    os.environ.get("EMIT_DIMENSION_METRICS", "false").lower() == "true"
)


def build_report(run_context: dict, check_results: list) -> dict:
    """Pure aggregation logic, unit-testable without AWS."""
    by_dimension = {r["dimension"]: r for r in check_results}

    overall = 0.0
    total_weight = 0.0
    for dimension, weight in WEIGHTS.items():
        result = by_dimension.get(dimension)
        if result is None:
            continue
        overall += weight * float(result.get("score", 0.0))
        total_weight += weight
    overall = overall / total_weight if total_weight else 0.0

    # Hard gates that override the weighted score: unexpected high-risk PII
    # or a completely broken schema always fail the file.
    pii = by_dimension.get("pii", {})
    hard_fail = any(
        f.get("high_risk") and not f.get("allowed") for f in pii.get("findings", [])
    )
    schema = by_dimension.get("schema", {})
    if any(v["type"] == "missing_column" for v in schema.get("violations", [])):
        hard_fail = True

    if hard_fail or overall < WARN_THRESHOLD:
        verdict = "FAILED"
    elif overall < PASS_THRESHOLD:
        verdict = "WARNED"
    else:
        verdict = "PASSED"

    profile = by_dimension.get("profile", {})
    return {
        "run_id": run_context["run_id"],
        "dataset": run_context["dataset"],
        "bucket": run_context["bucket"],
        "key": run_context["key"],
        "overall_score": round(overall, 4),
        "verdict": verdict,
        "row_count": profile.get("row_count"),
        "dimensions": by_dimension,
    }


def lambda_handler(event, _context):
    report = build_report(event["run"], event["checks"])

    dataset = report["dataset"]
    emit_quality_metric("OverallScore", report["overall_score"], dataset)
    if EMIT_DIMENSION_METRICS:
        for dimension, result in report["dimensions"].items():
            emit_quality_metric(
                f"Score.{dimension}", float(result.get("score", 0.0)), dataset
            )
    emit_quality_metric(
        "Failed", 1.0 if report["verdict"] == "FAILED" else 0.0, dataset, unit="Count"
    )

    return report
