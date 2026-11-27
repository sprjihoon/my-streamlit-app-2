"""
backend/app/api/auth.py - 인증 및 사용자 관리 API
내부 시스템용 간단한 인증
"""
import os
from datetime import date, datetime
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
    nickname: str
    department: Optional[str] = None
    position: Optional[str] = None
    join_date: Optional[str] = None
    naver_works_id: Optional[str] = None
    approver_id: Optional[int] = None
    is_admin: bool = False
    leave_exempt: bool = False
    can_jeongyeol: bool = False
    can_manage_part_time: bool = False


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    department: Optional[str] = None
    position: Optional[str] = None
    join_date: Optional[str] = None
    naver_works_id: Optional[str] = None
    approver_id: Optional[int] = None
    leave_exempt: Optional[bool] = None
    can_jeongyeol: Optional[bool] = None
    can_manage_part_time: Optional[bool] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    user_id: int
    username: str
    nickname: str
    is_admin: bool
    department: Optional[str] = None
    position: Optional[str] = None
    join_date: Optional[str] = None
    naver_works_id: Optional[str] = None
    approver_id: Optional[int] = None
    leave_exempt: bool = False
    can_jeongyeol: bool = False
    can_manage_part_time: bool = False
    resigned_on: Optional[str] = None


class ResignRequest(BaseModel):
    resigned_on: str


# ─────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────

def hash_password(password: str) -> str:
    """비밀번호 해시"""
    return hashlib.sha256(password.encode()).hexdigest()


def _parse_iso_date(value: str, label: str) -> str:
    text = (value or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label}은 YYYY-MM-DD 형식이어야 합니다.")


def resignation_in_effect(resigned_on: str | None, today: date | None = None) -> bool:
    """퇴사일이 오늘 이전이면 로그인을 막는다. 미래 퇴사일은 그날까지 재직이다."""
    text = (resigned_on or "").strip()
    if not text:
        return False
    try:
        day = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return False
    return day <= (today or date.today())


