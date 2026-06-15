import asyncio
import json
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core import database
from app.core.config import settings
from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import ProjectReviewReport
from app.services.evaluator import evaluate_project
from app.services.graphify.extractor import extract_graph_summary, run_graphify_for_github
from app.services.review_state import insert_review_state_snapshot

ReportCallback = Callable[[ProjectReviewReport], Awaitable[None]]


class ProjectReviewer:
    def __init__(
        self,
        github_url: str,
        idea_lab_report: IdeaLabReport,
        on_report_update: ReportCallback,
    ) -> None:
        self.github_url = github_url
        self.idea_lab_report = idea_lab_report
        self.on_report_update = on_report_update
        self.project_path: Path | None = None
        self.graph_json: Path | None = None
        self.watch_process: subprocess.Popen | None = None
        self._poll_task: asyncio.Task | None = None
        self._debounce: asyncio.Task | None = None

    async def start(self) -> None:
        await self._persist_state(
            "requested",
            state={
                "github_url": self.github_url,
                "conversation_id": self.idea_lab_report.conversation_id,
                "mode": "watch",
            },
        )
        try:
            self.project_path, graph = await asyncio.to_thread(run_graphify_for_github, self.github_url)
            self.graph_json = self.project_path / "graphify-out" / "graph.json"
            await self._evaluate_graph(graph)
        except Exception as exc:
            await self._persist_state(
                "failed",
                state={
                    "github_url": self.github_url,
                    "conversation_id": self.idea_lab_report.conversation_id,
                    "mode": "watch",
                },
                error=str(exc),
            )
            raise

        self.watch_process = subprocess.Popen(
            [settings.graphify_command, "watch", str(self.project_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._poll_task = asyncio.create_task(self._poll_graph())

    async def _poll_graph(self) -> None:
        last_mtime = self.graph_json.stat().st_mtime if self.graph_json and self.graph_json.exists() else 0
        while True:
            await asyncio.sleep(5)
            if not self.graph_json or not self.graph_json.exists():
                continue
            mtime = self.graph_json.stat().st_mtime
            if mtime == last_mtime:
                continue
            last_mtime = mtime
            if self._debounce:
                self._debounce.cancel()
            self._debounce = asyncio.create_task(self._debounced_evaluate())

    async def _debounced_evaluate(self) -> None:
        await asyncio.sleep(30)
        if not self.graph_json or not self.graph_json.exists():
            return
        graph = json.loads(self.graph_json.read_text(encoding="utf-8"))
        await self._evaluate_graph(graph)

    async def _evaluate_graph(self, graph: dict) -> None:
        summary = extract_graph_summary(graph)
        await self._persist_state(
            "graph_extracted",
            state={
                "github_url": self.github_url,
                "conversation_id": self.idea_lab_report.conversation_id,
                "mode": "watch",
                "project_path": str(self.project_path) if self.project_path else None,
                "graph_summary": summary,
            },
            graphify_graph_json=graph,
            graph=graph,
            graph_summary=summary,
        )
        try:
            report = await evaluate_project(self.idea_lab_report, summary)
        except Exception as exc:
            await self._persist_state(
                "failed",
                state={
                    "github_url": self.github_url,
                    "conversation_id": self.idea_lab_report.conversation_id,
                    "mode": "watch",
                    "project_path": str(self.project_path) if self.project_path else None,
                    "graph_summary": summary,
                },
                graphify_graph_json=graph,
                graph=graph,
                graph_summary=summary,
                error=str(exc),
            )
            raise

        await self._persist_state(
            "evaluated",
            state={
                "github_url": self.github_url,
                "conversation_id": self.idea_lab_report.conversation_id,
                "mode": "watch",
                "project_path": str(self.project_path) if self.project_path else None,
                "graph_summary": summary,
                "report": report.model_dump(mode="json"),
            },
            graphify_graph_json=graph,
            graph=graph,
            graph_summary=summary,
            review_report=report,
        )
        await self.on_report_update(report)

    async def _persist_state(
        self,
        stage: str,
        *,
        state: dict,
        graphify_graph_json: dict | None = None,
        graph: dict | None = None,
        graph_summary: dict | None = None,
        review_report: ProjectReviewReport | None = None,
        error: str | None = None,
    ) -> None:
        async with database.AsyncSessionLocal() as session:
            await insert_review_state_snapshot(
                session,
                conversation_id=self.idea_lab_report.conversation_id,
                github_url=self.github_url,
                stage=stage,
                state=state,
                idea_lab_report=self.idea_lab_report,
                project_path=str(self.project_path) if self.project_path else None,
                graphify_graph_json=graphify_graph_json,
                graph=graph,
                graph_summary=graph_summary,
                review_report=review_report,
                error=error,
            )

    def stop(self) -> None:
        if self._debounce:
            self._debounce.cancel()
        if self._poll_task:
            self._poll_task.cancel()
        if self.watch_process:
            self.watch_process.terminate()
