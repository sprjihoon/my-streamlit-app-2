"""
backend/app/api/logs.py - 활동 로그 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
from datetime import datetime

from logic.db import get_connection

router = APIRouter(prefix="/logs", tags=["logs"])


# ─────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────

def ensure_logs_table():
    """activity_logs 테이블 생성"""
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                target_name TEXT,
                user_nickname TEXT,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()


def add_log(
    action_type: str,
    target_type: str = None,
    target_id: str = None,
    target_name: str = None,
    user_nickname: str = None,
    details: str = None
):
    """로그 추가"""
    ensure_logs_table()
    with get_connection() as con:
        con.execute(
            """INSERT INTO activity_logs 
               (action_type, target_type, target_id, target_name, user_nickname, details) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (action_type, target_type, target_id, target_name, user_nickname, details)
        )
        con.commit()


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.get("")
@router.get("/")
async def get_logs(
    token: str,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    action_type: Optional[str] = None,
    target_type: Optional[str] = None,
    user_nickname: Optional[str] = None,
    target_name: Optional[str] = None,
    limit: int = 500
):
    """로그 목록 조회 (관리자만)"""
    ensure_logs_table()
    
    # 관리자 권한 확인
    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        # 쿼리 구성
        query = "SELECT * FROM activity_logs WHERE 1=1"
        params = []
        
        if period_from:
            query += " AND date(created_at) >= date(?)"
            params.append(period_from)
        
        if period_to:
            query += " AND date(created_at) <= date(?)"
            params.append(period_to)
        
        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)
        
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type)
        
        if user_nickname:
            query += " AND user_nickname LIKE ?"
            params.append(f"%{user_nickname}%")
        
        if target_name:
            query += " AND target_name LIKE ?"
            params.append(f"%{target_name}%")
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        df = pd.read_sql(query, con, params=params)
        
        # 필터 옵션들
        action_types = pd.read_sql(
            "SELECT DISTINCT action_type FROM activity_logs ORDER BY action_type", con
        )['action_type'].tolist()
        
        target_types = pd.read_sql(
            "SELECT DISTINCT target_type FROM activity_logs WHERE target_type IS NOT NULL ORDER BY target_type", con
        )['target_type'].tolist()
        
        users = pd.read_sql(
            "SELECT DISTINCT user_nickname FROM activity_logs WHERE user_nickname IS NOT NULL ORDER BY user_nickname", con
        )['user_nickname'].tolist()
    
    logs = []
    for _, row in df.iterrows():
        logs.append({
            "log_id": int(row['log_id']),
            "action_type": row['action_type'],
            "target_type": row['target_type'] if pd.notna(row['target_type']) else None,
            "target_id": row['target_id'] if pd.notna(row['target_id']) else None,
            "target_name": row['target_name'] if pd.notna(row['target_name']) else None,
            "user_nickname": row['user_nickname'] if pd.notna(row['user_nickname']) else None,
            "details": row['details'] if pd.notna(row['details']) else None,
            "created_at": str(row['created_at']) if row['created_at'] else None,
        })
    
    return {
        "logs": logs,
        "total": len(logs),
        "filters": {
            "action_types": action_types,
            "target_types": target_types,
            "users": users,
        }
    }


@router.get("/stats")
async def get_log_stats(token: str):
    """로그 통계 (관리자만)"""
    ensure_logs_table()
    
    # 관리자 권한 확인
    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        # 전체 로그 수
        total = con.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
        
        # 오늘 로그 수
        today = con.execute(
            "SELECT COUNT(*) FROM activity_logs WHERE date(created_at) = date('now')"
        ).fetchone()[0]
        
        # 액션별 통계
        by_action = pd.read_sql(
            "SELECT action_type, COUNT(*) as count FROM activity_logs GROUP BY action_type ORDER BY count DESC",
            con
        ).to_dict(orient='records')
        
        # 사용자별 통계
        by_user = pd.read_sql(
            "SELECT user_nickname, COUNT(*) as count FROM activity_logs WHERE user_nickname IS NOT NULL GROUP BY user_nickname ORDER BY count DESC LIMIT 10",
            con
        ).to_dict(orient='records')
    
    return {
        "total": total,
        "today": today,
        "by_action": by_action,
        "by_user": by_user,
    }

