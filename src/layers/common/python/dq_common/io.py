import csv
import io
import json

import boto3

_s3 = boto3.client("s3")

# Cap how much of a file we pull into a Lambda for profiling. Files larger
# than this are sampled from the head; full-file checks belong in Glue.
MAX_SAMPLE_BYTES = 16 * 1024 * 1024


def read_csv_sample(bucket: str, key: str, max_rows: int = 5000):
    """Read up to ``max_rows`` records from a CSV object in S3.

    Returns ``(header, rows, total_bytes)`` where rows is a list of dicts.
    """
    head = _s3.head_object(Bucket=bucket, Key=key)
    total_bytes = head["ContentLength"]

    kwargs = {"Bucket": bucket, "Key": key}
    if total_bytes > MAX_SAMPLE_BYTES:
        kwargs["Range"] = f"bytes=0-{MAX_SAMPLE_BYTES - 1}"

    body = _s3.get_object(**kwargs)["Body"].read().decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(body))
    rows = []
    for i, row in enumerate(reader):
        if i >= max_rows:
            break
        # A truncated ranged read can leave a partial last line; DictReader
        # surfaces it as a row with None values, which we drop.
        if None in row.values() and i > 0:
            continue
        rows.append(row)

    header = reader.fieldnames or []
    return header, rows, total_bytes


def read_json_object(bucket: str, key: str) -> dict:
    body = _s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(body)


def write_json_object(bucket: str, key: str, payload) -> None:
    _s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, default=str).encode("utf-8"),
        ContentType="application/json",
    )
