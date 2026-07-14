"""Entry point of the pipeline.

Fired by EventBridge when an object lands in the raw zone of the data lake
bucket. Validates the object is a candidate for quality checking, registers
the run in DynamoDB and starts the Step Functions Express workflow.
"""

import json
import os
import uuid

import boto3

from dq_common import RunStore, now_iso

_sfn = boto3.client("stepfunctions")

STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]
RAW_PREFIX = os.environ.get("RAW_PREFIX", "raw/")
SUPPORTED_EXTENSIONS = (".csv",)


def _dataset_from_key(key: str) -> str | None:
    """raw/<dataset>/<file> -> <dataset>"""
    if not key.startswith(RAW_PREFIX):
        return None
    parts = key[len(RAW_PREFIX):].split("/")
    return parts[0] if len(parts) >= 2 and parts[0] else None


def lambda_handler(event, _context):
    detail = event.get("detail", {})
    bucket = detail.get("bucket", {}).get("name")
    key = detail.get("object", {}).get("key")

    if not bucket or not key:
        return {"skipped": True, "reason": "not an S3 object event"}

    if not key.lower().endswith(SUPPORTED_EXTENSIONS):
        return {"skipped": True, "reason": f"unsupported file type: {key}"}

    dataset = _dataset_from_key(key)
    if dataset is None:
        return {"skipped": True, "reason": f"key outside {RAW_PREFIX}<dataset>/ layout: {key}"}

    run_id = uuid.uuid4().hex
    RunStore().create_run(run_id, dataset, bucket, key)

    execution_input = {
        "run_id": run_id,
        "dataset": dataset,
        "bucket": bucket,
        "key": key,
        "triggered_at": now_iso(),
    }
    _sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=f"dq-{dataset}-{run_id}"[:80],
        input=json.dumps(execution_input),
    )
    return {"started": True, "run_id": run_id, "dataset": dataset}
