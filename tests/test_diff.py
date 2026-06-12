from app.services.diff import diff_reports


def test_diff_reports_tracks_nested_changes():
    before = {"scores": {"overall": 5, "quality": 6}, "summary": "old"}
    after = {"scores": {"overall": 7, "quality": 6}, "summary": "new"}

    assert diff_reports(before, after) == {
        "scores": {"overall": {"before": 5, "after": 7}},
        "summary": {"before": "old", "after": "new"},
    }
