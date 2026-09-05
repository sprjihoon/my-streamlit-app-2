"""
대화 상태 관리 모듈
───────────────────────────────────────
불완전한 작업 정보를 임시 저장하고 후속 메시지와 연결합니다.
"""

import os
import re
import time
from typing import Optional, Dict, Any
from datetime import datetime
import json
import sqlite3
from pathlib import Path

_HISTORY_NAME_PREFIX = re.compile(r"^\[[^\]\n]{1,40}\]\s+")


def strip_history_name_prefix(content: str) -> str:
    """읽는 시점에만 [이름] 접두어를 제거한다. DB는 마이그레이션하지 않는다."""
    return _HISTORY_NAME_PREFIX.sub("", content or "", count=1)


def _default_conversation_db_path() -> str:
    """logic.db 와 같은 우선순위: BILLING_DB → DATABASE_PATH → settings/앱 기본값."""
    env_db = os.getenv("BILLING_DB") or os.getenv("DATABASE_PATH")
    if env_db:
        path = Path(env_db)
    else:
        try:
            from backend.app.config import settings
            path = Path(settings.DATABASE_PATH)
        except Exception:
            if os.path.exists("/app"):
                path = Path("/app/data/billing.db")
            else:
                path = Path("billing.db")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return str(path)


class ConversationStateManager:
    """대화 상태 관리자 (SQLite 기반)"""
    
    # 대화 상태 만료 시간 (5분). 수선·일지 draft는 60분으로 분리한다.
    EXPIRE_SECONDS = 300
    REPAIR_DRAFT_EXPIRE_SECONDS = 3600
    JOURNAL_DRAFT_EXPIRE_SECONDS = 3600
    # 대화 이력 최대 개수
    MAX_HISTORY = 10
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = _default_conversation_db_path()

        self.db_path = db_path
        self._ensure_table()
    
    def _ensure_table(self):
        """대화 상태 및 이력 테이블 생성. 기존 PK는 유지하고 v2를 추가한다."""
        with sqlite3.connect(self.db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS conversation_states (
                    user_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    pending_data TEXT,
                    missing TEXT,
                    last_question TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS conversation_states_v2 (
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    pending_data TEXT,
                    missing TEXT,
                    last_question TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    PRIMARY KEY (user_id, channel_id)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS bot_query_context (
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TIMESTAMP,
                    PRIMARY KEY (user_id, channel_id)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS bot_webhook_events (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    reply TEXT,
                    created_at TIMESTAMP
                )
            """)
            con.commit()

    def _scope(self, user_id: str, channel_id: Optional[str] = None) -> tuple[str, str]:
        uid = (user_id or "").strip()
        cid = (channel_id or "").strip() or uid
        return uid, cid
    
    @staticmethod
    def _expires_ts(value) -> float:
        """ISO와 unix를 같은 초 단위로 비교한다."""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return 0.0

    def get_state(self, user_id: str, channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """방 단위(v2) pending 조회. channel_id가 없으면 user_id로 본다."""
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                """
                SELECT user_id, channel_id, pending_data, missing, last_question, created_at, expires_at
                FROM conversation_states_v2
                WHERE user_id = ? AND channel_id = ?
                """,
                (uid, cid),
            ).fetchone()
            if row is None:
                return None
            pending = json.loads(row["pending_data"]) if row["pending_data"] else {}
            expired = self._expires_ts(row["expires_at"]) <= time.time()
            if expired:
                if pending.get("entry_type") in ("repair", "journal"):
                    return {
                        "user_id": row["user_id"],
                        "channel_id": row["channel_id"],
                        "pending_data": pending,
                        "missing": json.loads(row["missing"]) if row["missing"] else [],
                        "last_question": row["last_question"],
                        "created_at": row["created_at"],
                        "expires_at": row["expires_at"],
                        "expired": True,
                    }
                con.execute(
                    "DELETE FROM conversation_states_v2 WHERE user_id = ? AND channel_id = ?",
                    (uid, cid),
                )
                con.commit()
                return None
            return {
                "user_id": row["user_id"],
                "channel_id": row["channel_id"],
                "pending_data": pending,
                "missing": json.loads(row["missing"]) if row["missing"] else [],
                "last_question": row["last_question"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
    
    def set_state(
        self,
        user_id: str,
        channel_id: str,
        pending_data: Dict[str, Any],
        missing: list,
        last_question: str,
        expire_seconds: Optional[int] = None,
    ) -> None:
        """
        대화 상태 저장
        
        Args:
            user_id: 사용자 ID
            channel_id: 채널 ID
            pending_data: 미완성 작업 데이터
            missing: 누락된 필드 목록
            last_question: 마지막 질문
            expire_seconds: 생략 시 수선·일지 draft는 60분, 그 외는 5분
        """
        if expire_seconds is None:
            entry_type = (pending_data or {}).get("entry_type")
            if entry_type == "repair":
                expire_seconds = self.REPAIR_DRAFT_EXPIRE_SECONDS
            elif entry_type == "journal":
                expire_seconds = self.JOURNAL_DRAFT_EXPIRE_SECONDS
            else:
                expire_seconds = self.EXPIRE_SECONDS
        expires_at = int(time.time()) + int(expire_seconds)
        uid, cid = self._scope(user_id, channel_id)
        
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT OR REPLACE INTO conversation_states_v2
                (user_id, channel_id, pending_data, missing, last_question, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    cid,
                    json.dumps(pending_data, ensure_ascii=False),
                    json.dumps(missing, ensure_ascii=False),
                    last_question,
                    expires_at,
                )
            )
            con.commit()
    
    def clear_state(self, user_id: str, channel_id: Optional[str] = None) -> None:
        """해당 방의 pending만 삭제. 업무 테이블은 건드리지 않는다."""
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "DELETE FROM conversation_states_v2 WHERE user_id = ? AND channel_id = ?",
                (uid, cid),
            )
            con.commit()
    
    def cleanup_expired(self) -> int:
        """
        만료된 대화 상태 정리
        
        Returns:
            삭제된 레코드 수
        """
        now = time.time()
        deleted = 0
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT user_id, channel_id, expires_at FROM conversation_states_v2"
            ).fetchall()
            for uid, cid, exp in rows:
                if self._expires_ts(exp) <= now:
                    con.execute(
                        "DELETE FROM conversation_states_v2 WHERE user_id = ? AND channel_id = ?",
                        (uid, cid),
                    )
                    deleted += 1
            con.commit()
        return deleted
    
    # ─────────────────────────────────────
    # 대화 이력 관리
    # ─────────────────────────────────────
    
    def add_message(self, user_id: str, channel_id: str, role: str, content: str) -> None:
        """
        대화 메시지 추가
        
        Args:
            user_id: 사용자 ID
            channel_id: 채널 ID
            role: 역할 (user/assistant)
            content: 메시지 내용
        """
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """INSERT INTO conversation_history_v2 (user_id, channel_id, role, content)
                   VALUES (?, ?, ?, ?)""",
                (uid, cid, role, content)
            )
            con.execute(
                """DELETE FROM conversation_history_v2
                   WHERE user_id = ? AND channel_id = ? AND id NOT IN (
                       SELECT id FROM conversation_history_v2
                       WHERE user_id = ? AND channel_id = ?
                       ORDER BY created_at DESC LIMIT ?
                   )""",
                (uid, cid, uid, cid, self.MAX_HISTORY * 2)
            )
            con.commit()
    
    def get_history(self, user_id: str, limit: int = None, channel_id: Optional[str] = None) -> list:
        if limit is None:
            limit = self.MAX_HISTORY
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """SELECT role, content FROM conversation_history_v2
                   WHERE user_id = ? AND channel_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (uid, cid, limit)
            ).fetchall()
            out = []
            for row in reversed(rows):
                content = row["content"]
                if row["role"] == "user":
                    content = strip_history_name_prefix(content)
                out.append({"role": row["role"], "content": content})
            return out

    def get_query_context(self, user_id: str, channel_id: Optional[str] = None) -> Dict[str, Any]:
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT payload FROM bot_query_context WHERE user_id = ? AND channel_id = ?",
                (uid, cid),
            ).fetchone()
        if not row or not row[0]:
            return {}
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def set_query_context(self, user_id: str, channel_id: Optional[str], payload: Dict[str, Any]) -> None:
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT INTO bot_query_context (user_id, channel_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, channel_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (uid, cid, json.dumps(payload or {}, ensure_ascii=False), datetime.now().isoformat()),
            )
            con.commit()

    def clear_query_context(self, user_id: str, channel_id: Optional[str] = None) -> None:
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "DELETE FROM bot_query_context WHERE user_id = ? AND channel_id = ?",
                (uid, cid),
            )
            con.commit()

    def get_webhook_event(self, event_id: Optional[str]) -> Optional[str]:
        if not event_id:
            return None
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT reply FROM bot_webhook_events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
        return row[0] if row else None

    def remember_webhook_event(
        self,
        event_id: Optional[str],
        user_id: str,
        channel_id: Optional[str],
        reply: str,
    ) -> None:
        if not event_id:
            return
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT OR IGNORE INTO bot_webhook_events
                (event_id, user_id, channel_id, reply, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(event_id), uid, cid, (reply or "")[:500], datetime.now().isoformat()),
            )
            con.commit()
    
    def clear_history(self, user_id: str, channel_id: Optional[str] = None) -> None:
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "DELETE FROM conversation_history_v2 WHERE user_id = ? AND channel_id = ?",
                (uid, cid),
            )
            con.commit()


# 싱글톤 인스턴스
_manager: Optional[ConversationStateManager] = None


def get_conversation_manager() -> ConversationStateManager:
    """대화 상태 관리자 싱글톤 반환"""
    global _manager
    if _manager is None:
        _manager = ConversationStateManager()
    return _manager


def reset_conversation_manager(db_path: Optional[str] = None) -> Optional[ConversationStateManager]:
    """테스트용. 싱글톤을 비우거나 지정 DB로 다시 만든다."""
    global _manager
    _manager = ConversationStateManager(db_path=db_path) if db_path else None
    return _manager
