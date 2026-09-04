"""
대화 상태 관리 모듈
───────────────────────────────────────
불완전한 작업 정보를 임시 저장하고 후속 메시지와 연결합니다.
"""

import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json
import sqlite3
from pathlib import Path


class ConversationStateManager:
    """대화 상태 관리자 (SQLite 기반)"""
    
    # 대화 상태 만료 시간 (5분)
    EXPIRE_SECONDS = 300
    # 대화 이력 최대 개수
    MAX_HISTORY = 10
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # 프로젝트 루트의 billing.db 사용
            current_dir = Path(__file__).parent.parent.parent.parent
            db_path = str(current_dir / "billing.db")
        
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
            con.commit()

    def _scope(self, user_id: str, channel_id: Optional[str] = None) -> tuple[str, str]:
        uid = (user_id or "").strip()
        cid = (channel_id or "").strip() or uid
        return uid, cid
    
    def get_state(self, user_id: str, channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """방 단위(v2) pending 조회. channel_id가 없으면 user_id로 본다."""
        uid, cid = self._scope(user_id, channel_id)
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                """
                SELECT * FROM conversation_states_v2
                WHERE user_id = ? AND channel_id = ? AND expires_at > datetime('now')
                """,
                (uid, cid),
            ).fetchone()
            if row is None:
                return None
            return {
                "user_id": row["user_id"],
                "channel_id": row["channel_id"],
                "pending_data": json.loads(row["pending_data"]) if row["pending_data"] else {},
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
        last_question: str
    ) -> None:
        """
        대화 상태 저장
        
        Args:
            user_id: 사용자 ID
            channel_id: 채널 ID
            pending_data: 미완성 작업 데이터
            missing: 누락된 필드 목록
            last_question: 마지막 질문
        """
        expires_at = datetime.now() + timedelta(seconds=self.EXPIRE_SECONDS)
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
                    expires_at.isoformat()
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
        with sqlite3.connect(self.db_path) as con:
            cursor = con.execute(
                "DELETE FROM conversation_states_v2 WHERE expires_at < datetime('now')"
            )
            con.commit()
            return cursor.rowcount
    
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
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    
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
