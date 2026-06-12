from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth_router, review_router, websocket_router
from app.core.config import settings
from app.core.rate_limiter import close_redis
from app.services.review_worker import review_queue_worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.review_worker_enabled:
        review_queue_worker.start()
    yield
    if settings.review_worker_enabled:
        await review_queue_worker.stop()
    await close_redis()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(review_router)
app.include_router(websocket_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
