import asyncio
import logging

from app.core import database
from app.core.config import settings
from app.pipeline.review_graph import run_review_pipeline
from app.services.idea_lab import get_idea_lab_report
from app.services.review_queue import (
    find_next_queued_job,
    insert_review_job_event,
    is_missing_queue_table_error,
)
from app.utils.file_handler import cleanup_cloned_repository

logger = logging.getLogger(__name__)


class ReviewQueueWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="review-queue-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        logger.info("review_worker.started")
        while not self._stop.is_set():
            try:
                did_work = await self._run_once()
                if not did_work:
                    await asyncio.sleep(settings.review_worker_poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if is_missing_queue_table_error(exc):
                    logger.error(
                        "review_worker.schema_missing: required Postgres table is missing. "
                        "Run db/schema.sql with a migration/admin DB role, or set "
                        "up the local database with python script/setup.py."
                    )
                    self._stop.set()
                    continue
                logger.exception("review_worker.loop_error")
                await asyncio.sleep(settings.review_worker_poll_seconds)
        logger.info("review_worker.stopped")

    async def _run_once(self) -> bool:
        async with database.AsyncSessionLocal() as session:
            queued_event = await find_next_queued_job(
                session,
                stale_after_seconds=settings.review_worker_stale_seconds,
            )
            if queued_event is None:
                return False

            await insert_review_job_event(
                session,
                job_id=queued_event.job_id,
                conversation_id=queued_event.conversation_id,
                github_url=queued_event.github_url,
                event_type="started",
                payload={"queued_event_id": queued_event.id},
            )

            try:
                await insert_review_job_event(
                    session,
                    job_id=queued_event.job_id,
                    conversation_id=queued_event.conversation_id,
                    github_url=queued_event.github_url,
                    event_type="idea_lab_loading",
                    payload={
                        "message": "Loading the selected Idea Lab report.",
                        "conversation_id": queued_event.conversation_id,
                    },
                )
                idea_lab_report = await get_idea_lab_report(session, queued_event.conversation_id)
                await insert_review_job_event(
                    session,
                    job_id=queued_event.job_id,
                    conversation_id=queued_event.conversation_id,
                    github_url=queued_event.github_url,
                    event_type="idea_lab_loaded",
                    payload={
                        "message": "Idea Lab report loaded and ready for comparison.",
                        "conversation_id": idea_lab_report.conversation_id,
                    },
                )
                report = await run_review_pipeline(
                    queued_event.github_url,
                    idea_lab_report,
                    session,
                    job_id=queued_event.job_id,
                )
            except Exception as exc:
                await insert_review_job_event(
                    session,
                    job_id=queued_event.job_id,
                    conversation_id=queued_event.conversation_id,
                    github_url=queued_event.github_url,
                    event_type="failed",
                    payload={"queued_event_id": queued_event.id},
                    error=str(exc),
                )
                logger.exception("review_worker.job_failed job_id=%s", queued_event.job_id)
                return True

            await insert_review_job_event(
                session,
                job_id=queued_event.job_id,
                conversation_id=queued_event.conversation_id,
                github_url=queued_event.github_url,
                event_type="completed",
                payload={"report": report.model_dump(mode="json")},
            )
            try:
                deleted = cleanup_cloned_repository(
                    queued_event.github_url,
                    settings.projects_dir,
                )
                logger.info(
                    "review_worker.cleanup_completed job_id=%s deleted=%s",
                    queued_event.job_id,
                    deleted,
                )
            except Exception:
                logger.exception(
                    "review_worker.cleanup_failed job_id=%s",
                    queued_event.job_id,
                )
            logger.info("review_worker.job_completed job_id=%s", queued_event.job_id)
            return True


review_queue_worker = ReviewQueueWorker()
