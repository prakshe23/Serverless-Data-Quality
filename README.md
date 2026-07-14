# Serverless Data Quality Pipeline

An AI-enhanced, fully serverless data quality pipeline on AWS. Files landing
in a data lake are automatically validated against schema contracts,
profiled, scanned for PII with **Amazon Comprehend**, and checked for
statistical anomalies — then routed to a curated zone or quarantined, with
every result queryable through **Athena** and a REST API.

## Architecture

```mermaid
flowchart LR
    subgraph Ingest
        S3[(S3 data lake\nraw/)] -->|Object Created| EB[EventBridge rule]
        EB --> IT[Lambda\ningestion_trigger]
    end

    IT --> SFN{{Step Functions\nExpress Workflow}}

    subgraph Checks [Parallel quality checks]
        SFN --> SV[Lambda\nschema_validator]
        SFN --> DP[Lambda\ndata_profiler]
        SFN --> PII[Lambda\npii_detector] --> CMP[Amazon\nComprehend]
        SFN --> AD[Lambda\nanomaly_detector]
    end

    SV & DP & PII & AD --> QS[Lambda\nquality_scorer]
    QS -->|PASSED / WARNED| RW[Lambda\nresults_writer]
    QS -->|FAILED| RM[Lambda\nremediation]

    RW --> CUR[(S3 curated/ + metrics/)]
    RM --> Q[(S3 quarantine/)]
    RM --> SNS[SNS alerts]

    CUR --> GC[Glue crawlers\n+ Data Catalog]
    GC --> ATH[Athena workgroup]

    DDB[(DynamoDB\nrun store)] <--> IT & QS & RW & RM & AD
    ATH & DDB --> API[Lambda api_handler] --> APIGW[API Gateway\nHTTP API]

    QS --> CW[CloudWatch\nmetrics, dashboard, alarms] --> SNS
```

### The eleven AWS services

| # | Service | Role in the pipeline |
|---|---------|----------------------|
| 1 | **S3** | Data lake zones: `raw/`, `curated/`, `quarantine/`, `metrics/`; schema contracts; Athena results |
| 2 | **EventBridge** | Watches the raw zone and fires the pipeline on every new object |
| 3 | **Lambda** | Nine functions: trigger, four checks, scorer, writer, remediation, API |
| 4 | **Step Functions** | Express Workflow fanning the checks out in parallel and routing on the verdict |
| 5 | **Comprehend** | AI-powered PII entity detection (plus language detection) on sampled cell text |
| 6 | **DynamoDB** | Run store: per-run reports and per-dataset history (also the anomaly baseline) |
| 7 | **SNS** | Alerting channel for failed files, workflow crashes and CloudWatch alarms |
| 8 | **Glue** | Data Catalog database + crawlers cataloging quality metrics and curated data |
| 9 | **Athena** | SQL over the quality metrics (workgroup, named trend queries) |
| 10 | **CloudWatch** | Custom quality metrics, dashboard, failure alarms, all logs |
| 11 | **API Gateway** | HTTP API exposing run reports, dataset history and ad-hoc Athena queries |

X-Ray tracing is enabled across Lambda and Step Functions as a bonus.

## How a file flows through

1. A producer drops `raw/<dataset>/<file>.csv` into the lake bucket.
2. EventBridge matches the `Object Created` event and invokes
   `ingestion_trigger`, which registers a run in DynamoDB and starts the
   Express workflow.
3. Four checks run **in parallel**, each on a bounded sample of the file:
   - `schema_validator` — columns, types and required fields against the
     contract at `schemas/<dataset>.json` in the config bucket.
   - `data_profiler` — completeness, uniqueness, per-column statistics.
   - `pii_detector` — packs cell text into Comprehend
     `DetectPiiEntities` calls; unexpected PII columns are penalized and
     high-risk types (SSN, credit card, …) fail the file outright unless the
     contract's `pii_allowed` list expects them.
   - `anomaly_detector` — z-score outliers within the file plus volume
     drift against the dataset's own run history in DynamoDB.
4. `quality_scorer` combines the dimensions with weights
   (schema 0.35, PII 0.25, profile 0.20, anomaly 0.20) into an overall score
   and a verdict: `PASSED` / `WARNED` / `FAILED`, with hard-fail overrides
   for leaked high-risk PII and missing columns.
5. **PASSED/WARNED** → `results_writer` copies the file to `curated/` and
   appends a JSON metrics record to the Hive-partitioned `metrics/` prefix.
   **FAILED** (or a workflow error, via Catch) → `remediation` moves the
   file to `quarantine/` and publishes an SNS alert.
6. Glue crawlers keep the Data Catalog in sync so Athena can answer
   questions like "which dataset's quality is trending down this month?"
   — two named queries ship with the stack.

## Repository layout

```
infrastructure/terraform/   All eleven services as Terraform (one file per service)
  templates/                Step Functions ASL definition (templated ARNs)
src/lambdas/<name>/         One directory per Lambda function
src/layers/common/          Shared Lambda layer (S3/DynamoDB/CloudWatch helpers)
tests/                      Unit tests for the pure check/scoring logic
samples/                    Example dataset + schema contract
```

## Deploy

Prerequisites: Terraform >= 1.5, AWS credentials, a region where Comprehend
is available (default `us-east-1`).

```bash
make apply                     # terraform init + apply
make seed                      # upload sample contract + trigger a sample run
```

Optionally subscribe to alerts:

```bash
terraform -chdir=infrastructure/terraform apply -var alert_email=you@example.com
```

## Use the API

```bash
API=$(terraform -chdir=infrastructure/terraform output -raw api_endpoint)

# Recent runs for a dataset
curl "$API/datasets/customers/runs"

# Full report for one run
curl "$API/runs/<run_id>"

# Ad-hoc trend query through Athena
curl -X POST "$API/query" -H 'content-type: application/json' -d '{
  "sql": "SELECT dataset, avg(overall_score) FROM metrics GROUP BY 1"
}'
```

> The `/query` route only accepts read queries and runs inside a workgroup
> with a 1 GiB scan cutoff. For production, put an authorizer on the API.

## Schema contracts

Quality expectations per dataset live at `schemas/<dataset>.json` in the
config bucket:

```json
{
  "columns": [
    {"name": "customer_id", "type": "integer", "required": true},
    {"name": "email",       "type": "string",  "required": true},
    {"name": "signup_date", "type": "date",    "required": true}
  ],
  "allow_extra_columns": false,
  "pii_allowed": ["email"]
}
```

Supported types: `string`, `integer`, `number`, `date`, `timestamp`,
`boolean`. Datasets without a contract pass the schema dimension with an
advisory `no_contract` flag, so onboarding a new feed never blocks it.

## Develop

```bash
pip install -r requirements-dev.txt
make test        # pure-logic unit tests, no AWS needed
make fmt         # terraform fmt
```

## Cost notes

Everything is pay-per-use: Express Workflows are billed per transition,
DynamoDB is on-demand, Athena per TB scanned (capped per query), and
Comprehend per 100-character unit — the PII detector bounds its sample to
keep that predictable. An idle deployment costs approximately nothing.
