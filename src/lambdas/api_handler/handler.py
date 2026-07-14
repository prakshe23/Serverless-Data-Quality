"""REST API for quality results, behind API Gateway (HTTP API).

Routes:
  GET  /runs/{run_id}           -> full run report from DynamoDB
  GET  /datasets/{name}/runs    -> recent run history for a dataset
  POST /query                   -> run a SQL query over the Athena metrics
                                   table and return the rows (bounded)

The /query route is what dashboards use for trend analysis, e.g.::

    SELECT dataset, date_trunc('day', from_iso8601_timestamp(finished_at)) d,
           avg(overall_score) FROM quality_metrics GROUP BY 1, 2
"""

import json
import os
import time

import boto3

from dq_common import RunStore, response

_athena = boto3.client("athena")

ATHENA_DATABASE = os.environ["ATHENA_DATABASE"]
ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
QUERY_TIMEOUT_SECONDS = 25
MAX_RESULT_ROWS = 500


def _run_athena_query(sql: str) -> dict:
    execution = _athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        WorkGroup=ATHENA_WORKGROUP,
    )
    query_id = execution["QueryExecutionId"]

    deadline = time.time() + QUERY_TIMEOUT_SECONDS
    while True:
        state = _athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"][
            "Status"
        ]
        if state["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.time() > deadline:
            _athena.stop_query_execution(QueryExecutionId=query_id)
            return {"error": "query timed out", "query_id": query_id}
        time.sleep(0.5)

    if state["State"] != "SUCCEEDED":
        return {
            "error": state.get("StateChangeReason", state["State"]),
            "query_id": query_id,
        }

    result = _athena.get_query_results(QueryExecutionId=query_id, MaxResults=MAX_RESULT_ROWS)
    rows = [
        [col.get("VarCharValue") for col in row["Data"]]
        for row in result["ResultSet"]["Rows"]
    ]
    header, data = (rows[0], rows[1:]) if rows else ([], [])
    return {
        "query_id": query_id,
        "columns": header,
        "rows": data,
    }


def lambda_handler(event, _context):
    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}

    if route == "GET /runs/{run_id}":
        run = RunStore().get_run(params["run_id"])
        if run is None:
            return response(404, {"error": "run not found"})
        return response(200, run)

    if route == "GET /datasets/{name}/runs":
        history = RunStore().dataset_history(params["name"])
        return response(200, {"dataset": params["name"], "runs": history})

    if route == "POST /query":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return response(400, {"error": "invalid JSON body"})
        sql = (body.get("sql") or "").strip()
        if not sql:
            return response(400, {"error": "missing 'sql'"})
        if not sql.lower().startswith(("select", "with")):
            return response(400, {"error": "only read queries are allowed"})
        result = _run_athena_query(sql)
        status = 400 if "error" in result else 200
        return response(status, result)

    return response(404, {"error": f"unknown route {route}"})
