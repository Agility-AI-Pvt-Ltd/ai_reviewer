from app.services import evaluator


def test_review_prompt_allows_zero_alignment_for_unrelated_projects():
    expected = "valid to assign 0 for scores.alignment_with_idea"

    assert expected in evaluator.load_review_prompt()
    assert expected in evaluator.FALLBACK_REVIEW_PROMPT
