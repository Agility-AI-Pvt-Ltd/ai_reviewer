from app.services import evaluator


def test_review_prompt_allows_zero_alignment_for_unrelated_projects():
    expected = "valid to assign 0 for scores.alignment_with_idea"

    assert expected in evaluator.load_review_prompt()
    assert expected in evaluator.FALLBACK_REVIEW_PROMPT


def test_review_prompt_rewards_strong_idea_matches():
    expected = "90-100 alignment_percentage and 9-10 scores.alignment_with_idea"
    sparse_graph_guardrail = "do not punish alignment when the available evidence strongly matches"

    assert expected in evaluator.load_review_prompt()
    assert expected in evaluator.FALLBACK_REVIEW_PROMPT
    assert sparse_graph_guardrail in evaluator.load_review_prompt()
    assert sparse_graph_guardrail in evaluator.FALLBACK_REVIEW_PROMPT
