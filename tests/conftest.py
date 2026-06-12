import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.core.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    database.configure_database(db_url)
    settings.review_worker_enabled = False
    asyncio.run(database.init_db(create_idea_lab_tables=True))

    with TestClient(app) as test_client:
        yield test_client
