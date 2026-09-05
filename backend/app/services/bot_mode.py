"""
봇 모드 저장/명령 파서.
업무 저장 로직과 분리된 오케스트레이션 계층.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from logic.db import get_connection

MODE_IDLE = "idle"
MODE_JOURNAL = "journal"
MODE_REPAIR = "repair"
MODE_QUERY = "query"

MODE_LABELS = {
    MODE_IDLE: "기본상태",
    MODE_JOURNAL: "일지모드",
    MODE_REPAIR: "수선모드",
    MODE_QUERY: "조회모드",
}

_START_MAP = {
    "일지모드시작": MODE_JOURNAL,
    "일지시작": MODE_JOURNAL,
    "일지": MODE_JOURNAL,
    "작업일지": MODE_JOURNAL,
    "일지작성할래": MODE_JOURNAL,
    "일지쓸게": MODE_JOURNAL,
    "일지모드": MODE_JOURNAL,
    "수선모드시작": MODE_REPAIR,
    "수선시작": MODE_REPAIR,
    "수선": MODE_REPAIR,
    "수선모드": MODE_REPAIR,
    "수선할래": MODE_REPAIR,
    "수선할게": MODE_REPAIR,
    "조회모드시작": MODE_QUERY,
    "조회시작": MODE_QUERY,
    "조회": MODE_QUERY,
    "조회모드": MODE_QUERY,
    "조회할래": MODE_QUERY,
    "조회할게": MODE_QUERY,
    "기록좀볼래": MODE_QUERY,
}

_END_EXACT = frozenset(("모드종료", "종료", "끝"))
_STATUS_EXACT = frozenset(("현재모드",))
_HELP_EXACT = frozenset((
    "기능설명",
    "기능",
    "사용법알려줘",
    "사용법",
    "뭐할수있어",
    "뭐할수있어요",
    "뭘할수있어",
    "사용법알려주세요",
))
_HELP_PREFIXES = ("기능설명",)
_CMD_END = re.compile(r"^모드\s*종료$")
_CMD_STATUS = re.compile(r"^현재\s*모드$")
_CMD_HELP = re.compile(r"^기능\s*설명$")
_QUERY_CONTENT = re.compile(
    r"(몇\s*건|몇건|보여|목록|조회|얼마|비용|가격|단가|업체별|전체|오늘|어제|이번)"
)


def _norm(text: str) -> str:
    compact = re.sub(r"\s+", "", (text or "").strip())
    return re.sub(r"[?!.？！。,，]+$", "", compact)


def ensure_bot_mode_tables() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_modes (
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'idle',
                updated_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
            """
        )
        con.commit()


def mode_key(user_id: str, channel_id: Optional[str]) -> Tuple[str, str]:
    uid = (user_id or "").strip()
    cid = (channel_id or "").strip() or uid
    return uid, cid


def get_mode(user_id: str, channel_id: Optional[str] = None) -> str:
    ensure_bot_mode_tables()
    uid, cid = mode_key(user_id, channel_id)
    with get_connection() as con:
        row = con.execute(
            "SELECT mode FROM bot_modes WHERE user_id = ? AND channel_id = ?",
            (uid, cid),
        ).fetchone()
    mode = (row[0] if row else MODE_IDLE) or MODE_IDLE
    return mode if mode in MODE_LABELS else MODE_IDLE


def set_mode(user_id: str, channel_id: Optional[str], mode: str) -> str:
    ensure_bot_mode_tables()
    uid, cid = mode_key(user_id, channel_id)
    resolved = mode if mode in MODE_LABELS else MODE_IDLE
    with get_connection() as con:
        con.execute(
            """
            INSERT INTO bot_modes (user_id, channel_id, mode, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, channel_id) DO UPDATE SET
                mode = excluded.mode,
                updated_at = excluded.updated_at
            """,
            (uid, cid, resolved, datetime.now().isoformat()),
        )
        con.commit()
    return resolved


def mode_label(mode: Optional[str] = None, user_id: str = "", channel_id: Optional[str] = None) -> str:
    current = mode if mode in MODE_LABELS else get_mode(user_id, channel_id)
    return MODE_LABELS[current]


def with_mode_prefix(text: str, mode: Optional[str] = None, user_id: str = "", channel_id: Optional[str] = None) -> str:
    body = (text or "").strip()
    prefix = f"[{mode_label(mode, user_id, channel_id)}]"
    if body.startswith(prefix):
        return body
    if not body:
        return prefix
    return f"{prefix} {body}"


