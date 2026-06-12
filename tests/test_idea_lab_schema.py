import datetime as dt

from app.schemas.idea_lab import IdeaLabReport


class FeasibilityReportRow:
    id = 1
    conversation_id = "conv-strings"
    chain_of_thought = [
        "Step 1: Extract explicit features.",
        "Step 2: Identify user pain points.",
    ]
    idea_fit = "A focused product reviewer."
    competitors = None
    opportunity = None
    score = "8/10"
    targeting = None
    next_step = None
    created_at = dt.datetime(2026, 1, 1)


def test_idea_lab_report_accepts_string_chain_of_thought_items():
    report = IdeaLabReport.from_orm_report(FeasibilityReportRow())

    assert report.chain_of_thought == [
        {"step": 1, "text": "Step 1: Extract explicit features."},
        {"step": 2, "text": "Step 2: Identify user pain points."},
    ]
