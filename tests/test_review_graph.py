from pathlib import Path

import pytest

from app.core import database
from app.pipeline import review_graph
from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import Alignment, Architecture, ProjectReviewReport, Scores
from app.services.review_state import list_review_state_snapshots


def _report() -> ProjectReviewReport:
    return ProjectReviewReport(
        scores=Scores(
            overall=8,
            alignment_with_idea=8,
            architecture_quality=7,
            feature_completeness=8,
            code_organization=8,
        ),
        architecture=Architecture(
            pattern="REST API",
            description="The project exposes a clear API surface.",
            strengths=["Simple routing"],
            weaknesses=["Limited tests"],
        ),
        alignment=Alignment(
            alignment_percentage=80,
            implemented_features=["Review endpoint"],
            missing_features=["Dashboard"],
            extra_features=[],
        ),
        gaps=[],
        improvements=[],
        summary="The project is well aligned with the idea and needs more coverage.",
    )


@pytest.mark.asyncio
async def test_langgraph_review_pipeline_persists_node_stages(monkeypatch, client):
    def fake_run_graphify_for_github(github_url: str):
        assert github_url == "https://github.com/example/project"
        return Path("/tmp/project"), {
            "nodes": [{"name": "review_project", "type": "function", "file": "app/api/routes/review.py"}],
            "edges": [],
            "communities": [],
        }

    async def fake_evaluate_project(idea_lab_report, graph_summary):
        assert idea_lab_report.conversation_id == "conv-graph"
        assert graph_summary["functions"] == ["review_project"]
        return _report()

    monkeypatch.setattr(review_graph, "run_graphify_for_github", fake_run_graphify_for_github)
    monkeypatch.setattr(review_graph, "evaluate_project", fake_evaluate_project)

    async with database.AsyncSessionLocal() as session:
        report = await review_graph.run_review_pipeline(
            "https://github.com/example/project",
            IdeaLabReport(conversation_id="conv-graph", idea_fit="Build a review API"),
            session,
        )
        snapshots = await list_review_state_snapshots(session, "conv-graph")

    assert report.summary == "The project is well aligned with the idea and needs more coverage."
    assert [snapshot.stage for snapshot in snapshots] == ["requested", "graph_extracted", "evaluated"]
    assert snapshots[1].graph_summary["functions"] == ["review_project"]
    assert snapshots[2].review_report["scores"]["overall"] == 8.0
