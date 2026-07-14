from conftest import load_handler

handler = load_handler("quality_scorer")

RUN = {
    "run_id": "abc123",
    "dataset": "customers",
    "bucket": "lake",
    "key": "raw/customers/2026-07-13.csv",
}


def _checks(schema=1.0, profile=1.0, pii=1.0, anomaly=1.0, overrides=None):
    checks = [
        {"dimension": "schema", "score": schema, "violations": []},
        {"dimension": "profile", "score": profile, "row_count": 100},
        {"dimension": "pii", "score": pii, "findings": []},
        {"dimension": "anomaly", "score": anomaly},
    ]
    for check in checks:
        check.update((overrides or {}).get(check["dimension"], {}))
    return checks


def test_perfect_checks_pass():
    report = handler.build_report(RUN, _checks())
    assert report["verdict"] == "PASSED"
    assert report["overall_score"] == 1.0
    assert report["row_count"] == 100
    assert report["run_id"] == "abc123"


def test_weighted_average():
    report = handler.build_report(RUN, _checks(schema=0.0))
    # schema weight is 0.35 -> 0.65 overall
    assert report["overall_score"] == 0.65


def test_low_score_fails():
    report = handler.build_report(RUN, _checks(schema=0.2, pii=0.4, anomaly=0.5))
    assert report["verdict"] == "FAILED"


def test_mid_score_warns():
    report = handler.build_report(RUN, _checks(schema=0.5, profile=0.8))
    assert report["verdict"] == "WARNED"


def test_high_risk_pii_is_hard_fail_even_with_good_score():
    checks = _checks(
        overrides={"pii": {"score": 0.9, "findings": [{"high_risk": True, "allowed": False}]}}
    )
    report = handler.build_report(RUN, checks)
    assert report["verdict"] == "FAILED"


def test_missing_column_is_hard_fail():
    checks = _checks(
        overrides={
            "schema": {
                "score": 0.9,
                "violations": [{"type": "missing_column", "column": "id"}],
            }
        }
    )
    report = handler.build_report(RUN, checks)
    assert report["verdict"] == "FAILED"
