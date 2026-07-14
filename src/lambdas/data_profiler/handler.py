"""Profiles a sample of the file: completeness, uniqueness and basic stats.

Produces the "completeness" and "uniqueness" quality dimensions consumed by
the quality scorer, plus per-column statistics stored with the run report.
"""

import statistics

from dq_common import read_csv_sample


def _try_float(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def profile_rows(header: list, rows: list) -> dict:
    """Pure profiling logic, unit-testable without AWS."""
    row_count = len(rows)
    columns = {}
    completeness_scores = []
    uniqueness_scores = []

    for name in header:
        values = [(row.get(name) or "").strip() for row in rows]
        non_null = [v for v in values if v]
        null_count = row_count - len(non_null)
        distinct = len(set(non_null))

        completeness = len(non_null) / row_count if row_count else 1.0
        uniqueness = distinct / len(non_null) if non_null else 0.0
        completeness_scores.append(completeness)
        uniqueness_scores.append(uniqueness)

        stats = {
            "null_count": null_count,
            "distinct_count": distinct,
            "completeness": round(completeness, 4),
        }

        numeric = [f for f in (_try_float(v) for v in non_null) if f is not None]
        if numeric and len(numeric) >= max(1, int(0.9 * len(non_null))):
            stats.update(
                {
                    "min": min(numeric),
                    "max": max(numeric),
                    "mean": round(statistics.fmean(numeric), 4),
                    "stdev": round(statistics.pstdev(numeric), 4) if len(numeric) > 1 else 0.0,
                }
            )
        columns[name] = stats

    overall_completeness = (
        statistics.fmean(completeness_scores) if completeness_scores else 1.0
    )
    return {
        "dimension": "profile",
        "score": round(overall_completeness, 4),
        "row_count": row_count,
        "column_count": len(header),
        "avg_uniqueness": round(statistics.fmean(uniqueness_scores), 4)
        if uniqueness_scores
        else 0.0,
        "columns": columns,
    }


def lambda_handler(event, _context):
    header, rows, total_bytes = read_csv_sample(event["bucket"], event["key"])
    result = profile_rows(header, rows)
    result["file_bytes"] = total_bytes
    return result