def _ensure_sessions(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _user_row(con, user_id: int):
    return con.execute(
        "SELECT username, nickname, department, join_date, resigned_on FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()


def ensure_users_table():
    """users 테이블 생성 및 컬럼 마이그레이션"""
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

        # 신규 컬럼 마이그레이션 (없으면 추가)
        new_cols = [
            ("department",           "TEXT"),
            ("position",             "TEXT"),
            ("position_order",       "INTEGER DEFAULT 1"),
            ("naver_works_id",       "TEXT"),
            ("approver_id",          "INTEGER"),
            ("join_date",            "TEXT"),
            ("must_change_password", "INTEGER DEFAULT 0"),
            ("leave_exempt",         "INTEGER DEFAULT 0"),
            ("can_jeongyeol",        "INTEGER DEFAULT 0"),  # 전결권: 1이면 단독 승인으로 즉시 확정
            ("can_manage_part_time", "INTEGER DEFAULT 0"),  # 아르바이트 관리: 1이면 관리대장·통계·명세서 사용
            ("resigned_on",          "TEXT"),  # 퇴사일. 비어 있으면 재직
        ]
        existing_cols = [row[1] for row in con.execute("PRAGMA table_info(users)")]
        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                try:
                    con.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

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
            """SELECT user_id, username, nickname, is_admin, password_hash, department,
                      can_manage_part_time, resigned_on
               FROM users WHERE username = ?""",
            (request.username,)
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="잘못된 아이디 또는 비밀번호입니다.")
        
        user_id, username, nickname, is_admin, password_hash, department, can_manage_part_time, resigned_on = user
        
        if password_hash != hash_password(request.password):
            raise HTTPException(status_code=401, detail="잘못된 아이디 또는 비밀번호입니다.")
        if resignation_in_effect(resigned_on):
            raise HTTPException(status_code=401, detail="퇴사 처리된 계정입니다.")
        
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
        
        # must_change_password 조회
        must_change = con.execute(
            "SELECT must_change_password FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        must_change_password = bool(must_change[0]) if must_change and must_change[0] else False

        from backend.app.api.employment_contracts import worker_needs_contract

        return {
            "success": True,
            "token": token,
            "must_change_password": must_change_password,
            "user": {
                "user_id": user_id,
                "username": username,
                "nickname": nickname,
                "is_admin": bool(is_admin),
                "department": department,
                "can_manage_part_time": bool(can_manage_part_time),
                "needs_contract": worker_needs_contract(user_id, bool(is_admin)),
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
            """SELECT user_id, username, nickname, is_admin,
                      department, position, join_date, naver_works_id, approver_id, leave_exempt, can_jeongyeol,
                      can_manage_part_time, resigned_on
               FROM users WHERE user_id = ?""",
            (user_id,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
        if resignation_in_effect(user[12]):
            con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            con.commit()
            raise HTTPException(status_code=401, detail="퇴사 처리된 계정입니다.")

        from backend.app.api.employment_contracts import worker_needs_contract

        return {
            "user_id": user[0],
            "username": user[1],
            "nickname": user[2],
            "is_admin": bool(user[3]),
            "department": user[4],
            "position": user[5],
            "join_date": user[6],
            "naver_works_id": user[7],
            "approver_id": user[8],
            "leave_exempt": bool(user[9]) if user[9] else False,
            "can_jeongyeol": bool(user[10]) if user[10] else False,
            "can_manage_part_time": bool(user[11]) if user[11] else False,
            "resigned_on": user[12] or None,
            "needs_contract": worker_needs_contract(user[0], bool(user[3])),
        }


def _can_manage_users(token: str, con) -> tuple:
    """사용자 관리 권한 확인. (actor_id, is_admin, position, department) 반환"""
    row = con.execute(
        """SELECT u.user_id, u.is_admin, u.position, u.department
           FROM sessions s JOIN users u ON s.user_id = u.user_id
           WHERE s.token = ?""",
        (token,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    actor_id, is_admin, position, department = row
    allowed_positions = ("팀장", "인사과장", "대표")
    if not is_admin and position not in allowed_positions:
        raise HTTPException(status_code=403, detail="사용자 관리 권한이 없습니다. (관리자/팀장/인사과장만 가능)")
    return actor_id, bool(is_admin), position, department


@router.get("/users/me/can-manage")
async def check_can_manage(token: str):
    """현재 사용자의 사용자 관리 권한 여부"""
    ensure_users_table()
    with get_connection() as con:
        try:
            actor_id, is_admin, position, department = _can_manage_users(token, con)
            return {"can_manage": True, "is_admin": is_admin, "position": position, "department": department}
        except HTTPException:
            return {"can_manage": False}


@router.get("/users", response_model=List[UserResponse])
async def list_users(token: str):
    """사용자 목록 (관리자/팀장/인사과장)"""
    ensure_users_table()

    with get_connection() as con:
        _can_manage_users(token, con)

        rows = con.execute(
            """SELECT user_id, username, nickname, is_admin,
                      department, position, join_date, naver_works_id, approver_id, leave_exempt, can_jeongyeol,
                      can_manage_part_time, resigned_on
               FROM users ORDER BY department, position_order DESC, nickname"""
        ).fetchall()

    return [
        {
            "user_id": r[0],
            "username": r[1],
            "nickname": r[2],
            "is_admin": bool(r[3]),
            "department": r[4],
            "position": r[5],
            "join_date": r[6],
            "naver_works_id": r[7],
            "approver_id": r[8],
            "leave_exempt": bool(r[9]) if r[9] else False,
            "can_jeongyeol": bool(r[10]) if r[10] else False,
            "can_manage_part_time": bool(r[11]) if r[11] else False,
            "resigned_on": r[12] or None,
        }
        for r in rows
    ]


@router.post("/users")
async def create_user(user: UserCreate, token: str):
    """사용자 생성 (관리자/팀장/인사과장)"""
    ensure_users_table()

    with get_connection() as con:
        actor_id, is_admin, actor_position, actor_dept = _can_manage_users(token, con)

        # 팀장은 본인 팀에만 추가 가능
        if not is_admin and actor_position == "팀장":
            if user.department and user.department != actor_dept:
                raise HTTPException(status_code=403, detail=f"팀장은 본인 팀({actor_dept}) 직원만 추가할 수 있습니다.")
            # 팀 강제 지정
            if not user.department:
                user.department = actor_dept

        # 팀장/인사과장은 관리자 권한 부여 불가
        if not is_admin and user.is_admin:
            raise HTTPException(status_code=403, detail="관리자 권한 부여는 관리자만 가능합니다.")
        if not is_admin and user.can_manage_part_time:
            raise HTTPException(status_code=403, detail="아르바이트 관리 권한 부여는 관리자만 가능합니다.")

        # 중복 확인
        existing = con.execute("SELECT 1 FROM users WHERE username = ?", (user.username,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

        # position_order 매핑
        pos_order = {"대표": 99, "인사과장": 3, "팀장": 2}.get(user.position or "", 1)

        con.execute(
            """INSERT INTO users
               (username, password_hash, nickname, is_admin,
                department, position, position_order,
                join_date, naver_works_id, approver_id, leave_exempt,
                can_manage_part_time, must_change_password)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                user.username,
                hash_password("123456"),  # 초기 비밀번호
                user.nickname,
                1 if user.is_admin else 0,
                user.department,
                user.position,
                pos_order,
                user.join_date,
                user.naver_works_id or user.username,
                user.approver_id,
                1 if user.leave_exempt else 0,
                1 if user.can_manage_part_time else 0,
            )
        )
        con.commit()

        actor = con.execute(
            "SELECT nickname FROM users WHERE user_id = ?", (actor_id,)
        ).fetchone()
        actor_nickname = actor[0] if actor else None

    add_log(
        action_type="사용자 생성",
        target_type="user",
        target_id=None,
        target_name=user.nickname,
        user_nickname=actor_nickname,
        details=f"아이디: {user.username}, 팀: {user.department}, 직급: {user.position}, 입사일: {user.join_date}"
    )

    return {"success": True, "message": f"'{user.nickname}' 계정 생성 완료 (초기 비밀번호: 123456)"}


@router.put("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate, token: str):
    """사용자 수정 (관리자/팀장/인사과장)"""
    ensure_users_table()

    with get_connection() as con:
        actor_id, is_admin, actor_position, actor_dept = _can_manage_users(token, con)

        # 팀장은 본인 팀 직원만 수정 가능
        if not is_admin and actor_position == "팀장":
            target_dept = con.execute("SELECT department FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if target_dept and target_dept[0] != actor_dept:
                raise HTTPException(status_code=403, detail="팀장은 본인 팀 직원만 수정할 수 있습니다.")

        # 팀장/인사과장은 관리자 권한 수정 불가
        if not is_admin and data.is_admin is not None:
            raise HTTPException(status_code=403, detail="관리자 권한 변경은 관리자만 가능합니다.")

        updates = []
        params = []

        if data.nickname is not None:
            updates.append("nickname = ?"); params.append(data.nickname)
        if data.password is not None:
            updates.append("password_hash = ?"); params.append(hash_password(data.password))
        if data.is_admin is not None:
            updates.append("is_admin = ?"); params.append(1 if data.is_admin else 0)
        if data.department is not None:
            updates.append("department = ?"); params.append(data.department)
        if data.position is not None:
            pos_order = {"대표": 99, "인사과장": 3, "팀장": 2}.get(data.position, 1)
            updates.append("position = ?"); params.append(data.position)
            updates.append("position_order = ?"); params.append(pos_order)
        if data.join_date is not None:
            updates.append("join_date = ?"); params.append(data.join_date)
        if data.naver_works_id is not None:
            updates.append("naver_works_id = ?"); params.append(data.naver_works_id)
        if data.approver_id is not None:
            updates.append("approver_id = ?"); params.append(data.approver_id)
        if data.leave_exempt is not None:
            updates.append("leave_exempt = ?"); params.append(1 if data.leave_exempt else 0)
        if data.can_jeongyeol is not None:
            if not is_admin:
                raise HTTPException(status_code=403, detail="전결권 설정은 관리자만 가능합니다.")
            updates.append("can_jeongyeol = ?"); params.append(1 if data.can_jeongyeol else 0)
        if data.can_manage_part_time is not None:
            if not is_admin:
                raise HTTPException(status_code=403, detail="아르바이트 관리 권한 설정은 관리자만 가능합니다.")
            updates.append("can_manage_part_time = ?"); params.append(1 if data.can_manage_part_time else 0)

        if updates:
            params.append(user_id)
            con.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
            con.commit()

        target_user = con.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,)).fetchone()
        target_nickname = target_user[0] if target_user else None
        actor = con.execute("SELECT nickname FROM users WHERE user_id = ?", (actor_id,)).fetchone()
        actor_nickname = actor[0] if actor else None

    add_log(
        action_type="사용자 수정",
        target_type="user",
        target_id=str(user_id),
        target_name=target_nickname,
        user_nickname=actor_nickname,
        details=f"수정 항목: {', '.join(updates) if updates else '없음'}"
    )

    return {"success": True, "message": "사용자 정보 수정 완료"}


def _guard_employee_change(con, actor_id: int, is_admin: bool, actor_position: str, actor_dept: str, user_id: int):
    """팀장은 본인 팀만. 시스템 계정과 본인 퇴사·복귀는 막는다."""
    target = _user_row(con, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if actor_id == user_id:
        raise HTTPException(status_code=400, detail="본인 계정은 퇴사 처리할 수 없습니다.")
    if (target[0] or "").strip().lower() == "admin":
        raise HTTPException(status_code=400, detail="시스템 계정은 퇴사 처리할 수 없습니다.")
    if not is_admin and actor_position == "팀장" and target[2] != actor_dept:
        raise HTTPException(status_code=403, detail="팀장은 본인 팀 직원만 퇴사 처리할 수 있습니다.")
    return target


@router.post("/users/{user_id}/resign")
async def resign_user(user_id: int, body: ResignRequest, token: str):
    """직원 퇴사처리. 계정과 과거 급여·계약은 남기고, 퇴사일부터 로그인을 막는다."""
    ensure_users_table()
    resigned_on = _parse_iso_date(body.resigned_on, "퇴사일")
    with get_connection() as con:
        actor_id, is_admin, actor_position, actor_dept = _can_manage_users(token, con)
        target = _guard_employee_change(con, actor_id, is_admin, actor_position, actor_dept, user_id)
        join_date = (target[3] or "").strip()
        if join_date and resigned_on < join_date:
            raise HTTPException(status_code=400, detail="퇴사일은 입사일 이후여야 합니다.")
        con.execute(
            "UPDATE users SET resigned_on = ? WHERE user_id = ?",
            (resigned_on, user_id),
        )
        if resignation_in_effect(resigned_on):
            _ensure_sessions(con)
            con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        con.commit()
        actor = con.execute("SELECT nickname FROM users WHERE user_id = ?", (actor_id,)).fetchone()
    add_log(
        action_type="퇴사처리",
        target_type="user",
        target_id=str(user_id),
        target_name=target[1],
        user_nickname=actor[0] if actor else None,
        details=f"퇴사일: {resigned_on}",
    )
    return {
        "success": True,
        "user_id": user_id,
        "resigned_on": resigned_on,
        "message": f"'{target[1]}' 님을 {resigned_on} 퇴사 처리했습니다.",
    }


@router.post("/users/{user_id}/reinstate")
async def reinstate_user(user_id: int, token: str):
    """퇴사 처리를 취소하고 재직으로 되돌린다. 끊긴 로그인은 다시 로그인해야 한다."""
    ensure_users_table()
    with get_connection() as con:
        actor_id, is_admin, actor_position, actor_dept = _can_manage_users(token, con)
        target = _guard_employee_change(con, actor_id, is_admin, actor_position, actor_dept, user_id)
        if not (target[4] or "").strip():
            raise HTTPException(status_code=400, detail="재직 중인 직원입니다.")
        con.execute("UPDATE users SET resigned_on = NULL WHERE user_id = ?", (user_id,))
        con.commit()
        actor = con.execute("SELECT nickname FROM users WHERE user_id = ?", (actor_id,)).fetchone()
    add_log(
        action_type="재직복귀",
        target_type="user",
        target_id=str(user_id),
        target_name=target[1],
        user_nickname=actor[0] if actor else None,
        details="퇴사 처리를 취소함",
    )
    return {"success": True, "user_id": user_id, "message": f"'{target[1]}' 님을 재직으로 되돌렸습니다."}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, token: str):
    """사용자 삭제 (관리자만)"""
    ensure_users_table()

    with get_connection() as con:
        # 삭제는 관리자만 가능
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
        
        # 새 비밀번호로 업데이트 + must_change_password 해제
        con.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
            (hash_password(request.new_password), user_id)
        )
        con.commit()
    
    return {"success": True, "message": "비밀번호가 변경되었습니다."}


# ── 임시 테스트 엔드포인트 (배포 후 테스트 완료 시 삭제) ──────────────────────
@router.post("/dev/test-setup")
def dev_test_setup(secret: str):
    """테스트 계정 생성 + 토큰 반환. SECRET_KEY로 보호."""
    if secret != (os.getenv("SECRET_KEY") or ""):
        raise HTTPException(status_code=403, detail="forbidden")
    ensure_users_table()
    uname = "__test_relay__"
    pw = hash_password("Test1234!")
    tok = secrets.token_hex(32)
    with get_connection() as con:
        con.execute("DELETE FROM users WHERE username=?", (uname,))
        con.execute(
            "INSERT INTO users (username,password_hash,nickname,is_admin) VALUES (?,?,?,0)",
            (uname, pw, "테스트계정"),
        )
        uid = con.execute("SELECT user_id FROM users WHERE username=?", (uname,)).fetchone()[0]
        con.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id) VALUES (?,?)",
            (tok, uid),
        )
        con.commit()
    return {"token": tok, "username": uname}


@router.delete("/dev/test-cleanup")
def dev_test_cleanup(secret: str):
    """테스트 계정 삭제."""
    if secret != (os.getenv("SECRET_KEY") or ""):
        raise HTTPException(status_code=403, detail="forbidden")
    with get_connection() as con:
        row = con.execute("SELECT user_id FROM users WHERE username=?", ("__test_relay__",)).fetchone()
        if row:
            con.execute("DELETE FROM sessions WHERE user_id=?", (row[0],))
            con.execute("DELETE FROM users WHERE user_id=?", (row[0],))
            con.commit()
    return {"deleted": True}
# ─────────────────────────────────────────────────────────────────────────────

