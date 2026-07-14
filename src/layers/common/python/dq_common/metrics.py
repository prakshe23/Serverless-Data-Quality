import os

import boto3

_cloudwatch = boto3.client("cloudwatch")

NAMESPACE = os.environ.get("METRICS_NAMESPACE", "DataQuality")


def emit_quality_metric(name: str, value: float, dataset: str, unit: str = "None") -> None:
    """Publish a custom CloudWatch metric dimensioned by dataset."""
    _cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[
            {
                "MetricName": name,
                "Dimensions": [{"Name": "Dataset", "Value": dataset}],
                "Value": value,
                "Unit": unit,
            }
        ],
    )
