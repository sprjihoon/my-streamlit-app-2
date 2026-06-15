"""
backend/app/api/leave.py - 연월차 관리 API
──────────────────────────────────────────
근로기준법 제60조 기반 연차 관리
- 7시간 기준 근무 (10~18시, 점심 1시간 제외)
- 1년 미만: 월 1일씩 발생 (최대 11일)
- 1년 이상: 15일 기본, 2년마다 1일 추가, 최대 25일
- 마이너스 연차 허용
- 시간 단위 관리 (1일=7시간, 반차=3.5시간)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, timedelta, datetime

from logic.db import get_connection
from backend.app.api.logs import add_log

router = APIRouter(prefix="/leave", tags=["leave"])

HOURS_PER_DAY = 7.0


# ─────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────

def ensure_leave_tables():
    """연차 관련 테이블 및 users 컬럼 생성"""
    with get_connection() as con:
        # users 테이블 확장
        for col_def in [
            ("department", "TEXT"),
            ("position", "TEXT"),
            ("naver_works_id", "TEXT"),
            ("approver_id", "INTEGER"),
            ("join_date", "TEXT"),
            ("must_change_password", "INTEGER DEFAULT 0"),
            ("leave_exempt", "INTEGER DEFAULT 0"),
        ]:
            try:
                con.execute(f"ALTER TABLE users ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass  # 이미 존재하면 무시

        # 연차 부여 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS leave_allowances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                total_hours REAL NOT NULL DEFAULT 0,
                manual_adjustment REAL NOT NULL DEFAULT 0,
                note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, year)
            )
        """)

        # 연차 신청 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                leave_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                hours_requested REAL NOT NULL,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )
        """)

        # 결재 라인 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS leave_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                approver_id INTEGER NOT NULL,
                step INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting',
                comment TEXT,
                acted_at DATETIME,
                UNIQUE(request_id, step)
            )
        """)

        # 공휴일 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL
            )
        """)

        # 기본 공휴일 (2026년)
        default_holidays_2026 = [
            ("2026-01-01", "신정"),
            ("2026-01-28", "설날 연휴"),
            ("2026-01-29", "설날"),
            ("2026-01-30", "설날 연휴"),
            ("2026-03-01", "삼일절"),
            ("2026-05-05", "어린이날"),
            ("2026-05-25", "부처님오신날"),
            ("2026-06-06", "현충일"),
            ("2026-08-15", "광복절"),
            ("2026-09-24", "추석 연휴"),
            ("2026-09-25", "추석"),
            ("2026-09-26", "추석 연휴"),
            ("2026-10-03", "개천절"),
            ("2026-10-09", "한글날"),
            ("2026-12-25", "크리스마스"),
        ]
        for h_date, h_name in default_holidays_2026:
            try:
                con.execute(
                    "INSERT OR IGNORE INTO holidays (date, name) VALUES (?, ?)",
                    (h_date, h_name)
                )
            except Exception:
                pass

        con.commit()


# ─────────────────────────────────────
# 연차 계산 유틸리티
# ─────────────────────────────────────

def _months_between(join: date, ref: date) -> int:
    """두 날짜 사이 완성된 월수"""
    months = (ref.year - join.year) * 12 + (ref.month - join.month)
    if ref.day < join.day:
        months -= 1
    return max(0, months)


def _anniversary(join: date, years: int) -> date:
    """입사일 기준 n번째 기념일"""
    try:
        return join.replace(year=join.year + years)
    except ValueError:
        # 2월 29일 → 2월 28일
        return date(join.year + years, join.month, 28)


def get_work_year_range(join_date_str: str, ref_date_str: str = None):
    """
    현재 연차 연도의 시작일/종료일 반환
    - 1년 미만: (입사일, 첫 기념일 전날)
    - 1년 이상: (마지막 기념일, 다음 기념일 전날)
    """
    join = date.fromisoformat(join_date_str)
    ref = date.fromisoformat(ref_date_str) if ref_date_str else date.today()

    months = _months_between(join, ref)
    years = months // 12

    if years == 0:
        start = join
        end = _anniversary(join, 1) - timedelta(days=1)
    else:
        start = _anniversary(join, years)
        end = _anniversary(join, years + 1) - timedelta(days=1)

    return start, end


def calculate_entitlement_hours(join_date_str: str, ref_date_str: str = None) -> float:
    """
    현재 연차 연도의 부여 시간 (근로기준법 제60조)

    - 1년 미만: 완성된 월 × 1일 (최대 11일) — 매월 개근 확인 후 부여 원칙이나
      실무상 월 단위 발생으로 계산
    - 1년 이상: 입사기념일에 일괄 부여
        · 1년차 기념일: 15일
        · 3년차 기념일부터 2년마다 1일 추가, 최대 25일
    """
    join = date.fromisoformat(join_date_str)
    ref = date.fromisoformat(ref_date_str) if ref_date_str else date.today()

    if ref < join:
        return 0.0

    months = _months_between(join, ref)
    years = months // 12

    if years == 0:
        # 1년 미만: 완성된 월 수 (입사 당월 제외, 최대 11일)
        days = min(months, 11)
    else:
        # 1년 이상: 기념일 기준 해당 연도 부여일수
        # years=1 → 15일, years=2 → 15일, years=3 → 16일, years=4 → 16일 ...
        base = 15
        extra = (years - 1) // 2  # 1년차: 0, 3년차: 1, 5년차: 2 ...
        days = min(base + extra, 25)

    return round(days * HOURS_PER_DAY, 1)


def count_leave_hours(start_date_str: str, end_date_str: str, leave_type: str, con) -> float:
    """공휴일/주말 제외한 실제 연차 시간 계산"""
    if leave_type in ("반차(오전)", "반차(오후)"):
        return HOURS_PER_DAY / 2

    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)

    holidays_set = set()
    try:
        rows = con.execute("SELECT date FROM holidays").fetchall()
        holidays_set = {r[0] for r in rows}
    except Exception:
        pass

    total = 0.0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur.isoformat() not in holidays_set:
            total += HOURS_PER_DAY
        cur += timedelta(days=1)
    return round(total, 1)


def get_approval_chain(user_id: int, con) -> list:
    """결재 라인 반환 (leave_exempt=1 제외, 순서대로)"""
    chain = []
    visited = {user_id}
    current = user_id

    while True:
        row = con.execute(
            "SELECT approver_id FROM users WHERE user_id = ?", (current,)
        ).fetchone()
        if not row or not row[0]:
            break
        approver_id = row[0]
        if approver_id in visited:
            break
        # 결재자가 leave_exempt이면 체인 종료
        exempt_row = con.execute(
            "SELECT leave_exempt FROM users WHERE user_id = ?", (approver_id,)
        ).fetchone()
        if exempt_row and exempt_row[0]:
            break
        chain.append(approver_id)
        visited.add(approver_id)
        current = approver_id

    return chain


def get_used_hours(user_id: int, con, year: int = None, join_date_str: str = None) -> float:
    """
    승인된 연차 사용 시간 합계.
    join_date_str 이 주어지면 현재 연차 연도(입사기념일 기준)의 사용량을,
    없으면 달력 연도(year) 기준으로 반환.
    """
    if join_date_str:
        start, end = get_work_year_range(join_date_str)
        year_start = start.isoformat()
        year_end = end.isoformat()
    else:
        if year is None:
            year = date.today().year
        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"

    row = con.execute(
        """SELECT COALESCE(SUM(hours_requested), 0) FROM leave_requests
           WHERE user_id = ? AND status = 'approved'
           AND start_date >= ? AND start_date <= ?""",
        (user_id, year_start, year_end)
    ).fetchone()
    return round(float(row[0]) if row else 0.0, 1)


def get_leave_summary_data(user_id: int, year: int = None):
    """
    연차 현황 데이터 반환 (봇·웹 공용)
    - 부여량·사용량 모두 입사기념일 기준 연도로 계산
    - year 파라미터는 수동 조정 조회용으로만 사용 (하위 호환)
    """
    ensure_leave_tables()
    if year is None:
        year = date.today().year

    with get_connection() as con:
        user = con.execute(
            "SELECT nickname, join_date, leave_exempt FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not user:
            return None

        nickname, join_date, leave_exempt = user

        if leave_exempt:
            return {"exempt": True, "nickname": nickname}

        if not join_date:
            return {"no_join_date": True, "nickname": nickname}

        # 현재 연차 연도 범위 (입사기념일 기준)
        wy_start, wy_end = get_work_year_range(join_date)

        # 연차 부여 시간 (현재 연차 연도의 부여량)
        total_hours = calculate_entitlement_hours(join_date)

        # 수동 조정 (달력 연도 기준 유지)
        allow_row = con.execute(
            "SELECT manual_adjustment FROM leave_allowances WHERE user_id = ? AND year = ?",
            (user_id, year)
        ).fetchone()
        adjustment = float(allow_row[0]) if allow_row else 0.0

        # 사용 시간 (입사기념일 기준 연도)
        used_hours = get_used_hours(user_id, con, join_date_str=join_date)

        # 결재 중인 시간 (입사기념일 기준 연도)
        pending_row = con.execute(
            """SELECT COALESCE(SUM(r.hours_requested), 0)
               FROM leave_requests r
               WHERE r.user_id = ? AND r.status = 'pending'
               AND r.start_date >= ? AND r.start_date <= ?""",
            (user_id, wy_start.isoformat(), wy_end.isoformat())
        ).fetchone()
        pending_hours = round(float(pending_row[0]) if pending_row else 0.0, 1)

        total_with_adj = total_hours + adjustment
        remaining_hours = total_with_adj - used_hours

        return {
            "user_id": user_id,
            "nickname": nickname,
            "year": year,
            "join_date": join_date,
            "work_year_start": wy_start.isoformat(),
            "work_year_end": wy_end.isoformat(),
            "total_hours": total_with_adj,
            "total_days": round(total_with_adj / HOURS_PER_DAY, 1),
            "used_hours": used_hours,
            "used_days": round(used_hours / HOURS_PER_DAY, 1),
            "pending_hours": pending_hours,
            "pending_days": round(pending_hours / HOURS_PER_DAY, 1),
            "remaining_hours": round(remaining_hours, 1),
            "remaining_days": round(remaining_hours / HOURS_PER_DAY, 1),
        }


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class LeaveRequestCreate(BaseModel):
    leave_type: str  # 연차, 반차(오전), 반차(오후)
    start_date: str
    end_date: str
    reason: Optional[str] = None


class ApprovalAction(BaseModel):
    action: str  # approve / reject
    comment: Optional[str] = None


class ManualAdjustment(BaseModel):
    user_id: int
    year: int
    adjustment_hours: float
    note: Optional[str] = None


class HolidayCreate(BaseModel):
    date: str
    name: str


# ─────────────────────────────────────
# 내부 헬퍼: 네이버웍스 DM 발송
# ─────────────────────────────────────

async def send_nw_dm(naver_works_id: str, message: str):
    """네이버웍스 개인 DM 발송 (실패해도 무시)"""
    if not naver_works_id:
        return
    try:
        from backend.app.services import get_naver_works_client
        client = get_naver_works_client()
        await client.send_text_message(naver_works_id, message, channel_type="user")
    except Exception as e:
        print(f"[Leave] NW DM 발송 실패: {e}")


# ─────────────────────────────────────
# API: 내 연차 현황
# ─────────────────────────────────────

@router.get("/summary")
async def get_my_leave_summary(token: str, year: Optional[int] = None):
    """내 연차 현황"""
    ensure_leave_tables()
    if year is None:
        year = date.today().year

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        user_id = session[0]

    summary = get_leave_summary_data(user_id, year)
    if not summary:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return summary


# ─────────────────────────────────────
# API: 내 신청 목록
# ─────────────────────────────────────

@router.get("/requests")
async def get_my_requests(token: str, year: Optional[int] = None):
    """내 연차 신청 목록"""
    ensure_leave_tables()
    if year is None:
        year = date.today().year

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        user_id = session[0]

        rows = con.execute(
            """SELECT r.id, r.leave_type, r.start_date, r.end_date,
                      r.hours_requested, r.reason, r.status, r.created_at,
                      (SELECT GROUP_CONCAT(u.nickname || ':' || a.status, '|')
                       FROM leave_approvals a JOIN users u ON a.approver_id = u.user_id
                       WHERE a.request_id = r.id ORDER BY a.step) as approvals
               FROM leave_requests r
               WHERE r.user_id = ? AND strftime('%Y', r.start_date) = ?
               ORDER BY r.created_at DESC""",
            (user_id, str(year))
        ).fetchall()

    return [
        {
            "id": r[0],
            "leave_type": r[1],
            "start_date": r[2],
            "end_date": r[3],
            "hours_requested": r[4],
            "days_requested": round(r[4] / HOURS_PER_DAY, 1),
            "reason": r[5],
            "status": r[6],
            "created_at": r[7],
            "approvals": r[8] or "",
        }
        for r in rows
    ]


# ─────────────────────────────────────
# API: 연차 신청
# ─────────────────────────────────────

@router.post("/requests")
async def create_leave_request(data: LeaveRequestCreate, token: str):
    """연차 신청"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        user_id = session[0]

        user = con.execute(
            "SELECT nickname, join_date, leave_exempt, naver_works_id FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        nickname, join_date, leave_exempt, requester_nw_id = user

        if leave_exempt:
            raise HTTPException(status_code=400, detail="연차 관리 대상이 아닙니다.")

        if not join_date:
            raise HTTPException(status_code=400, detail="입사일이 등록되지 않았습니다. 관리자에게 문의하세요.")

        # 날짜 유효성
        try:
            s = date.fromisoformat(data.start_date)
            e = date.fromisoformat(data.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)")

        if s > e:
            raise HTTPException(status_code=400, detail="종료일이 시작일보다 이전입니다.")

        if data.leave_type in ("반차(오전)", "반차(오후)") and s != e:
            raise HTTPException(status_code=400, detail="반차는 하루만 신청 가능합니다.")

        # 사용 시간 계산
        hours = count_leave_hours(data.start_date, data.end_date, data.leave_type, con)
        if hours <= 0:
            raise HTTPException(status_code=400, detail="신청 기간에 근무일이 없습니다. (주말/공휴일 확인)")

        # 연차 신청 저장
        cur = con.execute(
            """INSERT INTO leave_requests (user_id, leave_type, start_date, end_date, hours_requested, reason, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (user_id, data.leave_type, data.start_date, data.end_date, hours, data.reason)
        )
        request_id = cur.lastrowid

        # 결재 라인 생성
        chain = get_approval_chain(user_id, con)
        for step, approver_id in enumerate(chain, start=1):
            con.execute(
                """INSERT INTO leave_approvals (request_id, approver_id, step, status)
                   VALUES (?, ?, ?, ?)""",
                (request_id, approver_id, step, "waiting" if step == 1 else "pending_prev")
            )

        con.commit()

        # 결재자 정보 조회 (DM 발송용)
        approver_nw_ids = []
        if chain:
            first_approver = con.execute(
                "SELECT nickname, naver_works_id FROM users WHERE user_id = ?", (chain[0],)
            ).fetchone()
            if first_approver:
                approver_nw_ids.append((first_approver[0], first_approver[1]))

    # 로그
    add_log(
        action_type="연차 신청",
        target_type="leave",
        target_id=str(request_id),
        target_name=nickname,
        user_nickname=nickname,
        details=f"{data.leave_type} {data.start_date}~{data.end_date} ({round(hours/HOURS_PER_DAY,1)}일/{hours}시간)"
    )

    # 네이버웍스 알림
    days_str = round(hours / HOURS_PER_DAY, 1)
    for approver_name, approver_nw_id in approver_nw_ids:
        msg = (
            f"📋 연차 결재 요청\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 신청자: {nickname}\n"
            f"📅 기간: {data.start_date} ~ {data.end_date}\n"
            f"🏷️ 종류: {data.leave_type}\n"
            f"⏱️ 시간: {hours}시간 ({days_str}일)\n"
            f"💬 사유: {data.reason or '없음'}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"승인: '승인 #{request_id}'\n"
            f"반려: '반려 #{request_id} 사유입력'"
        )
        import asyncio
        asyncio.create_task(send_nw_dm(approver_nw_id, msg))

    return {
        "success": True,
        "request_id": request_id,
        "hours_requested": hours,
        "days_requested": days_str,
        "message": f"연차 신청이 완료되었습니다. ({len(chain)}단계 결재 진행 중)"
    }


# ─────────────────────────────────────
# API: 신청 취소
# ─────────────────────────────────────

class CancelLeaveBody(BaseModel):
    reason: str = ""


@router.put("/requests/{request_id}/cancel")
async def cancel_leave_request(request_id: int, token: str, body: CancelLeaveBody = None):
    """연차 신청 취소 (pending/approved 모두 가능, 모든 기록 보존)"""
    ensure_leave_tables()
    if body is None:
        body = CancelLeaveBody()

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id, is_admin FROM sessions s JOIN users u USING(user_id) WHERE s.token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        user_id, is_admin = session[0], bool(session[1])

        req = con.execute(
            "SELECT user_id, status, leave_type, start_date, end_date, hours_requested FROM leave_requests WHERE id = ?",
            (request_id,)
        ).fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")

        owner_id, current_status, leave_type, start_date, end_date, hours = req

        # 본인 또는 관리자만 취소 가능
        if owner_id != user_id and not is_admin:
            raise HTTPException(status_code=403, detail="본인 또는 관리자만 취소할 수 있습니다.")

        # 이미 취소/반려된 건은 불가
        if current_status in ("cancelled", "rejected"):
            raise HTTPException(status_code=400, detail=f"이미 '{current_status}' 상태인 신청은 취소할 수 없습니다.")

        actor = con.execute("SELECT nickname FROM users WHERE user_id=?", (user_id,)).fetchone()
        actor_name = actor[0] if actor else str(user_id)
        owner = con.execute("SELECT nickname FROM users WHERE user_id=?", (owner_id,)).fetchone()
        owner_name = owner[0] if owner else str(owner_id)

        now = datetime.now().isoformat()

        # 상태를 cancelled로, 취소 사유·취소자·취소시각 기록
        # cancel_reason 컬럼이 없으면 마이그레이션
        cols = [c[1] for c in con.execute("PRAGMA table_info(leave_requests)").fetchall()]
        if "cancel_reason" not in cols:
            con.execute("ALTER TABLE leave_requests ADD COLUMN cancel_reason TEXT")
        if "cancelled_by" not in cols:
            con.execute("ALTER TABLE leave_requests ADD COLUMN cancelled_by TEXT")
        if "cancelled_at" not in cols:
            con.execute("ALTER TABLE leave_requests ADD COLUMN cancelled_at TEXT")

        con.execute(
            """UPDATE leave_requests
               SET status='cancelled', updated_at=?, cancel_reason=?, cancelled_by=?, cancelled_at=?
               WHERE id=?""",
            (now, body.reason or None, actor_name, now, request_id)
        )

        # 대기 중인 결재 항목도 'cancelled' 처리 (이력 보존)
        con.execute(
            "UPDATE leave_approvals SET status='cancelled', acted_at=? WHERE request_id=? AND status='waiting'",
            (now, request_id)
        )
        con.commit()

    action = "연차 취소(관리자)" if (is_admin and owner_id != user_id) else "연차 취소"
    detail = f"#{request_id} {leave_type} {start_date}~{end_date} / 이전상태:{current_status}"
    if body.reason:
        detail += f" / 사유:{body.reason}"
    add_log(
        action_type=action,
        target_type="leave",
        target_id=str(request_id),
        target_name=owner_name,
        user_nickname=actor_name,
        details=detail,
    )

    return {"success": True, "message": "연차가 취소되었습니다. 기록은 이력에 보존됩니다."}


# ─────────────────────────────────────
# API: 내 결재 대기 목록
# ─────────────────────────────────────

@router.get("/pending-approvals")
async def get_pending_approvals(token: str):
    """내가 결재해야 할 목록"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        user_id = session[0]

        rows = con.execute(
            """SELECT a.id, a.request_id, a.step,
                      r.leave_type, r.start_date, r.end_date, r.hours_requested, r.reason, r.created_at,
                      u.nickname, u.department, u.position
               FROM leave_approvals a
               JOIN leave_requests r ON a.request_id = r.id
               JOIN users u ON r.user_id = u.user_id
               WHERE a.approver_id = ? AND a.status = 'waiting' AND r.status = 'pending'
               ORDER BY r.created_at ASC""",
            (user_id,)
        ).fetchall()

    return [
        {
            "approval_id": r[0],
            "request_id": r[1],
            "step": r[2],
            "leave_type": r[3],
            "start_date": r[4],
            "end_date": r[5],
            "hours_requested": r[6],
            "days_requested": round(r[6] / HOURS_PER_DAY, 1),
            "reason": r[7],
            "created_at": r[8],
            "requester_nickname": r[9],
            "requester_department": r[10],
            "requester_position": r[11],
        }
        for r in rows
    ]


# ─────────────────────────────────────
# API: 결재 처리 이력 (내가 처리한 것)
# ─────────────────────────────────────

@router.get("/approval-history")
async def get_approval_history(token: str, limit: int = 100):
    """내가 처리한 결재 이력 (승인/반려/취소 모두)"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        user_id = session[0]

        rows = con.execute(
            """SELECT a.id, a.request_id, a.step, a.status, a.comment, a.acted_at,
                      r.leave_type, r.start_date, r.end_date, r.hours_requested,
                      r.status AS req_status, r.cancel_reason,
                      u.nickname, u.department, u.position
               FROM leave_approvals a
               JOIN leave_requests r ON a.request_id = r.id
               JOIN users u ON r.user_id = u.user_id
               WHERE a.approver_id = ? AND a.status != 'waiting'
               ORDER BY COALESCE(a.acted_at, r.created_at) DESC
               LIMIT ?""",
            (user_id, limit)
        ).fetchall()

    return [
        {
            "approval_id": r[0],
            "request_id": r[1],
            "step": r[2],
            "status": r[3],           # approved / rejected / cancelled
            "comment": r[4],
            "acted_at": r[5],
            "leave_type": r[6],
            "start_date": r[7],
            "end_date": r[8],
            "hours_requested": r[9],
            "days_requested": round(r[9] / HOURS_PER_DAY, 1),
            "req_status": r[10],
            "cancel_reason": r[11],
            "requester_nickname": r[12],
            "requester_department": r[13],
            "requester_position": r[14],
        }
        for r in rows
    ]


# ─────────────────────────────────────
# API: 승인 / 반려
# ─────────────────────────────────────

@router.put("/approvals/{approval_id}/act")
async def act_on_approval(approval_id: int, data: ApprovalAction, token: str):
    """연차 승인 또는 반려"""
    ensure_leave_tables()

    if data.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action은 'approve' 또는 'reject'여야 합니다.")

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        actor_id = session[0]

        approval = con.execute(
            "SELECT request_id, approver_id, step, status FROM leave_approvals WHERE id = ?",
            (approval_id,)
        ).fetchone()
        if not approval:
            raise HTTPException(status_code=404, detail="결재 항목을 찾을 수 없습니다.")
        request_id, approver_id, step, current_status = approval

        if approver_id != actor_id:
            raise HTTPException(status_code=403, detail="본인 결재 항목만 처리할 수 있습니다.")
        if current_status != "waiting":
            raise HTTPException(status_code=400, detail="이미 처리된 결재입니다.")

        req = con.execute(
            "SELECT user_id, leave_type, start_date, end_date, hours_requested, status FROM leave_requests WHERE id = ?",
            (request_id,)
        ).fetchone()
        if not req or req[5] != "pending":
            raise HTTPException(status_code=400, detail="처리할 수 없는 신청 상태입니다.")
        requester_id, leave_type, start_date, end_date, hours, _ = req

        actor = con.execute("SELECT nickname, naver_works_id FROM users WHERE user_id=?", (actor_id,)).fetchone()
        actor_name = actor[0] if actor else str(actor_id)

        requester = con.execute("SELECT nickname, naver_works_id FROM users WHERE user_id=?", (requester_id,)).fetchone()
        requester_name = requester[0] if requester else str(requester_id)
        requester_nw_id = requester[1] if requester else None

        now = datetime.now().isoformat()

        if data.action == "reject":
            # 반려 처리
            con.execute(
                "UPDATE leave_approvals SET status='rejected', comment=?, acted_at=? WHERE id=?",
                (data.comment, now, approval_id)
            )
            con.execute(
                "UPDATE leave_requests SET status='rejected', updated_at=? WHERE id=?",
                (now, request_id)
            )
            con.commit()

            add_log("연차 반려", "leave", str(request_id), requester_name, actor_name,
                    f"#{request_id} {leave_type} {start_date}~{end_date}, 사유: {data.comment or '없음'}")

            # 신청자에게 DM
            msg = (
                f"❌ 연차 반려\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📅 {start_date} ~ {end_date} ({leave_type})\n"
                f"👤 반려자: {actor_name}\n"
                f"💬 사유: {data.comment or '없음'}"
            )
            import asyncio
            asyncio.create_task(send_nw_dm(requester_nw_id, msg))

            return {"success": True, "message": "반려 처리 완료"}

        else:
            # 승인 처리
            con.execute(
                "UPDATE leave_approvals SET status='approved', comment=?, acted_at=? WHERE id=?",
                (data.comment, now, approval_id)
            )

            # 다음 결재 단계 확인
            next_step = con.execute(
                "SELECT id, approver_id FROM leave_approvals WHERE request_id=? AND step=?",
                (request_id, step + 1)
            ).fetchone()

            if next_step:
                # 다음 단계 활성화
                con.execute(
                    "UPDATE leave_approvals SET status='waiting' WHERE id=?",
                    (next_step[0],)
                )
                con.commit()

                # 다음 결재자에게 DM
                next_approver = con.execute(
                    "SELECT nickname, naver_works_id FROM users WHERE user_id=?", (next_step[1],)
                ).fetchone()
                if next_approver and next_approver[1]:
                    days_str = round(hours / HOURS_PER_DAY, 1)
                    msg = (
                        f"📋 연차 결재 요청 ({step + 1}차)\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"👤 신청자: {requester_name}\n"
                        f"📅 기간: {start_date} ~ {end_date}\n"
                        f"🏷️ 종류: {leave_type}\n"
                        f"⏱️ {hours}시간 ({days_str}일)\n"
                        f"✅ {actor_name} 승인 완료\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"승인: '승인 #{request_id}'\n"
                        f"반려: '반려 #{request_id} 사유입력'"
                    )
                    import asyncio
                    asyncio.create_task(send_nw_dm(next_approver[1], msg))

                return {"success": True, "message": f"{step}차 승인 완료. 다음 결재자에게 전달되었습니다."}

            else:
                # 최종 승인
                con.execute(
                    "UPDATE leave_requests SET status='approved', updated_at=? WHERE id=?",
                    (now, request_id)
                )
                con.commit()

                add_log("연차 승인", "leave", str(request_id), requester_name, actor_name,
                        f"#{request_id} {leave_type} {start_date}~{end_date} ({hours}시간)")

                # 신청자에게 DM
                summary = get_leave_summary_data(requester_id)
                remaining = summary.get("remaining_hours", 0) if summary else 0
                days_str = round(hours / HOURS_PER_DAY, 1)
                msg = (
                    f"✅ 연차 승인 완료!\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📅 {start_date} ~ {end_date} ({leave_type})\n"
                    f"⏱️ {hours}시간 ({days_str}일) 차감\n"
                    f"📊 잔여: {remaining}시간 ({round(remaining/HOURS_PER_DAY,1)}일)"
                )
                import asyncio
                asyncio.create_task(send_nw_dm(requester_nw_id, msg))

                return {"success": True, "message": "최종 승인 완료. 연차가 차감되었습니다."}


# ─────────────────────────────────────
# API: 관리자 - 전체 현황
# ─────────────────────────────────────

@router.get("/admin/all")
async def get_all_leave_status(token: str, year: Optional[int] = None):
    """전체 직원 연차 현황 (관리자)"""
    ensure_leave_tables()
    if year is None:
        year = date.today().year

    with get_connection() as con:
        session = con.execute(
            "SELECT u.user_id, u.is_admin FROM sessions s JOIN users u ON s.user_id=u.user_id WHERE s.token=?",
            (token,)
        ).fetchone()
        if not session or not session[1]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

        users = con.execute(
            """SELECT user_id, nickname, department, position, join_date, leave_exempt
               FROM users ORDER BY department, position_order DESC, nickname"""
        ).fetchall()

    result = []
    for u in users:
        uid, nickname, dept, pos, join_date, exempt = u
        if exempt:
            result.append({
                "user_id": uid, "nickname": nickname,
                "department": dept, "position": pos,
                "exempt": True
            })
            continue
        if not join_date:
            result.append({
                "user_id": uid, "nickname": nickname,
                "department": dept, "position": pos,
                "no_join_date": True
            })
            continue
        summary = get_leave_summary_data(uid, year)
        if summary:
            summary["department"] = dept
            summary["position"] = pos
            result.append(summary)

    return result


@router.get("/admin/requests")
async def get_all_requests(token: str, year: Optional[int] = None, status: Optional[str] = None):
    """전체 연차 신청 목록 (관리자)"""
    ensure_leave_tables()
    if year is None:
        year = date.today().year

    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id=u.user_id WHERE s.token=?",
            (token,)
        ).fetchone()
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

        query = """
            SELECT r.id, r.leave_type, r.start_date, r.end_date, r.hours_requested,
                   r.reason, r.status, r.created_at,
                   u.nickname, u.department, u.position
            FROM leave_requests r
            JOIN users u ON r.user_id = u.user_id
            WHERE strftime('%Y', r.start_date) = ?
        """
        params = [str(year)]
        if status:
            query += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.created_at DESC"

        rows = con.execute(query, params).fetchall()

    return [
        {
            "id": r[0],
            "leave_type": r[1],
            "start_date": r[2],
            "end_date": r[3],
            "hours_requested": r[4],
            "days_requested": round(r[4] / HOURS_PER_DAY, 1),
            "reason": r[5],
            "status": r[6],
            "created_at": r[7],
            "nickname": r[8],
            "department": r[9],
            "position": r[10],
        }
        for r in rows
    ]


@router.post("/admin/adjustment")
async def adjust_leave(data: ManualAdjustment, token: str):
    """연차 수동 조정 (관리자)"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT u.user_id, u.is_admin, u.nickname FROM sessions s JOIN users u ON s.user_id=u.user_id WHERE s.token=?",
            (token,)
        ).fetchone()
        if not session or not session[1]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        actor_name = session[2]

        con.execute(
            """INSERT INTO leave_allowances (user_id, year, total_hours, manual_adjustment, note, updated_at)
               VALUES (?, ?, 0, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, year) DO UPDATE SET
               manual_adjustment = excluded.manual_adjustment,
               note = excluded.note,
               updated_at = CURRENT_TIMESTAMP""",
            (data.user_id, data.year, data.adjustment_hours, data.note)
        )
        con.commit()

        target = con.execute("SELECT nickname FROM users WHERE user_id=?", (data.user_id,)).fetchone()
        target_name = target[0] if target else str(data.user_id)

    add_log("연차 조정", "leave", str(data.user_id), target_name, actor_name,
            f"{data.year}년 {data.adjustment_hours:+.1f}시간 ({data.note or ''})")

    return {"success": True, "message": f"{target_name}의 {data.year}년 연차가 조정되었습니다."}


# ─────────────────────────────────────
# API: 공휴일 관리
# ─────────────────────────────────────

@router.get("/holidays")
async def get_holidays(year: Optional[int] = None):
    """공휴일 목록"""
    ensure_leave_tables()
    if year is None:
        year = date.today().year

    with get_connection() as con:
        rows = con.execute(
            "SELECT id, date, name FROM holidays WHERE strftime('%Y', date) = ? ORDER BY date",
            (str(year),)
        ).fetchall()

    return [{"id": r[0], "date": r[1], "name": r[2]} for r in rows]


@router.post("/holidays")
async def add_holiday(data: HolidayCreate, token: str):
    """공휴일 등록 (관리자)"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id=u.user_id WHERE s.token=?",
            (token,)
        ).fetchone()
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        try:
            con.execute("INSERT OR REPLACE INTO holidays (date, name) VALUES (?, ?)", (data.date, data.name))
            con.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"success": True}


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(holiday_id: int, token: str):
    """공휴일 삭제 (관리자)"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT u.is_admin FROM sessions s JOIN users u ON s.user_id=u.user_id WHERE s.token=?",
            (token,)
        ).fetchone()
        if not session or not session[0]:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        con.execute("DELETE FROM holidays WHERE id=?", (holiday_id,))
        con.commit()

    return {"success": True}


