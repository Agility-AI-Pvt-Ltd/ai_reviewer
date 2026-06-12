import asyncio
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import ProjectReviewReport
from app.services.evaluator import evaluate_project
from app.services.graphify.extractor import extract_graph_summary, run_graphify_for_github
from app.services.review_state import insert_review_state_snapshot


class ReviewState(TypedDict, total=False):
    job_id: str
    github_url: str
    conversation_id: str
    idea_lab_report: IdeaLabReport
    session: AsyncSession
    project_path: str
    graph: dict[str, Any]
    graph_summary: dict
    report: ProjectReviewReport
    error: str


async def requested_node(state: ReviewState) -> ReviewState:
    conversation_id = state["idea_lab_report"].conversation_id
    snapshot_state: dict[str, Any] = {"github_url": state["github_url"], "conversation_id": conversation_id}
    if state.get("job_id"):
        snapshot_state["job_id"] = state["job_id"]
    await insert_review_state_snapshot(
        state["session"],
        conversation_id=conversation_id,
        github_url=state["github_url"],
        stage="requested",
        state=snapshot_state,
        idea_lab_report=state["idea_lab_report"],
    )
    return {"conversation_id": conversation_id}


async def extract_graph_node(state: ReviewState) -> ReviewState:
    project_path, graph = await asyncio.to_thread(run_graphify_for_github, state["github_url"])
    graph_summary = extract_graph_summary(graph)
    project_path_text = str(project_path)
    await insert_review_state_snapshot(
        state["session"],
        conversation_id=state["conversation_id"],
        github_url=state["github_url"],
        stage="graph_extracted",
        project_path=project_path_text,
        state={
            "job_id": state.get("job_id"),
            "github_url": state["github_url"],
            "conversation_id": state["conversation_id"],
            "project_path": project_path_text,
            "graph_summary": graph_summary,
        },
        idea_lab_report=state["idea_lab_report"],
        graph=graph,
        graph_summary=graph_summary,
    )
    return {
        "project_path": project_path_text,
        "graph": graph,
        "graph_summary": graph_summary,
    }


async def evaluate_node(state: ReviewState) -> ReviewState:
    report = await evaluate_project(state["idea_lab_report"], state["graph_summary"])
    await insert_review_state_snapshot(
        state["session"],
        conversation_id=state["conversation_id"],
        github_url=state["github_url"],
        stage="evaluated",
        project_path=state.get("project_path"),
        state={
            "job_id": state.get("job_id"),
            "github_url": state["github_url"],
            "conversation_id": state["conversation_id"],
            "project_path": state.get("project_path"),
            "graph_summary": state["graph_summary"],
            "report": report.model_dump(mode="json"),
        },
        idea_lab_report=state["idea_lab_report"],
        graph=state.get("graph"),
        graph_summary=state["graph_summary"],
        review_report=report,
    )
    return {"report": report}


def build_review_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("requested", requested_node)
    graph.add_node("extract_graph", extract_graph_node)
    graph.add_node("evaluate", evaluate_node)
    graph.set_entry_point("requested")
    graph.add_edge("requested", "extract_graph")
    graph.add_edge("extract_graph", "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()


async def run_review_pipeline(
    github_url: str,
    idea_lab_report: IdeaLabReport,
    session: AsyncSession,
    job_id: str | None = None,
) -> ProjectReviewReport:
    conversation_id = idea_lab_report.conversation_id
    try:
        app = build_review_graph()
        final_state = await app.ainvoke(
            {
                "github_url": github_url,
                "job_id": job_id,
                "conversation_id": conversation_id,
                "idea_lab_report": idea_lab_report,
                "session": session,
            }
        )
        return final_state["report"]
    except Exception as exc:
        await insert_review_state_snapshot(
            session,
            conversation_id=conversation_id,
            github_url=github_url,
            stage="failed",
            state={"job_id": job_id, "github_url": github_url, "conversation_id": conversation_id},
            idea_lab_report=idea_lab_report,
            error=str(exc),
        )
        raise
