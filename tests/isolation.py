"""테스트 전용: 실제 billing.db / data/uploads 를 건드리지 않기 위한 헬퍼."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_BILLING_DB = REPO_ROOT / "billing.db"
REAL_UPLOAD_DIR = REPO_ROOT / "data" / "uploads" / "repair"


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_manifest(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    return sorted(
        str(p.relative_to(folder)).replace("\\", "/")
        for p in folder.rglob("*")
        if p.is_file()
    )


def seed_isolated_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                날짜 TEXT,
                업체명 TEXT,
                분류 TEXT,
                단가 INTEGER,
                수량 INTEGER,
                합계 INTEGER,
                비고1 TEXT,
                작성자 TEXT,
                저장시간 TEXT,
                출처 TEXT,
                works_user_id TEXT
            );
            CREATE TABLE IF NOT EXISTS work_log_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER,
                action TEXT,
                날짜 TEXT,
                업체명 TEXT,
                분류 TEXT,
                단가 INTEGER,
                수량 INTEGER,
                합계 INTEGER,
                작성자 TEXT,
                변경자 TEXT,
                변경시간 TEXT,
                변경사유 TEXT,
                works_user_id TEXT
            );
            CREATE TABLE IF NOT EXISTS vendors (
                vendor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor TEXT UNIQUE,
                name TEXT,
                rate_type TEXT,
                active TEXT
            );
            CREATE TABLE IF NOT EXISTS aliases (
                alias TEXT,
                file_type TEXT,
                vendor TEXT
            );
            CREATE TABLE IF NOT EXISTS bot_modes (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'idle',
                updated_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            );
            CREATE TABLE IF NOT EXISTS conversation_states_v2 (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                pending_data TEXT,
                missing TEXT,
                last_question TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            );
            CREATE TABLE IF NOT EXISTS conversation_history_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS repair_photo_inbox (
                user_id TEXT PRIMARY KEY,
                channel_id TEXT,
                channel_type TEXT,
                user_name TEXT,
                extra_rounds INTEGER DEFAULT 0,
                notified_n INTEGER DEFAULT 0,
                flush_after REAL,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS repair_photo_inbox_file (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                name TEXT,
                ext TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS repair_photo_inbox_v2 (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_type TEXT,
                user_name TEXT,
                extra_rounds INTEGER DEFAULT 0,
                notified_n INTEGER DEFAULT 0,
                flush_after REAL,
                updated_at TEXT,
                PRIMARY KEY (user_id, channel_id)
            );
            CREATE TABLE IF NOT EXISTS repair_photo_inbox_file_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                name TEXT,
                ext TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS repair_work_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                날짜 TEXT,
                업체명 TEXT,
                제품명 TEXT,
                옵션 TEXT,
                바코드 TEXT,
                작업 TEXT,
                수량 INTEGER DEFAULT 1,
                비용 INTEGER DEFAULT 0,
                비고 TEXT,
                작성자 TEXT,
                저장시간 TIMESTAMP,
                출처 TEXT,
                barcode_image TEXT,
                before_image TEXT,
                after_image TEXT
            );
            CREATE TABLE IF NOT EXISTS shipping_zone (
                [요금제] TEXT,
                [구간] TEXT,
                len_min_cm INTEGER,
                len_max_cm INTEGER,
                [요금] INTEGER,
                PRIMARY KEY([요금제], [구간])
            );
            CREATE TABLE IF NOT EXISTS kpost_in (
                발송인명 TEXT,
                접수일자 TEXT,
                부피 INTEGER,
                송장번호 TEXT
            );
            CREATE TABLE IF NOT EXISTS activity_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                target_name TEXT,
                user_nickname TEXT,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT OR IGNORE INTO vendors (vendor, name, rate_type, active)
            VALUES ('틸리언', '틸리언', '표준', NULL);
            INSERT OR IGNORE INTO vendors (vendor, name, rate_type, active)
            VALUES ('팔로우미코스메틱', '팔로우미코스메틱', '표준', NULL);
            INSERT INTO aliases (alias, file_type, vendor) VALUES ('틸', 'work_log', '틸리언');
            INSERT INTO aliases (alias, file_type, vendor) VALUES ('팔로우미', 'work_log', '팔로우미코스메틱');
            """
        )
        con.commit()


def seed_shipping_fixture(db_path: Path) -> None:
    """인보이스 택배 구간 회귀용 고정 입력. 계산 본체는 호출만 한다."""
    seed_isolated_schema(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute("DELETE FROM shipping_zone")
        con.execute("DELETE FROM kpost_in")
        con.executemany(
            "INSERT INTO shipping_zone (요금제, 구간, len_min_cm, len_max_cm, 요금) VALUES (?,?,?,?,?)",
            [
                ("표준", "극소", 0, 40, 2500),
                ("표준", "중", 71, 100, 4000),
            ],
        )
        rows = []
        for i in range(3):
            rows.append(("팔로우미코스메틱", "2025-06-10", 20, f"TRK-XS-{i}"))
        rows.append(("팔로우미코스메틱", "2025-06-11", 80, "TRK-M-1"))
        con.executemany(
            "INSERT INTO kpost_in (발송인명, 접수일자, 부피, 송장번호) VALUES (?,?,?,?)",
            rows,
        )
        con.commit()
