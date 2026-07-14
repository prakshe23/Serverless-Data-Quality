"""Terminal state for files that pass (or pass with warnings).

- Copies the raw object into the curated zone.
- Writes the quality report as JSON Lines into the Hive-partitioned
  ``metrics/`` prefix that the Glue crawler catalogs for Athena.
- Marks the run finished in DynamoDB.
"""

import datetime
import json
import os

import boto3

from dq_common import RunStore

_s3 = boto3.client("s3")

LAKE_BUCKET = os.environ["LAKE_BUCKET"]
CURATED_PREFIX = os.environ.get("CURATED_PREFIX", "curated/")
METRICS_PREFIX = os.environ.get("METRICS_PREFIX", "metrics/")


def metrics_record(report: dict, finished_at: str) -> dict:
    """Flatten the report into the row shape of the Athena metrics table."""
    dimensions = report.get("dimensions", {})
    return {
        "run_id": report["run_id"],
        "dataset": report["dataset"],
        "source_key": report["key"],
        "verdict": report["verdict"],
        "overall_score": report["overall_score"],
        "schema_score": dimensions.get("schema", {}).get("score"),
        "profile_score": dimensions.get("profile", {}).get("score"),
        "pii_score": dimensions.get("pii", {}).get("score"),
        "anomaly_score": dimensions.get("anomaly", {}).get("score"),
        "row_count": report.get("row_count"),
        "finished_at": finished_at,
    }


def lambda_handler(event, _context):
    report = event
    run_id, dataset, key = report["run_id"], report["dataset"], report["key"]
    now = datetime.datetime.now(datetime.timezone.utc)

    curated_key = f"{CURATED_PREFIX}{dataset}/{os.path.basename(key)}"
    _s3.copy_object(
        Bucket=LAKE_BUCKET,
        CopySource={"Bucket": report["bucket"], "Key": key},
        Key=curated_key,
    )

    metrics_key = (
        f"{METRICS_PREFIX}year={now:%Y}/month={now:%m}/day={now:%d}/{run_id}.json"
    )
    record = metrics_record(report, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    _s3.put_object(
        Bucket=LAKE_BUCKET,
        Key=metrics_key,
        Body=(json.dumps(record) + "\n").encode("utf-8"),
        ContentType="application/json",
    )

    RunStore().finish_run(run_id, dataset, report["verdict"], report)

    return {
        "run_id": run_id,
        "verdict": report["verdict"],
        "curated_key": curated_key,
        "metrics_key": metrics_key,
    }
