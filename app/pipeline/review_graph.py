import asyncio
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import add_trace_metadata, traceable
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


def _state_trace_input(inputs: dict[str, Any]) -> dict[str, Any]:
    state = inputs.get("state", inputs)
    if not isinstance(state, dict):
        return {}
    idea_lab_report = state.get("idea_lab_report")
    graph_summary = state.get("graph_summary") or {}
    return {
        "job_id": state.get("job_id"),
        "github_url": state.get("github_url"),
        "conversation_id": state.get("conversation_id") or getattr(idea_lab_report, "conversation_id", None),
        "project_path": state.get("project_path"),
        "has_graph": "graph" in state,
        "graph_summary_counts": {
            "files": len(graph_summary.get("files", [])) if isinstance(graph_summary, dict) else 0,
            "functions": len(graph_summary.get("functions", [])) if isinstance(graph_summary, dict) else 0,
            "classes": len(graph_summary.get("classes", [])) if isinstance(graph_summary, dict) else 0,
        },
    }


def _state_trace_output(output: dict[str, Any]) -> dict[str, Any]:
    graph_summary = output.get("graph_summary") or {}
    report = output.get("report")
    return {
        "project_path": output.get("project_path"),
        "has_graph": "graph" in output,
        "graph_summary_counts": {
            "files": len(graph_summary.get("files", [])) if isinstance(graph_summary, dict) else 0,
            "functions": len(graph_summary.get("functions", [])) if isinstance(graph_summary, dict) else 0,
            "classes": len(graph_summary.get("classes", [])) if isinstance(graph_summary, dict) else 0,
        },
        "has_report": report is not None,
        "overall_score": getattr(getattr(report, "scores", None), "overall", None),
    }


def _report_trace_output(output: ProjectReviewReport) -> dict[str, Any]:
    return {
        "overall_score": output.scores.overall,
        "alignment_percentage": output.alignment.alignment_percentage,
        "gap_count": len(output.gaps),
        "improvement_count": len(output.improvements),
    }


@traceable(
    name="review.node.requested",
    run_type="chain",
    tags=["review", "langgraph", "requested"],
    process_inputs=_state_trace_input,
    process_outputs=_state_trace_output,
)
async def requested_node(state: ReviewState) -> ReviewState:
    conversation_id = state["idea_lab_report"].conversation_id
    add_trace_metadata(
        {
            "job_id": state.get("job_id"),
            "github_url": state["github_url"],
            "conversation_id": conversation_id,
            "stage": "requested",
        }
    )
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


@traceable(
    name="review.node.extract_graph",
    run_type="chain",
    tags=["review", "langgraph", "graphify"],
    process_inputs=_state_trace_input,
    process_outputs=_state_trace_output,
)
async def extract_graph_node(state: ReviewState) -> ReviewState:
    project_path, graph = await asyncio.to_thread(run_graphify_for_github, state["github_url"])
    graph_summary = extract_graph_summary(graph)
    project_path_text = str(project_path)
    add_trace_metadata(
        {
            "job_id": state.get("job_id"),
            "github_url": state["github_url"],
            "conversation_id": state["conversation_id"],
            "project_path": project_path_text,
            "stage": "graph_extracted",
            "graph_summary_counts": {
                "files": len(graph_summary.get("files", [])),
                "functions": len(graph_summary.get("functions", [])),
                "classes": len(graph_summary.get("classes", [])),
                "call_edges": len(graph_summary.get("call_edges", [])),
                "import_edges": len(graph_summary.get("import_edges", [])),
                "communities": len(graph_summary.get("communities", [])),
            },
        }
    )
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


@traceable(
    name="review.node.evaluate",
    run_type="chain",
    tags=["review", "langgraph", "evaluate"],
    process_inputs=_state_trace_input,
    process_outputs=_state_trace_output,
)
async def evaluate_node(state: ReviewState) -> ReviewState:
    report = await evaluate_project(state["idea_lab_report"], state["graph_summary"])
    add_trace_metadata(
        {
            "job_id": state.get("job_id"),
            "github_url": state["github_url"],
            "conversation_id": state["conversation_id"],
            "stage": "evaluated",
            "overall_score": report.scores.overall,
            "alignment_percentage": report.alignment.alignment_percentage,
        }
    )
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


@traceable(
    name="review.pipeline",
    run_type="chain",
    tags=["review", "langgraph", "pipeline"],
    process_inputs=_state_trace_input,
    process_outputs=_report_trace_output,
)
async def run_review_pipeline(
    github_url: str,
    idea_lab_report: IdeaLabReport,
    session: AsyncSession,
    job_id: str | None = None,
) -> ProjectReviewReport:
    conversation_id = idea_lab_report.conversation_id
    add_trace_metadata(
        {
            "job_id": job_id,
            "github_url": github_url,
            "conversation_id": conversation_id,
        }
    )
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
        add_trace_metadata(
            {
                "job_id": job_id,
                "github_url": github_url,
                "conversation_id": conversation_id,
                "failed": True,
                "error": str(exc),
            }
        )
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
