from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import database
from app.core.dependencies import verify_websocket_internal_auth
from app.services.graphify.watcher import ProjectReviewer
from app.services.idea_lab import get_idea_lab_report

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/review/{conversation_id}")
async def review_socket(websocket: WebSocket, conversation_id: str) -> None:
    auth_payload = verify_websocket_internal_auth(websocket)
    if auth_payload is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    init_payload = await websocket.receive_json()
    github_url = init_payload.get("github_url")
    if not github_url:
        await websocket.send_json({"type": "error", "detail": "github_url is required"})
        await websocket.close(code=1003)
        return

    async with database.AsyncSessionLocal() as idea_lab_session:
        idea_lab_report = await get_idea_lab_report(idea_lab_session, conversation_id)

    async def push_update(report) -> None:
        await websocket.send_json({"type": "report_update", "data": report.model_dump()})

    reviewer = ProjectReviewer(
        github_url=github_url,
        idea_lab_report=idea_lab_report,
        on_report_update=push_update,
    )

    try:
        await reviewer.start()
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        reviewer.stop()
