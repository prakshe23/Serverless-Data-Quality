"""Detects statistical anomalies in the incoming file.

Two classes of checks:

1. Value-level outliers within the file (z-score per numeric column).
2. Drift against the dataset's own history: the row count of this file is
   compared to the trailing runs recorded in DynamoDB, so a feed that
   suddenly shrinks or explodes is flagged even if every row is valid.
"""

import statistics

from dq_common import RunStore, read_csv_sample


def _try_float(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_outliers(header: list, rows: list, z_threshold: float = 3.0) -> dict:
    """Per-column z-score outlier counts. Pure, unit-testable."""
    outliers = {}
    for name in header:
        numeric = [
            f for f in ((_try_float((row.get(name) or "").strip())) for row in rows)
            if f is not None
        ]
        if len(numeric) < 10:
            continue
        mean = statistics.fmean(numeric)
        stdev = statistics.pstdev(numeric)
        if stdev == 0:
            continue
        count = sum(1 for v in numeric if abs(v - mean) / stdev > z_threshold)
        if count:
            outliers[name] = {"count": count, "ratio": round(count / len(numeric), 4)}
    return outliers


def detect_volume_drift(row_count: int, history_counts: list, tolerance: float = 0.5) -> dict:
    """Compare this file's row count to the trailing median. Pure, unit-testable."""
    if len(history_counts) < 3:
        return {"checked": False, "reason": "insufficient history"}
    median = statistics.median(history_counts)
    if median == 0:
        return {"checked": False, "reason": "zero baseline"}
    deviation = (row_count - median) / median
    return {
        "checked": True,
        "baseline_median": median,
        "deviation": round(deviation, 4),
        "anomalous": abs(deviation) > tolerance,
    }


def score_anomalies(outliers: dict, drift: dict, row_count: int) -> dict:
    """Combine outlier and drift signals into one dimension score."""
    outlier_cells = sum(o["count"] for o in outliers.values())
    outlier_penalty = min(0.5, outlier_cells / max(row_count, 1))
    drift_penalty = 0.4 if drift.get("anomalous") else 0.0
    score = max(0.0, 1.0 - outlier_penalty - drift_penalty)
    return {
        "dimension": "anomaly",
        "score": round(score, 4),
        "passed": not drift.get("anomalous") and outlier_penalty < 0.05,
        "outliers": outliers,
        "volume_drift": drift,
    }


def lambda_handler(event, _context):
    dataset, bucket, key = event["dataset"], event["bucket"], event["key"]
    header, rows, _ = read_csv_sample(bucket, key)

    outliers = detect_outliers(header, rows)

    history = RunStore().dataset_history(dataset)
    history_counts = [
        int(item["row_count"])
        for item in history
        if item.get("row_count") is not None and item.get("status") == "PASSED"
    ]
    drift = detect_volume_drift(len(rows), history_counts)

    return score_anomalies(outliers, drift, len(rows))
