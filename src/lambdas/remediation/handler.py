"""Terminal state for files that fail quality checks or crash the workflow.

Quarantines the object (move to ``quarantine/``), records the failed run and
notifies data owners through SNS. Also handles workflow-level errors caught
by the state machine's Catch, in which case there is no report — just the
error payload.
"""

import json
import os

import boto3

from dq_common import RunStore, now_iso

_s3 = boto3.client("s3")
_sns = boto3.client("sns")

LAKE_BUCKET = os.environ["LAKE_BUCKET"]
QUARANTINE_PREFIX = os.environ.get("QUARANTINE_PREFIX", "quarantine/")
ALERT_TOPIC_ARN = os.environ["ALERT_TOPIC_ARN"]


def _quarantine(bucket: str, key: str, dataset: str) -> str:
    quarantine_key = f"{QUARANTINE_PREFIX}{dataset}/{os.path.basename(key)}"
    _s3.copy_object(
        Bucket=LAKE_BUCKET,
        CopySource={"Bucket": bucket, "Key": key},
        Key=quarantine_key,
    )
    _s3.delete_object(Bucket=bucket, Key=key)
    return quarantine_key


def lambda_handler(event, _context):
    if "error" in event:
        # Workflow crashed mid-check: event = {"run": {...}, "error": {...}}
        run = event["run"]
        report = {
            "run_id": run["run_id"],
            "dataset": run["dataset"],
            "overall_score": 0.0,
            "verdict": "ERRORED",
            "error": event["error"],
        }
        bucket, key = run["bucket"], run["key"]
    else:
        report = event
        bucket, key = report["bucket"], report["key"]

    run_id, dataset = report["run_id"], report["dataset"]
    quarantine_key = _quarantine(bucket, key, dataset)

    status = report.get("verdict", "FAILED")
    RunStore().finish_run(run_id, dataset, status, report)

    failed_dimensions = [
        name
        for name, result in report.get("dimensions", {}).items()
        if not result.get("passed", True)
    ]
    _sns.publish(
        TopicArn=ALERT_TOPIC_ARN,
        Subject=f"[data-quality] {dataset} file {status.lower()}"[:100],
        Message=json.dumps(
            {
                "run_id": run_id,
                "dataset": dataset,
                "status": status,
                "overall_score": report.get("overall_score"),
                "failed_dimensions": failed_dimensions,
                "quarantine_key": quarantine_key,
                "error": report.get("error"),
                "at": now_iso(),
            },
            indent=2,
            default=str,
        ),
    )

    return {"run_id": run_id, "status": status, "quarantine_key": quarantine_key}
