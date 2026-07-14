from conftest import load_handler

handler = load_handler("data_profiler")


def test_profile_computes_completeness_and_stats():
    header = ["id", "amount", "note"]
    rows = [
        {"id": "1", "amount": "10.0", "note": "ok"},
        {"id": "2", "amount": "20.0", "note": ""},
        {"id": "3", "amount": "30.0", "note": "fine"},
        {"id": "4", "amount": "", "note": "meh"},
    ]
    result = handler.profile_rows(header, rows)

    assert result["row_count"] == 4
    assert result["column_count"] == 3
    assert result["columns"]["id"]["completeness"] == 1.0
    assert result["columns"]["amount"]["null_count"] == 1
    assert result["columns"]["amount"]["min"] == 10.0
    assert result["columns"]["amount"]["max"] == 30.0
    assert result["columns"]["amount"]["mean"] == 20.0
    # note column is text: no numeric stats
    assert "mean" not in result["columns"]["note"]


def test_empty_file_scores_gracefully():
    result = handler.profile_rows([], [])
    assert result["row_count"] == 0
    assert result["score"] == 1.0


def test_unique_id_column_has_full_uniqueness():
    header = ["id"]
    rows = [{"id": str(i)} for i in range(10)]
    result = handler.profile_rows(header, rows)
    assert result["columns"]["id"]["distinct_count"] == 10
    assert result["avg_uniqueness"] == 1.0