# ─────────────────────────────────────
# API: 달력용 연차 현황
# ─────────────────────────────────────

@router.get("/calendar")
async def get_leave_calendar(token: str, year: int, month: int):
    """달력용 월간 연차 현황 (날짜별 휴가자 목록)"""
    ensure_leave_tables()

    with get_connection() as con:
        session = con.execute(
            "SELECT user_id FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

        month_start = f"{year}-{month:02d}-01"
        import calendar as cal
        last_day = cal.monthrange(year, month)[1]
        month_end = f"{year}-{month:02d}-{last_day:02d}"

        rows = con.execute(
            """SELECT r.start_date, r.end_date, r.leave_type, r.hours_requested,
                      u.nickname, u.department, u.position
               FROM leave_requests r
               JOIN users u ON r.user_id = u.user_id
               WHERE r.status = 'approved'
               AND r.end_date >= ? AND r.start_date <= ?
               ORDER BY u.department, u.nickname""",
            (month_start, month_end)
        ).fetchall()

        # 공휴일 목록
        holidays = con.execute(
            "SELECT date, name FROM holidays WHERE date >= ? AND date <= ?",
            (month_start, month_end)
        ).fetchall()

    # 날짜별로 그룹화
    day_map: dict = {}
    for start_str, end_str, leave_type, hours, nickname, dept, pos in rows:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        cur = start
        while cur <= end:
            if cur.month == month:
                day_key = cur.isoformat()
                if day_key not in day_map:
                    day_map[day_key] = []
                day_map[day_key].append({
                    "nickname": nickname,
                    "department": dept,
                    "position": pos,
                    "leave_type": leave_type,
                    "hours": hours,
                })
            cur += timedelta(days=1)

    return {
        "year": year,
        "month": month,
        "days": day_map,
        "holidays": {h[0]: h[1] for h in holidays},
    }


# ─────────────────────────────────────
# 봇 전용 헬퍼
# ─────────────────────────────────────

def get_user_id_by_nw_id(naver_works_id: str) -> Optional[int]:
    """네이버웍스 ID로 user_id 조회"""
    ensure_leave_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT user_id FROM users WHERE naver_works_id = ? OR username = ?",
            (naver_works_id, naver_works_id)
        ).fetchone()
        return row[0] if row else None


