import decimal
import json
import os

import boto3

from dq_common.util import now_iso


def _to_dynamo(obj):
    """DynamoDB rejects float; round-trip through JSON with Decimal parsing."""
    return json.loads(json.dumps(obj, default=str), parse_float=decimal.Decimal)


class RunStore:
    """Persistence for pipeline run records in DynamoDB.

    Table schema:
      pk = "RUN#<run_id>"           sk = "META"           -> run record
      pk = "DATASET#<dataset>"      sk = "RUN#<timestamp>" -> per-dataset history
    """

    def __init__(self, table_name: str | None = None):
        table_name = table_name or os.environ["RUNS_TABLE"]
        self._table = boto3.resource("dynamodb").Table(table_name)

    def create_run(self, run_id: str, dataset: str, bucket: str, key: str) -> dict:
        record = {
            "pk": f"RUN#{run_id}",
            "sk": "META",
            "run_id": run_id,
            "dataset": dataset,
            "bucket": bucket,
            "key": key,
            "status": "RUNNING",
            "started_at": now_iso(),
        }
        self._table.put_item(Item=record)
        return record

    def finish_run(self, run_id: str, dataset: str, status: str, report: dict) -> None:
        timestamp = now_iso()
        self._table.update_item(
            Key={"pk": f"RUN#{run_id}", "sk": "META"},
            UpdateExpression="SET #s = :s, finished_at = :t, report = :r",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": status,
                ":t": timestamp,
                ":r": _to_dynamo(report),
            },
        )
        self._table.put_item(
            Item=_to_dynamo(
                {
                    "pk": f"DATASET#{dataset}",
                    "sk": f"RUN#{timestamp}#{run_id}",
                    "run_id": run_id,
                    "status": status,
                    "overall_score": report.get("overall_score"),
                    "row_count": report.get("row_count"),
                    "finished_at": timestamp,
                }
            )
        )

    def get_run(self, run_id: str) -> dict | None:
        item = self._table.get_item(Key={"pk": f"RUN#{run_id}", "sk": "META"}).get("Item")
        return item

    def dataset_history(self, dataset: str, limit: int = 20) -> list:
        result = self._table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk)",
            ExpressionAttributeValues={":pk": f"DATASET#{dataset}", ":sk": "RUN#"},
            ScanIndexForward=False,
            Limit=limit,
        )
        return result.get("Items", [])
