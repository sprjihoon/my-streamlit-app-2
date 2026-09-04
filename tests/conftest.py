"""모든 테스트를 임시 DB·임시 업로드 폴더로 격리한다."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from tests.isolation import (
    REAL_BILLING_DB,
    REAL_UPLOAD_DIR,
    seed_isolated_schema,
    sha256_file,
    upload_manifest,
)

# import 전에 실제 산출물 스냅샷 (repair_log.UPLOAD_DIR.mkdir 보다 앞)
_BEFORE_DB_SHA = sha256_file(REAL_BILLING_DB)
_BEFORE_UPLOADS = upload_manifest(REAL_UPLOAD_DIR)

_SESSION_TMP = Path(tempfile.mkdtemp(prefix="bot-modes-import-"))
_SESSION_UPLOADS = _SESSION_TMP / "uploads"
_SESSION_UPLOADS.mkdir(parents=True)
os.environ["BILLING_DB"] = str(_SESSION_TMP / "placeholder.db")
os.environ["DATABASE_PATH"] = str(_SESSION_TMP / "placeholder.db")

from backend.app.config import settings  # noqa: E402

settings.DATABASE_PATH = str(_SESSION_TMP / "placeholder.db")
settings.UPLOAD_DIR = str(_SESSION_UPLOADS)


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    db_path = tmp_path / "billing.db"
    upload_root = tmp_path / "uploads"
    repair_dir = upload_root / "repair"
    repair_dir.mkdir(parents=True)
    seed_isolated_schema(db_path)

    monkeypatch.setenv("BILLING_DB", str(db_path))
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    import logic.db as logic_db

    logic_db._db_path_cache = None
    monkeypatch.setattr(logic_db, "DB_PATH", db_path)

    monkeypatch.setattr(settings, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))

    import backend.app.api.repair_log as repair_log

    monkeypatch.setattr(repair_log, "UPLOAD_DIR", repair_dir)

    from backend.app.services.conversation_state import reset_conversation_manager

    reset_conversation_manager(str(db_path))

    import backend.app.services.repair_bot as repair_bot

    for task in list(repair_bot._flush_tasks.values()):
        if task and not task.done():
            task.cancel()
    repair_bot._flush_tasks.clear()

    yield {
        "db": db_path,
        "uploads": upload_root,
        "repair": repair_dir,
    }

    for task in list(repair_bot._flush_tasks.values()):
        if task and not task.done():
            task.cancel()
    repair_bot._flush_tasks.clear()
    reset_conversation_manager(None)
    logic_db._db_path_cache = None


@pytest.fixture(scope="session", autouse=True)
def _assert_real_artifacts_untouched():
    yield
    after_sha = sha256_file(REAL_BILLING_DB)
    after_uploads = upload_manifest(REAL_UPLOAD_DIR)
    assert after_sha == _BEFORE_DB_SHA, "실제 billing.db 가 테스트에 의해 변경됨"
    assert after_uploads == _BEFORE_UPLOADS, "실제 data/uploads/repair 가 테스트에 의해 변경됨"