def looks_like_work_sentence(text: str) -> bool:
    """모드 단어가 들어 있어도 업무 문장이면 모드 전환하지 않는다."""
    compact = _norm(text)
    if not compact or compact in _START_MAP or compact in _END_EXACT or compact in _HELP_EXACT:
        return False
    return bool(_QUERY_CONTENT.search(text or "")) or bool(_QUERY_CONTENT.search(compact))


def parse_mode_command(text: str) -> Optional[dict]:
    """짧고 명확한 모드 명령만 코드가 확정한다. 업무 문장의 단어 포함은 무시한다."""
    raw = (text or "").strip()
    compact = _norm(raw)
    if not compact:
        return None
    if compact in _START_MAP:
        return {"action": "start", "mode": _START_MAP[compact]}
    if compact in _END_EXACT or _CMD_END.match(raw):
        return {"action": "end"}
    if compact in _STATUS_EXACT or _CMD_STATUS.match(raw):
        return {"action": "status"}
    if compact in _HELP_EXACT or _CMD_HELP.match(raw) or any(
        compact.startswith(prefix) and len(compact) <= len(prefix) + 4 for prefix in _HELP_PREFIXES
    ):
        return {"action": "help"}
    return None


def idle_guide() -> str:
    return (
        "사용할 모드를 선택해주세요.\n"
        "• 일지모드 시작\n"
        "• 수선모드 시작\n"
        "• 조회모드 시작\n"
        "• 기능설명"
    )


def mode_feature_guide() -> str:
    return (
        "모드별 기능 안내\n"
        "\n"
        "• 일지모드\n"
        "  물류 작업일지를 말로 입력·수정·삭제합니다.\n"
        "  예: 틸리언 하차 3만원 / 방금거 삭제 / 5만원으로 바꿔\n"
        "  시작: 일지모드 시작\n"
        "\n"
        "• 수선모드\n"
        "  수선일지를 사진과 말로 남깁니다. 바코드와 사진 2장 이상.\n"
        "  예: 구멍 바느질 1500원 / 직전내용수정 / 금액 2천원으로\n"
        "  시작: 수선모드 시작\n"
        "\n"
        "• 조회모드\n"
        "  작업일지 검색·목록·건수·수량·금액\n"
        "  수선일지 검색·목록·건수·수량·금액\n"
        "  업체·작업·작업자별 묶음\n"
        "  작업 단가 이력, 수선 가격\n"
        "  조회만 합니다. 조회모드는 저장·수정·삭제를 할 수 없습니다.\n"
        "  예: 오늘 수선작업 몇 건 / 봉제 몇 건 / 방금 저장된 수선항목\n"
        "  시작: 조회모드 시작\n"
        "\n"
        "공통: 모드 종료 / 현재 모드 / 기능설명\n"
        "엑셀 파일은 모드와 관계없이 작업일지 일괄 등록에 씁니다."
    )


def decide_bot_route(user_id: str, channel_id: Optional[str], text: str) -> str:
    if parse_mode_command(text):
        return "mode_command"
    mode = get_mode(user_id, channel_id)
    if mode == MODE_IDLE:
        return "idle"
    if mode == MODE_REPAIR:
        return "repair"
    if mode == MODE_QUERY:
        return "query"
    return "journal"


def should_accept_repair_photo(user_id: str, channel_id: Optional[str]) -> bool:
    return get_mode(user_id, channel_id) == MODE_REPAIR


def apply_mode_command(user_id: str, channel_id: Optional[str], command: dict) -> str:
    """모드 변경. 저장 완료 데이터와 domain별 last_saved는 지우지 않는다."""
    from backend.app.services.conversation_state import get_conversation_manager
    from backend.app.services.repair_bot import clear_photo_inbox

    uid, cid = mode_key(user_id, channel_id)
    action = command.get("action")
    mgr = get_conversation_manager()
    if action == "start":
        set_mode(uid, cid, command["mode"])
        mgr.clear_state(uid, cid)
        mgr.clear_query_context(uid, cid)
        clear_photo_inbox(uid, cid)
        return f"{MODE_LABELS[command['mode']]}를 시작했어요."
    if action == "end":
        current = get_mode(uid, cid)
        state = mgr.get_state(uid, cid) or {}
        had_draft = bool(state.get("pending_data")) and not state.get("expired")
        set_mode(uid, cid, MODE_IDLE)
        mgr.clear_state(uid, cid)
        mgr.clear_query_context(uid, cid)
        clear_photo_inbox(uid, cid)
        if current == MODE_IDLE and not had_draft:
            return "이미 기본상태입니다. " + idle_guide()
        return "모드를 종료했어요. " + idle_guide()
    if action == "help":
        return mode_feature_guide()
    return f"지금은 {mode_label(user_id=uid, channel_id=cid)}입니다."
