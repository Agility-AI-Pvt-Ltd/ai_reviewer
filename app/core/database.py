from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite+aiosqlite:///:memory:"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    if database_url.startswith("sqlite+aiosqlite:///"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def _make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, **_engine_kwargs(database_url))


engine = _make_engine(settings.database_url)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def configure_database(database_url: str) -> None:
    global engine, AsyncSessionLocal

    engine = _make_engine(database_url)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_idea_lab_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db(create_idea_lab_tables: bool = False) -> None:
    from app.models.idea_lab import FeasibilityReport
    from app.models.review_job import ReviewJobEvent
    from app.models.review_state import ReviewStateSnapshot

    if create_idea_lab_tables:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[
                    FeasibilityReport.__table__,
                    ReviewJobEvent.__table__,
                    ReviewStateSnapshot.__table__,
                ],
            )