def bot_get_leave_summary(naver_works_id: str) -> dict:
    """봇용 연차 현황 조회"""
    user_id = get_user_id_by_nw_id(naver_works_id)
    if not user_id:
        return {"error": "등록된 사용자가 아닙니다."}
    return get_leave_summary_data(user_id) or {"error": "연차 정보를 찾을 수 없습니다."}


def bot_apply_leave(naver_works_id: str, leave_type: str, start_date: str, end_date: str, reason: str = None) -> dict:
    """봇용 연차 신청"""
    ensure_leave_tables()
    user_id = get_user_id_by_nw_id(naver_works_id)
    if not user_id:
        return {"error": "등록된 사용자가 아닙니다."}

    with get_connection() as con:
        user = con.execute(
            "SELECT nickname, join_date, leave_exempt FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not user:
            return {"error": "사용자를 찾을 수 없습니다."}
        nickname, join_date, leave_exempt = user

        if leave_exempt:
            return {"error": "연차 관리 대상이 아닙니다."}
        if not join_date:
            return {"error": "입사일이 등록되지 않았습니다. 관리자에게 문의하세요."}

        try:
            s = date.fromisoformat(start_date)
            e = date.fromisoformat(end_date)
        except ValueError:
            return {"error": "날짜 형식 오류 (YYYY-MM-DD)"}

        if s > e:
            return {"error": "종료일이 시작일보다 이전입니다."}

        hours = count_leave_hours(start_date, end_date, leave_type, con)
        if hours <= 0:
            return {"error": "신청 기간에 근무일이 없습니다. (주말/공휴일 확인)"}

        cur = con.execute(
            """INSERT INTO leave_requests (user_id, leave_type, start_date, end_date, hours_requested, reason, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (user_id, leave_type, start_date, end_date, hours, reason)
        )
        request_id = cur.lastrowid

        chain = get_approval_chain(user_id, con)
        for step, approver_id in enumerate(chain, start=1):
            con.execute(
                """INSERT INTO leave_approvals (request_id, approver_id, step, status)
                   VALUES (?, ?, ?, ?)""",
                (request_id, approver_id, step, "waiting" if step == 1 else "pending_prev")
            )
        con.commit()

        # 결재자 DM 발송
        if chain:
            approver = con.execute(
                "SELECT nickname, naver_works_id FROM users WHERE user_id=?", (chain[0],)
            ).fetchone()
            if approver and approver[1]:
                days_str = round(hours / HOURS_PER_DAY, 1)
                msg = (
                    f"📋 연차 결재 요청\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"👤 신청자: {nickname}\n"
                    f"📅 기간: {start_date} ~ {end_date}\n"
                    f"🏷️ 종류: {leave_type}\n"
                    f"⏱️ {hours}시간 ({days_str}일)\n"
                    f"💬 사유: {reason or '없음'}\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"승인: '승인 #{request_id}'\n"
                    f"반려: '반려 #{request_id} 사유입력'"
                )
                import asyncio
                try:
                    asyncio.create_task(send_nw_dm(approver[1], msg))
                except Exception:
                    pass

    days_str = round(hours / HOURS_PER_DAY, 1)
    return {
        "success": True,
        "request_id": request_id,
        "hours_requested": hours,
        "days_requested": days_str,
        "approvers": len(chain),
        "message": f"#{request_id} 연차 신청 완료 ({days_str}일/{hours}시간, {len(chain)}단계 결재)"
    }


def bot_cancel_leave(naver_works_id: str, request_id: int) -> dict:
    """봇용 연차 취소"""
    ensure_leave_tables()
    user_id = get_user_id_by_nw_id(naver_works_id)
    if not user_id:
        return {"error": "등록된 사용자가 아닙니다."}

    with get_connection() as con:
        req = con.execute(
            "SELECT user_id, status FROM leave_requests WHERE id=?", (request_id,)
        ).fetchone()
        if not req:
            return {"error": f"#{request_id} 신청을 찾을 수 없습니다."}
        if req[0] != user_id:
            return {"error": "본인 신청만 취소할 수 있습니다."}
        if req[1] != "pending":
            return {"error": f"'{req[1]}' 상태는 취소할 수 없습니다."}

        con.execute(
            "UPDATE leave_requests SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (request_id,)
        )
        con.commit()

    return {"success": True, "message": f"#{request_id} 연차 신청이 취소되었습니다."}


def bot_approve_leave(naver_works_id: str, request_id: int, comment: str = None) -> dict:
    """봇용 연차 승인"""
    ensure_leave_tables()
    user_id = get_user_id_by_nw_id(naver_works_id)
    if not user_id:
        return {"error": "등록된 사용자가 아닙니다."}

    with get_connection() as con:
        approval = con.execute(
            """SELECT id, step, status FROM leave_approvals
               WHERE request_id=? AND approver_id=? AND status='waiting'""",
            (request_id, user_id)
        ).fetchone()
        if not approval:
            return {"error": f"#{request_id} 결재할 항목이 없습니다. (이미 처리됐거나 권한 없음)"}

        approval_id, step, _ = approval

        req = con.execute(
            "SELECT user_id, leave_type, start_date, end_date, hours_requested FROM leave_requests WHERE id=? AND status='pending'",
            (request_id,)
        ).fetchone()
        if not req:
            return {"error": "처리할 수 없는 상태입니다."}
        requester_id, leave_type, start_date, end_date, hours = req

        now = datetime.now().isoformat()
        con.execute(
            "UPDATE leave_approvals SET status='approved', comment=?, acted_at=? WHERE id=?",
            (comment, now, approval_id)
        )

        next_step = con.execute(
            "SELECT id, approver_id FROM leave_approvals WHERE request_id=? AND step=?",
            (request_id, step + 1)
        ).fetchone()

        actor = con.execute("SELECT nickname FROM users WHERE user_id=?", (user_id,)).fetchone()
        actor_name = actor[0] if actor else str(user_id)

        requester = con.execute("SELECT nickname, naver_works_id FROM users WHERE user_id=?", (requester_id,)).fetchone()
        requester_name = requester[0] if requester else str(requester_id)
        requester_nw_id = requester[1] if requester else None

        if next_step:
            con.execute("UPDATE leave_approvals SET status='waiting' WHERE id=?", (next_step[0],))
            con.commit()
            next_approver = con.execute(
                "SELECT nickname, naver_works_id FROM users WHERE user_id=?", (next_step[1],)
            ).fetchone()
            if next_approver and next_approver[1]:
                days_str = round(hours / HOURS_PER_DAY, 1)
                msg = (
                    f"📋 연차 결재 요청 ({step+1}차)\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"👤 신청자: {requester_name}\n"
                    f"📅 {start_date} ~ {end_date} ({leave_type})\n"
                    f"⏱️ {hours}시간 ({days_str}일)\n"
                    f"✅ {actor_name} 승인 완료\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"승인: '승인 #{request_id}'\n"
                    f"반려: '반려 #{request_id} 사유입력'"
                )
                import asyncio
                try:
                    asyncio.create_task(send_nw_dm(next_approver[1], msg))
                except Exception:
                    pass
            return {"success": True, "message": f"#{request_id} {step}차 승인 완료. 다음 결재자에게 전달했습니다."}
        else:
            con.execute(
                "UPDATE leave_requests SET status='approved', updated_at=? WHERE id=?",
                (now, request_id)
            )
            con.commit()
            summary = get_leave_summary_data(requester_id)
            remaining = summary.get("remaining_hours", 0) if summary else 0
            days_str = round(hours / HOURS_PER_DAY, 1)
            msg = (
                f"✅ 연차 승인 완료!\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📅 {start_date} ~ {end_date} ({leave_type})\n"
                f"⏱️ {hours}시간 ({days_str}일) 차감\n"
                f"📊 잔여: {remaining}시간 ({round(remaining/HOURS_PER_DAY,1)}일)"
            )
            import asyncio
            try:
                asyncio.create_task(send_nw_dm(requester_nw_id, msg))
            except Exception:
                pass
            add_log("연차 승인", "leave", str(request_id), requester_name, actor_name,
                    f"#{request_id} {leave_type} {start_date}~{end_date}")
            return {"success": True, "message": f"#{request_id} 최종 승인 완료! {requester_name}에게 알림을 보냈습니다."}


def bot_reject_leave(naver_works_id: str, request_id: int, comment: str = None) -> dict:
    """봇용 연차 반려"""
    ensure_leave_tables()
    user_id = get_user_id_by_nw_id(naver_works_id)
    if not user_id:
        return {"error": "등록된 사용자가 아닙니다."}

    with get_connection() as con:
        approval = con.execute(
            """SELECT id FROM leave_approvals
               WHERE request_id=? AND approver_id=? AND status='waiting'""",
            (request_id, user_id)
        ).fetchone()
        if not approval:
            return {"error": f"#{request_id} 결재할 항목이 없습니다."}

        req = con.execute(
            "SELECT user_id, leave_type, start_date, end_date FROM leave_requests WHERE id=? AND status='pending'",
            (request_id,)
        ).fetchone()
        if not req:
            return {"error": "처리할 수 없는 상태입니다."}
        requester_id, leave_type, start_date, end_date = req

        now = datetime.now().isoformat()
        con.execute(
            "UPDATE leave_approvals SET status='rejected', comment=?, acted_at=? WHERE id=?",
            (comment, now, approval[0])
        )
        con.execute(
            "UPDATE leave_requests SET status='rejected', updated_at=? WHERE id=?",
            (now, request_id)
        )
        con.commit()

        actor = con.execute("SELECT nickname FROM users WHERE user_id=?", (user_id,)).fetchone()
        actor_name = actor[0] if actor else str(user_id)
        requester = con.execute("SELECT nickname, naver_works_id FROM users WHERE user_id=?", (requester_id,)).fetchone()
        requester_name = requester[0] if requester else str(requester_id)

        if requester and requester[1]:
            msg = (
                f"❌ 연차 반려\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📅 {start_date} ~ {end_date} ({leave_type})\n"
                f"👤 반려자: {actor_name}\n"
                f"💬 사유: {comment or '없음'}"
            )
            import asyncio
            try:
                asyncio.create_task(send_nw_dm(requester[1], msg))
            except Exception:
                pass

    add_log("연차 반려", "leave", str(request_id), requester_name, actor_name,
            f"#{request_id} {leave_type}, 사유: {comment or '없음'}")
    return {"success": True, "message": f"#{request_id} 반려 처리 완료. {requester_name}에게 알림을 보냈습니다."}


def bot_get_pending_approvals(naver_works_id: str) -> dict:
    """봇용 결재 대기 목록"""
    ensure_leave_tables()
    user_id = get_user_id_by_nw_id(naver_works_id)
    if not user_id:
        return {"error": "등록된 사용자가 아닙니다."}

    with get_connection() as con:
        rows = con.execute(
            """SELECT r.id, r.leave_type, r.start_date, r.end_date, r.hours_requested, r.reason,
                      u.nickname, u.department, a.step
               FROM leave_approvals a
               JOIN leave_requests r ON a.request_id = r.id
               JOIN users u ON r.user_id = u.user_id
               WHERE a.approver_id=? AND a.status='waiting' AND r.status='pending'
               ORDER BY r.created_at ASC""",
            (user_id,)
        ).fetchall()

    if not rows:
        return {"success": True, "count": 0, "items": [], "message": "결재 대기 중인 연차가 없습니다."}

    items = [
        {
            "request_id": r[0],
            "leave_type": r[1],
            "start_date": r[2],
            "end_date": r[3],
            "days": round(r[4] / HOURS_PER_DAY, 1),
            "reason": r[5] or "없음",
            "requester": r[6],
            "department": r[7],
            "step": r[8],
        }
        for r in rows
    ]
    return {"success": True, "count": len(items), "items": items}
