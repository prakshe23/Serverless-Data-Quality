from conftest import load_handler

handler = load_handler("anomaly_detector")


def test_outliers_detected_with_zscore():
    header = ["value"]
    rows = [{"value": "10"} for _ in range(50)] + [{"value": "10000"}]
    outliers = handler.detect_outliers(header, rows)
    assert outliers["value"]["count"] == 1


def test_no_outliers_in_uniform_data():
    header = ["value"]
    rows = [{"value": str(10 + (i % 3))} for i in range(50)]
    assert handler.detect_outliers(header, rows) == {}


def test_volume_drift_needs_history():
    drift = handler.detect_volume_drift(100, [100, 110])
    assert drift["checked"] is False


def test_volume_drift_flags_collapse():
    drift = handler.detect_volume_drift(10, [100, 110, 90, 105])
    assert drift["checked"] is True
    assert drift["anomalous"] is True
    assert drift["deviation"] < -0.5


def test_volume_within_tolerance_passes():
    drift = handler.detect_volume_drift(95, [100, 110, 90, 105])
    assert drift["anomalous"] is False


def test_score_combines_signals():
    result = handler.score_anomalies({}, {"checked": True, "anomalous": False}, 100)
    assert result["score"] == 1.0
    assert result["passed"] is True

    result = handler.score_anomalies(
        {"v": {"count": 2, "ratio": 0.02}},
        {"checked": True, "anomalous": True},
        100,
    )
    assert result["score"] < 0.6
    assert result["passed"] is False
