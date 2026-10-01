import os
import sys
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DATA = Path(__file__).parent / ".tmp-data"
os.environ["APP_DATA_DIR"] = str(TEST_DATA)
os.environ["APP_TIMEZONE"] = "UTC"
os.environ["GASTOS_COMIDA_URL"] = ""

import app as app_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    TEST_DATA.mkdir(parents=True, exist_ok=True)
    db_path = TEST_DATA / "chores.db"
    if db_path.exists():
        db_path.unlink()
    attachments = TEST_DATA / "attachments"
    if attachments.exists():
        shutil.rmtree(attachments)
    attachments.mkdir(parents=True, exist_ok=True)

    app_module.init_db()

    with TestClient(app_module.app) as test_client:
        yield test_client

    if db_path.exists():
        db_path.unlink()
