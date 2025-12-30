"""
backend/app/api/auth.py - 인증 및 사용자 관리 API
내부 시스템용 간단한 인증
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import hashlib
import secrets
import pandas as pd

from logic.db import get_connection
from backend.app.api.logs import add_log

router = APIRouter(prefix="/auth", tags=["auth"])

# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    user_id: int
    username: str
    nickname: str
    is_admin: bool


# ─────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────

def hash_password(password: str) -> str:
    """비밀번호 해시"""
    return hashlib.sha256(password.encode()).hexdigest()


def ensure_users_table():
    """users 테이블 생성"""
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 기본 관리자 계정 생성 (없으면)
        existing = con.execute("SELECT 1 FROM users WHERE username = 'admin'").fetchone()
        if not existing:
            con.execute(
                "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?, ?, ?, ?)",
                ('admin', hash_password('admin123'), '관리자', 1)
            )
        
        con.commit()


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.post("/login")
async def login(request: LoginRequest):
    """로그인"""
    ensure_users_table()
    
    with get_connection() as con:
        user = con.execute(
            "SELECT user_id, username, nickname, is_admin, password_hash FROM users WHERE username = ?",
            (request.username,)
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="잘못된 아이디 또는 비밀번호입니다.")
        
        user_id, username, nickname, is_admin, password_hash = user
        
        if password_hash != hash_password(request.password):
            raise HTTPException(status_code=401, detail="잘못된 아이디 또는 비밀번호입니다.")
        
        # 간단한 토큰 생성 (내부 시스템용)
        token = secrets.token_hex(32)
        
        # 토큰 저장 (세션 테이블)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("INSERT OR REPLACE INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
        con.commit()
        
        # 로그 기록
        add_log(
            action_type="로그인",
            target_type="user",
            target_id=str(user_id),
            target_name=nickname,
            user_nickname=nickname,
            details=f"아이디: {username}"
        )
        
        return {
            "success": True,
            "token": token,
            "user": {
                "user_id": user_id,
                "username": username,
                "nickname": nickname,
                "is_admin": bool(is_admin)
            }
        }


@router.post("/logout")
async def logout(token: str):
    """로그아웃"""
    nickname = None
    with get_connection() as con:
        # 로그아웃 전 사용자 정보 가져오기
        result = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        nickname = result[0] if result else None
        
        con.execute("DELETE FROM sessions WHERE token = ?", (token,))
        con.commit()
    
    # 로그 기록
    if nickname:
        add_log(
            action_type="로그아웃",
            target_type="user",
            target_id=None,
            target_name=nickname,
            user_nickname=nickname,
            details=None
        )
    
    return {"success": True}


@router.get("/me")
async def get_current_user(token: str):
    """현재 로그인된 사용자 정보"""
    ensure_users_table()
    
    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        
        if not session:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        
        user_id = session[0]
        user = con.execute(
            "SELECT user_id, username, nickname, is_admin FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
        
        return {
            "user_id": user[0],
            "username": user[1],
            "nickname": user[2],
            "is_admin": bool(user[3])
        }


@router.get("/users", response_model=List[UserResponse])
async def list_users(token: str):
    """사용자 목록 (관리자만)"""
    ensure_users_table()
    
    # 관리자 권한 확인
    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        users = pd.read_sql(
            "SELECT user_id, username, nickname, is_admin FROM users ORDER BY user_id",
            con
        )
    
    return [
        {
            "user_id": int(row['user_id']),
            "username": row['username'],
            "nickname": row['nickname'],
            "is_admin": bool(row['is_admin'])
        }
        for _, row in users.iterrows()
    ]


@router.post("/users")
async def create_user(user: UserCreate, token: str):
    """사용자 생성 (관리자만)"""
    ensure_users_table()
    
    # 관리자 권한 확인
    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        # 중복 확인
        existing = con.execute(
            "SELECT 1 FROM users WHERE username = ?", (user.username,)
        ).fetchone()
        
        if existing:
            raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")
        
        con.execute(
            "INSERT INTO users (username, password_hash, nickname, is_admin) VALUES (?, ?, ?, ?)",
            (user.username, hash_password(user.password), user.nickname, 1 if user.is_admin else 0)
        )
        con.commit()
        
        # 현재 작업자 닉네임 가져오기
        actor = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        actor_nickname = actor[0] if actor else None
    
    # 로그 기록
    add_log(
        action_type="사용자 생성",
        target_type="user",
        target_id=None,
        target_name=user.nickname,
        user_nickname=actor_nickname,
        details=f"아이디: {user.username}, 관리자: {'예' if user.is_admin else '아니오'}"
    )
    
    return {"success": True, "message": f"사용자 '{user.username}' 생성 완료"}


@router.put("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate, token: str):
    """사용자 수정 (관리자만)"""
    ensure_users_table()
    
    with get_connection() as con:
        # 관리자 권한 확인
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        updates = []
        params = []
        
        if data.nickname is not None:
            updates.append("nickname = ?")
            params.append(data.nickname)
        
        if data.password is not None:
            updates.append("password_hash = ?")
            params.append(hash_password(data.password))
        
        if data.is_admin is not None:
            updates.append("is_admin = ?")
            params.append(1 if data.is_admin else 0)
        
        if updates:
            params.append(user_id)
            con.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
            con.commit()
        
        # 대상 사용자 정보 가져오기
        target_user = con.execute(
            "SELECT nickname FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        target_nickname = target_user[0] if target_user else None
        
        # 현재 작업자 닉네임 가져오기
        actor = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        actor_nickname = actor[0] if actor else None
    
    # 로그 기록
    add_log(
        action_type="사용자 수정",
        target_type="user",
        target_id=str(user_id),
        target_name=target_nickname,
        user_nickname=actor_nickname,
        details=f"수정 항목: {', '.join(updates) if updates else '없음'}"
    )
    
    return {"success": True, "message": "사용자 정보 수정 완료"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, token: str):
    """사용자 삭제 (관리자만)"""
    ensure_users_table()
    
    with get_connection() as con:
        # 관리자 권한 확인
        session = con.execute(
            "SELECT u.user_id, u.is_admin FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session or not session[1]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        # 자기 자신은 삭제 불가
        if session[0] == user_id:
            raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다.")
        
        # 삭제 대상 사용자 정보 가져오기
        target_user = con.execute(
            "SELECT username, nickname FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        target_username = target_user[0] if target_user else None
        target_nickname = target_user[1] if target_user else None
        
        # 현재 작업자 닉네임 가져오기
        actor = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        actor_nickname = actor[0] if actor else None
        
        con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        con.commit()
    
    # 로그 기록
    add_log(
        action_type="사용자 삭제",
        target_type="user",
        target_id=str(user_id),
        target_name=target_nickname,
        user_nickname=actor_nickname,
        details=f"아이디: {target_username}"
    )
    
    return {"success": True, "message": "사용자 삭제 완료"}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(request: ChangePasswordRequest, token: str):
    """본인 비밀번호 변경"""
    ensure_users_table()
    
    if not request.new_password.strip():
        raise HTTPException(status_code=400, detail="새 비밀번호를 입력하세요.")
    
    with get_connection() as con:
        # 현재 사용자 확인
        session = con.execute(
            "SELECT u.user_id, u.password_hash FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        
        user_id, current_hash = session
        
        # 현재 비밀번호 확인
        if current_hash != hash_password(request.current_password):
            raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
        
        # 새 비밀번호로 업데이트
        con.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (hash_password(request.new_password), user_id)
        )
        con.commit()
    
    return {"success": True, "message": "비밀번호가 변경되었습니다."}

