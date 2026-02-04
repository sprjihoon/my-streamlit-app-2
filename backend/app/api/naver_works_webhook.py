"""
네이버 웍스 Bot Webhook API
───────────────────────────────────────
네이버 웍스에서 보내는 메시지를 수신하고 처리합니다.
하이브리드 방식: 자동 저장 + 취소 가능 + 중복 체크
"""

import os
import json
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

from backend.app.services import (
    get_naver_works_client,
    get_ai_parser,
    get_conversation_manager,
)
from logic.db import get_connection

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/naver-works", tags=["naver-works"])

# 디버그 로그 저장 (최근 50개)
_debug_logs: List[Dict[str, Any]] = []
MAX_DEBUG_LOGS = 50

def add_debug_log(event: str, data: Any = None, error: str = None):
    """디버그 로그 추가"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "data": data,
        "error": error
    }
    _debug_logs.append(log_entry)
    if len(_debug_logs) > MAX_DEBUG_LOGS:
        _debug_logs.pop(0)
    
    # 콘솔에도 출력
    if error:
        logger.error(f"[{event}] {error}")
    else:
        logger.info(f"[{event}] {data}")

# NOTE: 최근 저장 정보는 DB에서 직접 조회 (multi-worker 환경 지원)
# get_user_recent_log(user_id, within_seconds=30) 사용


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class MessageContent(BaseModel):
    """메시지 내용"""
    type: str
    text: Optional[str] = None
    postback: Optional[str] = None


class MessageSource(BaseModel):
    """메시지 발신자"""
    userId: str
    channelId: Optional[str] = None
    domainId: Optional[int] = None


class WebhookEvent(BaseModel):
    """Webhook 이벤트"""
    type: str
    source: MessageSource
    issuedTime: Optional[str] = None
    content: Optional[MessageContent] = None


# ─────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────

def save_work_log(data: Dict[str, Any], user_id: str, user_name: str = None) -> int:
    """
    작업일지를 DB에 저장
    
    Args:
        data: 파싱된 작업 데이터
        user_id: 네이버 웍스 사용자 ID
        user_name: 작성자 이름
    
    Returns:
        저장된 레코드 ID
    """
    vendor = data.get("vendor", "")
    work_type = data.get("work_type", "")
    qty = data.get("qty", 1)
    unit_price = data.get("unit_price", 0)
    total = qty * unit_price
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    remark = data.get("remark", "")
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        # 새 컬럼 추가 확인
        existing_cols = [c[1] for c in con.execute("PRAGMA table_info(work_log);")]
        
        if "작성자" in existing_cols:
            cursor = con.execute(
                """
                INSERT INTO work_log (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date, vendor, work_type, unit_price, qty, total, remark, user_name, 저장시간, "bot", user_id)
            )
        else:
            cursor = con.execute(
                """
                INSERT INTO work_log (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (date, vendor, work_type, unit_price, qty, total, remark)
            )
        con.commit()
        record_id = cursor.lastrowid
        
        # 생성 이력 기록
        log_work_history(
            record_id, 
            "create", 
            {
                "날짜": date,
                "업체명": vendor,
                "분류": work_type,
                "단가": unit_price,
                "수량": qty,
                "합계": total,
                "작성자": user_name,
            },
            변경자=user_name,
            변경사유="봇 입력",
            works_user_id=user_id
        )
        
        return record_id


def check_duplicate(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    중복 작업일지 확인
    
    Returns:
        중복 레코드가 있으면 해당 레코드 정보, 없으면 None
    """
    vendor = data.get("vendor", "")
    work_type = data.get("work_type", "")
    qty = data.get("qty", 1)
    unit_price = data.get("unit_price", 0)
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    
    with get_connection() as con:
        row = con.execute(
            """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간 
               FROM work_log 
               WHERE 날짜 = ? AND 업체명 = ? AND 분류 = ? AND 수량 = ? AND 단가 = ?
               ORDER BY id DESC LIMIT 1""",
            (date, vendor, work_type, qty, unit_price)
        ).fetchone()
        
        if row:
            return {
                "id": row[0],
                "날짜": row[1],
                "업체명": row[2],
                "분류": row[3],
                "수량": row[4],
                "단가": row[5],
                "합계": row[6],
                "저장시간": str(row[7]) if row[7] else None,
            }
        return None


def log_work_history(
    log_id: int,
    action: str,
    log_data: Dict[str, Any],
    변경자: str = None,
    변경사유: str = None,
    works_user_id: str = None
):
    """작업일지 변경 이력 기록"""
    with get_connection() as con:
        con.execute(
            """INSERT INTO work_log_history 
               (log_id, action, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 변경자, 변경시간, 변경사유, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                log_id,
                action,
                log_data.get("날짜") or log_data.get("date"),
                log_data.get("업체명") or log_data.get("vendor"),
                log_data.get("분류") or log_data.get("work_type"),
                log_data.get("단가") or log_data.get("unit_price"),
                log_data.get("수량") or log_data.get("qty"),
                log_data.get("합계") or (log_data.get("수량", 1) * log_data.get("단가", 0)),
                log_data.get("작성자"),
                변경자,
                datetime.now().isoformat(),
                변경사유,
                works_user_id
            )
        )
        con.commit()


def delete_work_log(log_id: int, 변경자: str = None, works_user_id: str = None) -> bool:
    """작업일지 삭제 (이력 로그 남김)"""
    with get_connection() as con:
        # 삭제 전 데이터 조회
        row = con.execute(
            "SELECT 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자 FROM work_log WHERE id = ?",
            (log_id,)
        ).fetchone()
        
        if row:
            log_data = {
                "날짜": row[0],
                "업체명": row[1],
                "분류": row[2],
                "단가": row[3],
                "수량": row[4],
                "합계": row[5],
                "작성자": row[6],
            }
            
            # 삭제 이력 기록
            log_work_history(log_id, "delete", log_data, 변경자, "삭제", works_user_id)
        
        con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
        con.commit()
        return True


def get_user_recent_log(user_id: str, within_seconds: int = None) -> Optional[Dict[str, Any]]:
    """
    사용자의 가장 최근 작업일지 조회
    
    Args:
        user_id: 사용자 ID
        within_seconds: 지정 시 해당 초 내에 저장된 것만 반환 (취소 가능 시간 체크용)
    """
    with get_connection() as con:
        row = con.execute(
            """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log 
               WHERE works_user_id = ?
               ORDER BY id DESC LIMIT 1""",
            (user_id,)
        ).fetchone()
        
        if row:
            result = {
                "id": row[0],
                "날짜": row[1],
                "업체명": row[2],
                "분류": row[3],
                "수량": row[4],
                "단가": row[5],
                "합계": row[6],
                "저장시간": str(row[7]) if row[7] else None,
                "작성자": row[8],
            }
            
            # 시간 체크 (within_seconds가 지정된 경우)
            if within_seconds and row[7]:
                try:
                    saved_time = datetime.fromisoformat(str(row[7]))
                    elapsed = (datetime.now() - saved_time).total_seconds()
                    if elapsed > within_seconds:
                        return None  # 시간 초과
                except:
                    pass
            
            return result
        return None


def get_today_work_logs(user_id: str = None) -> List[Dict[str, Any]]:
    """오늘 작업일지 목록 조회"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    with get_connection() as con:
        if user_id:
            rows = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
                   FROM work_log 
                   WHERE 날짜 = ? AND works_user_id = ?
                   ORDER BY id DESC""",
                (today, user_id)
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
                   FROM work_log 
                   WHERE 날짜 = ?
                   ORDER BY id DESC""",
                (today,)
            ).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "날짜": row[1],
                "업체명": row[2],
                "분류": row[3],
                "수량": row[4],
                "단가": row[5],
                "합계": row[6],
                "저장시간": str(row[7]) if row[7] else None,
                "작성자": row[8],
            })
        return result


def get_work_logs_by_period(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """기간별 작업일지 목록 조회"""
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log 
               WHERE 날짜 >= ? AND 날짜 <= ?
               ORDER BY 날짜 DESC, id DESC""",
            (start_date, end_date)
        ).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "날짜": row[1],
                "업체명": row[2],
                "분류": row[3],
                "수량": row[4],
                "단가": row[5],
                "합계": row[6],
                "저장시간": str(row[7]) if row[7] else None,
                "작성자": row[8],
            })
        return result


def is_vendor_registered(vendor_name: str) -> bool:
    """업체명이 등록된 리스트에 있는지 확인"""
    if not vendor_name:
        return False
    
    with get_connection() as con:
        # vendors 테이블에서 확인
        row = con.execute(
            """SELECT vendor FROM vendors 
               WHERE vendor = ? OR name = ?
               LIMIT 1""",
            (vendor_name, vendor_name)
        ).fetchone()
        
        if row:
            return True
        
        # aliases 테이블에서도 확인
        alias_row = con.execute(
            """SELECT vendor FROM aliases 
               WHERE alias = ? OR vendor = ?
               LIMIT 1""",
            (vendor_name, vendor_name)
        ).fetchone()
        
        return bool(alias_row)


def get_registered_vendors() -> list:
    """등록된 업체 목록 조회"""
    with get_connection() as con:
        rows = con.execute(
            "SELECT DISTINCT vendor FROM vendors WHERE active != 'NO' OR active IS NULL"
        ).fetchall()
        return [row[0] for row in rows if row[0]]


def search_work_logs(
    vendor: str = None,
    work_type: str = None,
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    price: int = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """조건부 작업일지 검색"""
    conditions = []
    params = []
    
    if vendor:
        conditions.append("업체명 LIKE ?")
        params.append(f"%{vendor}%")
    if work_type:
        conditions.append("분류 LIKE ?")
        params.append(f"%{work_type}%")
    if date:
        conditions.append("날짜 = ?")
        params.append(date)
    elif start_date and end_date:
        conditions.append("날짜 >= ? AND 날짜 <= ?")
        params.extend([start_date, end_date])
    elif start_date:
        conditions.append("날짜 >= ?")
        params.append(start_date)
    elif end_date:
        conditions.append("날짜 <= ?")
        params.append(end_date)
    if price:
        # 10% 오차 허용
        conditions.append("합계 BETWEEN ? AND ?")
        params.extend([int(price * 0.9), int(price * 1.1)])
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_connection() as con:
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log 
               WHERE {where_clause}
               ORDER BY 날짜 DESC, id DESC
               LIMIT ?""",
            params + [limit]
        ).fetchall()
        
        return [
            {"id": r[0], "날짜": r[1], "업체명": r[2], "분류": r[3], "수량": r[4], 
             "단가": r[5], "합계": r[6], "저장시간": str(r[7]) if r[7] else None, "작성자": r[8]}
            for r in rows
        ]


def get_work_log_stats(
    start_date: str = None,
    end_date: str = None,
    vendor: str = None
) -> Dict[str, Any]:
    """작업일지 통계"""
    conditions = []
    params = []
    
    if start_date:
        conditions.append("날짜 >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("날짜 <= ?")
        params.append(end_date)
    if vendor:
        conditions.append("업체명 LIKE ?")
        params.append(f"%{vendor}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_connection() as con:
        # 총 합계
        total_row = con.execute(
            f"SELECT COUNT(*), SUM(합계) FROM work_log WHERE {where_clause}",
            params
        ).fetchone()
        
        total_count = total_row[0] or 0
        total_amount = total_row[1] or 0
        
        # 업체별 통계
        vendor_stats = con.execute(
            f"""SELECT 업체명, COUNT(*), SUM(합계)
               FROM work_log WHERE {where_clause}
               GROUP BY 업체명
               ORDER BY SUM(합계) DESC""",
            params
        ).fetchall()
        
        # 작업종류별 통계
        work_type_stats = con.execute(
            f"""SELECT 분류, COUNT(*), SUM(합계)
               FROM work_log WHERE {where_clause}
               GROUP BY 분류
               ORDER BY COUNT(*) DESC""",
            params
        ).fetchall()
        
        return {
            "total_count": total_count,
            "total_amount": total_amount,
            "by_vendor": [{"vendor": v[0], "count": v[1], "amount": v[2]} for v in vendor_stats],
            "by_work_type": [{"work_type": w[0], "count": w[1], "amount": w[2]} for w in work_type_stats]
        }


def find_specific_log(
    vendor: str = None,
    work_type: str = None,
    date: str = None,
    price: int = None,
    user_id: str = None
) -> Optional[Dict[str, Any]]:
    """특정 조건의 작업일지 1건 찾기 (가장 최근)"""
    conditions = []
    params = []
    
    if vendor:
        conditions.append("업체명 LIKE ?")
        params.append(f"%{vendor}%")
    if work_type:
        conditions.append("분류 LIKE ?")
        params.append(f"%{work_type}%")
    if date:
        conditions.append("날짜 = ?")
        params.append(date)
    if price:
        conditions.append("합계 BETWEEN ? AND ?")
        params.extend([int(price * 0.9), int(price * 1.1)])
    if user_id:
        conditions.append("works_user_id = ?")
        params.append(user_id)
    
    if not conditions:
        return None
    
    where_clause = " AND ".join(conditions)
    
    with get_connection() as con:
        row = con.execute(
            f"""SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log 
               WHERE {where_clause}
               ORDER BY id DESC
               LIMIT 1""",
            params
        ).fetchone()
        
        if row:
            return {
                "id": row[0], "날짜": row[1], "업체명": row[2], "분류": row[3],
                "수량": row[4], "단가": row[5], "합계": row[6],
                "저장시간": str(row[7]) if row[7] else None, "작성자": row[8]
            }
        return None


def get_price_history(vendor: str, work_type: str, limit: int = 20) -> List[int]:
    """업체+작업종류별 과거 단가 이력 조회 (이상치 탐지용)"""
    with get_connection() as con:
        rows = con.execute(
            """SELECT 단가 FROM work_log 
               WHERE 업체명 = ? AND 분류 = ? AND 단가 > 0
               ORDER BY id DESC LIMIT ?""",
            (vendor, work_type, limit)
        ).fetchall()
        return [r[0] for r in rows if r[0]]


def add_memo_to_log(log_id: int, memo: str) -> bool:
    """작업일지에 메모(비고) 추가"""
    with get_connection() as con:
        # 기존 비고 가져오기
        existing = con.execute("SELECT 비고1 FROM work_log WHERE id = ?", (log_id,)).fetchone()
        if existing:
            old_memo = existing[0] or ""
            new_memo = f"{old_memo} [{memo}]" if old_memo else memo
            con.execute("UPDATE work_log SET 비고1 = ? WHERE id = ?", (new_memo, log_id))
            con.commit()
            return True
        return False


def bulk_update_logs(
    conditions: Dict[str, Any],
    updates: Dict[str, Any],
    user_id: str = None
) -> int:
    """조건에 맞는 여러 건 일괄 수정"""
    where_parts = []
    where_params = []
    
    if conditions.get("vendor"):
        where_parts.append("업체명 LIKE ?")
        where_params.append(f"%{conditions['vendor']}%")
    if conditions.get("work_type"):
        where_parts.append("분류 LIKE ?")
        where_params.append(f"%{conditions['work_type']}%")
    if conditions.get("date"):
        where_parts.append("날짜 = ?")
        where_params.append(conditions["date"])
    if conditions.get("start_date"):
        where_parts.append("날짜 >= ?")
        where_params.append(conditions["start_date"])
    if conditions.get("end_date"):
        where_parts.append("날짜 <= ?")
        where_params.append(conditions["end_date"])
    if user_id:
        where_parts.append("works_user_id = ?")
        where_params.append(user_id)
    
    if not where_parts:
        return 0
    
    set_parts = []
    set_params = []
    
    if updates.get("unit_price") is not None:
        set_parts.append("단가 = ?")
        set_params.append(updates["unit_price"])
        # 합계도 자동 업데이트
        set_parts.append("합계 = 수량 * ?")
        set_params.append(updates["unit_price"])
    
    if not set_parts:
        return 0
    
    with get_connection() as con:
        cursor = con.execute(
            f"UPDATE work_log SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}",
            set_params + where_params
        )
        con.commit()
        return cursor.rowcount


def copy_work_logs(
    source_conditions: Dict[str, Any],
    target_date: str
) -> List[int]:
    """조건에 맞는 작업일지를 다른 날짜로 복사"""
    where_parts = []
    params = []
    
    if source_conditions.get("date"):
        where_parts.append("날짜 = ?")
        params.append(source_conditions["date"])
    if source_conditions.get("start_date") and source_conditions.get("end_date"):
        where_parts.append("날짜 >= ? AND 날짜 <= ?")
        params.extend([source_conditions["start_date"], source_conditions["end_date"]])
    if source_conditions.get("vendor"):
        where_parts.append("업체명 LIKE ?")
        params.append(f"%{source_conditions['vendor']}%")
    if source_conditions.get("work_type"):
        where_parts.append("분류 LIKE ?")
        params.append(f"%{source_conditions['work_type']}%")
    
    if not where_parts:
        return []
    
    new_ids = []
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        rows = con.execute(
            f"""SELECT 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 출처, works_user_id
               FROM work_log WHERE {' AND '.join(where_parts)}""",
            params
        ).fetchall()
        
        for row in rows:
            cursor = con.execute(
                """INSERT INTO work_log (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (target_date, row[0], row[1], row[2], row[3], row[4], 
                 f"{row[5] or ''} [복사됨]", row[6], 저장시간, "bot_copy", row[8])
            )
            new_ids.append(cursor.lastrowid)
        
        con.commit()
    
    return new_ids


def get_undo_history(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """사용자의 최근 변경 이력 조회"""
    with get_connection() as con:
        # 테이블 컬럼 확인
        cols = [c[1] for c in con.execute("PRAGMA table_info(work_log_history);")]
        
        # action 컬럼 기반 쿼리 (실제 테이블 구조에 맞춤)
        rows = con.execute(
            """SELECT id, action, 업체명, 분류, 합계, 변경자, 변경시간, log_id
               FROM work_log_history 
               WHERE works_user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
        
        result = []
        for r in rows:
            # before 정보를 JSON 형태로 구성
            before_data = {
                "업체명": r[2],
                "분류": r[3],
                "합계": r[4]
            }
            result.append({
                "id": r[0],
                "type": r[1].upper() if r[1] else "UNKNOWN",  # create->INSERT, delete->DELETE
                "before": json.dumps(before_data, ensure_ascii=False) if r[1] == "delete" else None,
                "after": json.dumps(before_data, ensure_ascii=False) if r[1] == "create" else None,
                "user": r[5],
                "time": r[6],
                "log_id": r[7]
            })
        return result


def get_dashboard_url() -> str:
    """대시보드 URL 반환"""
    import os
    return os.getenv("FRONTEND_URL", "https://my-streamlit-app-2.vercel.app")


async def send_welcome_message(channel_id: str):
    """봇 초대 시 환영 메시지 전송"""
    try:
        nw_client = get_naver_works_client()
        
        welcome_msg = (
            "👋 안녕하세요! 작업일지봇이에요!\n\n"
            "저를 초대해주셔서 감사합니다 😊\n\n"
            "📝 **사용법**\n"
            "• 작업 입력: 'A업체 1톤하차 50000원'\n"
            "• 취소: '취소' 또는 '방금거 취소해줘'\n"
            "• 수정: '방금거 수정해줘'\n"
            "• 대화모드: '대화모드' (GPT와 자유 대화)\n"
            "• 도움말: '도움말'\n\n"
            "무엇이든 물어보세요! 💬"
        )
        
        await nw_client.send_text_message(channel_id, welcome_msg, "group")
        add_debug_log("welcome_message_sent", {"channel_id": channel_id})
        
    except Exception as e:
        add_debug_log("welcome_message_error", error=str(e))


def validate_work_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    작업 데이터 유효성 검증
    
    Returns:
        {
            "valid": True/False,
            "warnings": ["경고 메시지들"],
            "errors": ["에러 메시지들"]
        }
    """
    warnings = []
    errors = []
    
    vendor = data.get("vendor", "")
    work_type = data.get("work_type", "")
    qty = data.get("qty", 1)
    unit_price = data.get("unit_price", 0)
    
    # 필수 필드 체크
    if not vendor:
        errors.append("업체명이 없습니다.")
    if not work_type:
        errors.append("작업 종류가 없습니다.")
    
    # 업체명 등록 여부 확인
    if vendor and not is_vendor_registered(vendor):
        warnings.append(f"'{vendor}'은(는) 등록되지 않은 업체입니다.")
    
    # 단가 체크
    if unit_price == 0:
        warnings.append("단가가 0원입니다.")
    elif unit_price < 0:
        errors.append("단가가 음수입니다.")
    elif unit_price > 10000000:  # 천만원 초과
        warnings.append(f"단가가 {unit_price:,}원으로 매우 높습니다.")
    
    # 수량 체크
    if qty <= 0:
        errors.append("수량이 0 이하입니다.")
    elif qty > 10000:  # 만개 초과
        warnings.append(f"수량이 {qty:,}개로 매우 많습니다.")
    
    # 합계 체크
    total = qty * unit_price
    if total > 100000000:  # 1억 초과
        warnings.append(f"합계가 {total:,}원으로 매우 높습니다.")
    
    return {
        "valid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors
    }


async def process_message(
    user_id: str,
    channel_id: str,
    text: str,
    channel_type: str = "group",
    user_name: str = None
):
    """
    메시지 처리 메인 로직 (하이브리드 방식)
    
    Args:
        user_id: 사용자 ID
        channel_id: 채널 ID
        text: 메시지 텍스트
        channel_type: 채널 타입
        user_name: 사용자 이름
    """
    add_debug_log("process_message_start", {
        "user_id": user_id,
        "channel_id": channel_id,
        "text": text,
        "channel_type": channel_type
    })
    
    try:
        nw_client = get_naver_works_client()
        add_debug_log("nw_client_loaded", {"private_key_loaded": bool(nw_client.private_key)})
    except Exception as e:
        add_debug_log("nw_client_error", error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
        return
    
    # 사용자 이름 조회 (user_name이 없는 경우)
    if not user_name:
        try:
            user_name = await nw_client.get_user_name(user_id)
            add_debug_log("user_name_fetched", {"user_id": user_id, "user_name": user_name})
        except Exception as e:
            add_debug_log("user_name_fetch_error", error=str(e))
            user_name = None
    
    try:
        ai_parser = get_ai_parser()
        add_debug_log("ai_parser_loaded", {"model": ai_parser.model})
    except Exception as e:
        add_debug_log("ai_parser_error", error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
        # AI 파서 실패 시에도 에러 메시지 전송 시도
        try:
            await nw_client.send_text_message(
                channel_id,
                f"❌ AI 파서 초기화 오류: {str(e)}",
                channel_type
            )
        except:
            pass
        return
    
    conv_manager = get_conversation_manager()
    
    text_lower = text.strip().lower()
    existing_state = conv_manager.get_state(user_id)
    has_pending_state = existing_state is not None and existing_state.get("last_question") is not None
    
    # ═══════════════════════════════════════════════════════════════════
    # 1단계: 진행 중인 대화 상태 확인 (우선 처리)
    # ═══════════════════════════════════════════════════════════════════
    
    # 취소 확인 대기 중
    if existing_state and existing_state.get("last_question") == "🗑️ 취소 확인":
        intent_context = {
            "last_question": "삭제할까요? (예/아니오)",
            "options": ["예: 삭제", "아니오: 유지"],
            "pending_data": existing_state.get("pending_data", {})
        }
        intent_result = await ai_parser.parse_intent(text, intent_context)
        add_debug_log("cancel_confirm_intent", data=intent_result)
        
        if intent_result.get("intent") == "confirm_yes":
            pending_data = existing_state.get("pending_data", {})
            log_id = pending_data.get("log_id")
            log_info = pending_data.get("log_info", {})
            
            if log_id:
                delete_work_log(log_id, 변경자=user_name, works_user_id=user_id)
                conv_manager.clear_state(user_id)
                await nw_client.send_text_message(
                    channel_id,
                    f"🚫 삭제완료!\n• 업체: {log_info.get('업체명', '-')}\n• 작업: {log_info.get('분류', '-')}\n• 금액: {log_info.get('합계', 0):,}원",
                    channel_type
                )
            return
        elif intent_result.get("intent") == "confirm_no":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "✅ 취소가 취소되었습니다.", channel_type)
            return
    
    # 경고 확인 대기 중
    if existing_state and existing_state.get("last_question", "").startswith("⚠️"):
        intent_context = {
            "last_question": "경고가 있습니다. 그래도 저장할까요?",
            "options": ["예: 저장", "아니오: 취소"],
            "pending_data": existing_state.get("pending_data", {})
        }
        intent_result = await ai_parser.parse_intent(text, intent_context)
        add_debug_log("warning_confirm_intent", data=intent_result)
        
        if intent_result.get("intent") == "confirm_yes":
            data = existing_state.get("pending_data", {})
            try:
                record_id = save_work_log(data, user_id, user_name)
                conv_manager.clear_state(user_id)
                response_msg = generate_success_message(data, record_id)
                await nw_client.send_text_message(channel_id, response_msg, channel_type)
            except Exception as e:
                await nw_client.send_text_message(channel_id, f"❌ 저장 오류: {str(e)}", channel_type)
            return
        elif intent_result.get("intent") == "confirm_no":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "🚫 저장하지 않았습니다.", channel_type)
            return
    
    # 일괄 수정 확인 대기 중
    if existing_state and existing_state.get("last_question") == "⚠️ 일괄 수정 확인":
        intent_context = {
            "last_question": "일괄 수정할까요?",
            "options": ["예: 수정", "아니오: 취소"],
            "pending_data": existing_state.get("pending_data", {})
        }
        intent_result = await ai_parser.parse_intent(text, intent_context)
        
        if intent_result.get("intent") == "confirm_yes":
            pending = existing_state.get("pending_data", {})
            conditions = pending.get("conditions", {})
            new_price = pending.get("new_price")
            
            updated = bulk_update_logs(conditions, {"unit_price": new_price}, user_id)
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(
                channel_id, 
                f"✅ {updated}건 일괄 수정 완료!\n단가: {new_price:,}원",
                channel_type
            )
            return
        elif intent_result.get("intent") == "confirm_no":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "🚫 일괄 수정을 취소했습니다.", channel_type)
            return
    
    # 복사 확인 대기 중
    if existing_state and existing_state.get("last_question") == "📋 복사 확인":
        intent_context = {
            "last_question": "복사할까요?",
            "options": ["예: 복사", "아니오: 취소"],
            "pending_data": existing_state.get("pending_data", {})
        }
        intent_result = await ai_parser.parse_intent(text, intent_context)
        
        if intent_result.get("intent") == "confirm_yes":
            pending = existing_state.get("pending_data", {})
            source = pending.get("source", {})
            target_date = pending.get("target_date")
            
            new_ids = copy_work_logs(source, target_date)
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(
                channel_id, 
                f"✅ {len(new_ids)}건 복사 완료!\n대상 날짜: {target_date}",
                channel_type
            )
            return
        elif intent_result.get("intent") == "confirm_no":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "🚫 복사를 취소했습니다.", channel_type)
            return
    
    # 되돌리기 선택 대기 중
    if existing_state and existing_state.get("last_question") == "🔄 되돌리기 선택":
        import re
        # 번호 추출 (1, 1번, 1번 되돌려줘 등)
        num_match = re.search(r'(\d+)', text)
        
        if num_match:
            selected_num = int(num_match.group(1))
            history = existing_state.get("pending_data", {}).get("undo_history", [])
            
            if 1 <= selected_num <= len(history):
                item = history[selected_num - 1]
                change_type = item.get("type", "")
                log_id = item.get("log_id")
                before_data = item.get("before")
                after_data = item.get("after")
                
                try:
                    if change_type == "INSERT" and log_id:
                        # 추가된 것 삭제
                        delete_work_log(log_id, 변경자=user_name, works_user_id=user_id)
                        conv_manager.clear_state(user_id)
                        await nw_client.send_text_message(channel_id, f"✅ 되돌리기 완료 (추가된 데이터 삭제됨)", channel_type)
                    elif change_type == "DELETE" and before_data:
                        # 삭제된 것 복구
                        import json
                        try:
                            restore_data = json.loads(before_data) if isinstance(before_data, str) else before_data
                            record_id = save_work_log(restore_data, user_id, user_name)
                            conv_manager.clear_state(user_id)
                            await nw_client.send_text_message(channel_id, f"✅ 되돌리기 완료 (삭제된 데이터 복구됨)\nID: {record_id}", channel_type)
                        except json.JSONDecodeError:
                            await nw_client.send_text_message(channel_id, "❌ 복구 데이터 파싱 오류", channel_type)
                    elif change_type == "UPDATE" and log_id and before_data:
                        # 수정 전으로 되돌리기
                        import json
                        try:
                            restore_data = json.loads(before_data) if isinstance(before_data, str) else before_data
                            # 기존 레코드 업데이트
                            with get_connection() as con:
                                con.execute(
                                    """UPDATE work_log 
                                       SET 업체명=?, 분류=?, 수량=?, 단가=?, 합계=?, 비고1=?
                                       WHERE id=?""",
                                    (restore_data.get("업체명"), restore_data.get("분류"),
                                     restore_data.get("수량", 1), restore_data.get("단가", 0),
                                     restore_data.get("합계", 0), restore_data.get("비고1", ""), log_id)
                                )
                                con.commit()
                            conv_manager.clear_state(user_id)
                            await nw_client.send_text_message(channel_id, f"✅ 되돌리기 완료 (수정 전으로 복구됨)", channel_type)
                        except json.JSONDecodeError:
                            await nw_client.send_text_message(channel_id, "❌ 복구 데이터 파싱 오류", channel_type)
                    else:
                        await nw_client.send_text_message(channel_id, "❌ 이 항목은 되돌릴 수 없습니다.", channel_type)
                except Exception as e:
                    add_debug_log("undo_error", error=str(e))
                    await nw_client.send_text_message(channel_id, f"❌ 되돌리기 오류: {str(e)}", channel_type)
                return
            else:
                await nw_client.send_text_message(channel_id, f"❓ 1~{len(history)} 사이 번호를 입력해주세요.", channel_type)
                return
        
        # 취소 처리
        if "취소" in text or "그만" in text:
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "✅ 되돌리기를 취소했습니다.", channel_type)
            return
    
    # ═══════════════════════════════════════════════════════════════════
    # 2단계: AI로 메시지 의도 분류
    # ═══════════════════════════════════════════════════════════════════
    # 현재 모드 확인
    current_mode = "work"  # 기본값
    if existing_state:
        pending_data = existing_state.get("pending_data", {})
        if pending_data.get("chat_mode"):
            current_mode = "chat"
    
    message_class = await ai_parser.classify_message(text, user_name, has_pending_state, current_mode)
    add_debug_log("message_classified", data={**message_class, "current_mode": current_mode})
    
    intent = message_class.get("intent", "chat")
    intent_data = message_class.get("data", {})
    confidence = message_class.get("confidence", 0.0)
    
    # ═══════════════════════════════════════════════════════════════════
    # 대화모드 체크 (최우선 처리!)
    # ═══════════════════════════════════════════════════════════════════
    is_chat_mode = (current_mode == "chat")
    
    if is_chat_mode:
        add_debug_log("chat_mode_active", {"intent": intent, "text": text})
        
        # 대화모드에서 허용되는 명령 (모드 전환만)
        if intent == "work_mode_start":
            conv_manager.clear_state(user_id)
            conv_manager.set_state(user_id=user_id, channel_id=channel_id, pending_data={"work_mode": True}, missing=[], last_question="📋 작업모드")
            await nw_client.send_text_message(
                channel_id,
                "📋 작업모드 시작!\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ 입력: 틸리언 1톤하차 3만원\n"
                "📊 조회: 오늘/이번주 작업 정리해줘\n"
                "🔍 검색: 틸리언 작업 보여줘\n"
                "📈 분석: 이번달 통계, 지난주 비교\n\n"
                "💬 자유 대화는 '대화모드'를 입력하세요",
                channel_type
            )
            return
        
        if intent == "chat_mode_end":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "💬 대화모드가 종료되었습니다.\n📋 '작업모드'로 작업을 시작하세요!", channel_type)
            return
        
        # 그 외 모든 메시지 → GPT 대화 또는 웹검색으로 처리
        add_debug_log("chat_mode_gpt_response", {"text": text})
        try:
            # 웹검색 키워드 감지
            web_search_keywords = ["조사", "검색", "알려줘", "정보", "뭐야", "누구", "어떤 회사", "회사정보"]
            needs_web_search = any(kw in text for kw in web_search_keywords)
            
            if needs_web_search or intent == "web_search":
                # 웹검색 수행
                try:
                    from duckduckgo_search import DDGS
                    search_results = []
                    with DDGS() as ddgs:
                        for r in ddgs.text(text, max_results=5):
                            search_results.append(f"• {r['title']}: {r['body'][:100]}...")
                    
                    if search_results:
                        search_context = "\n".join(search_results)
                        chat_response = await ai_parser.generate_chat_response(
                            f"다음 웹 검색 결과를 바탕으로 '{text}'에 대해 답변해주세요:\n\n{search_context}",
                            user_name
                        )
                    else:
                        chat_response = await ai_parser.generate_chat_response(text, user_name)
                except Exception as e:
                    add_debug_log("web_search_error", error=str(e))
                    chat_response = await ai_parser.generate_chat_response(text, user_name)
            else:
                chat_response = await ai_parser.generate_chat_response(text, user_name)
            
            add_debug_log("chat_response_success", {"response_length": len(chat_response)})
            await nw_client.send_text_message(channel_id, chat_response, channel_type)
        except Exception as e:
            add_debug_log("chat_response_error", error=str(e))
            await nw_client.send_text_message(channel_id, "죄송합니다, 응답 생성 중 오류가 발생했습니다.", channel_type)
        return  # 대화모드에서는 여기서 종료!
    
    # ═══════════════════════════════════════════════════════════════════
    # 3단계: 의도별 처리 (작업모드)
    # ═══════════════════════════════════════════════════════════════════
    
    # 인사
    if intent == "greeting":
        name_part = f"{user_name}님! " if user_name else ""
        await nw_client.send_text_message(
            channel_id,
            f"👋 안녕하세요, {name_part}작업일지봇이에요!\n\n"
            "📋 '작업모드' - 작업일지 입력/관리\n"
            "💬 '대화모드' - 자유 대화\n"
            "❓ '도움말' - 사용법 확인",
            channel_type
        )
        return
    
    # 도움말
    if intent == "help":
        # 도움말 메시지 (여러 개로 분할)
        help_main = (
            "📚 작업일지봇 도움말\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔄 모드 전환\n"
            "• 작업모드 - 작업일지 관리\n"
            "• 대화모드 - GPT 자유대화\n\n"
            "📖 상세 도움말:\n"
            "• '도움말 입력' - 작업 입력 방법\n"
            "• '도움말 조회' - 조회/검색 방법\n"
            "• '도움말 수정' - 수정/삭제 방법\n"
            "• '도움말 분석' - 통계/분석 방법"
        )
        await nw_client.send_text_message(channel_id, help_main, channel_type)
        return
    
    # 상세 도움말 - 입력
    if "도움말" in text and ("입력" in text or "저장" in text or "등록" in text):
        help_input = (
            "✅ 작업일지 입력 방법\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📝 기본 입력\n"
            "• 틸리언 1톤하차 3만원\n"
            "• 나블리 양품화 20개 800원\n"
            "• A업체 검수 50000원\n\n"
            "📝 다중 입력 (한번에 여러 건)\n"
            "• 틸리언 하차 3만, 나블리 검수 2만\n"
            "• A업체 입고 1만 그리고 B업체 출고 2만\n\n"
            "📝 복사 입력\n"
            "• 어제꺼 오늘로 복사해줘\n"
            "• 지난주 틸리언꺼 복사\n\n"
            "💡 업체명 + 작업종류 + 금액 형식으로 입력"
        )
        await nw_client.send_text_message(channel_id, help_input, channel_type)
        return
    
    # 상세 도움말 - 조회
    if "도움말" in text and ("조회" in text or "검색" in text or "보기" in text):
        help_query = (
            "🔍 조회/검색 방법\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📋 기간별 조회\n"
            "• 오늘 작업 정리해줘\n"
            "• 이번주 작업 보여줘\n"
            "• 이번달 작업일지\n"
            "• 1월 20일부터 25일까지\n\n"
            "🔍 조건 검색\n"
            "• 틸리언 작업 보여줘\n"
            "• 3만원짜리 뭐있어?\n"
            "• 양품화 작업 검색\n"
            "• 오늘 나블리 있어?\n\n"
            "💡 자연어로 편하게 물어보세요"
        )
        await nw_client.send_text_message(channel_id, help_query, channel_type)
        return
    
    # 상세 도움말 - 수정
    if "도움말" in text and ("수정" in text or "삭제" in text or "취소" in text):
        help_edit = (
            "✏️ 수정/삭제 방법\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🗑️ 취소/삭제\n"
            "• 취소 (방금 입력한 것)\n"
            "• 방금꺼 삭제해줘\n"
            "• 오늘 틸리언 3만원꺼 삭제\n\n"
            "✏️ 수정\n"
            "• 방금꺼 5만원으로 수정\n"
            "• 오늘 틸리언꺼 수정해줘\n\n"
            "📋 일괄 수정\n"
            "• 오늘 틸리언 전부 5만원으로\n"
            "• 이번주 나블리 단가 일괄 수정\n\n"
            "🔄 되돌리기\n"
            "• 되돌려줘 (최근 변경 취소)"
        )
        await nw_client.send_text_message(channel_id, help_edit, channel_type)
        return
    
    # 상세 도움말 - 분석
    if "도움말" in text and ("분석" in text or "통계" in text or "비교" in text):
        help_analysis = (
            "📊 통계/분석 방법\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📈 통계\n"
            "• 이번달 총 얼마야?\n"
            "• 오늘 몇 건 했어?\n"
            "• 가장 많이 일한 업체\n\n"
            "📊 기간 비교\n"
            "• 지난주랑 이번주 비교해줘\n"
            "• 1월이랑 2월 비교\n"
            "• 어제랑 오늘 비교\n\n"
            "💡 데이터 분석 질문\n"
            "• 틸리언 단가 적정해?\n"
            "• 비용 절감 방법 있어?\n"
            "• 이번달 트렌드 분석해줘\n\n"
            "🌐 대시보드\n"
            "• 대시보드 (웹 링크 제공)"
        )
        await nw_client.send_text_message(channel_id, help_analysis, channel_type)
        return
    
    # 테스트
    if intent == "test":
        await nw_client.send_text_message(
            channel_id,
            f"🏓 퐁! 정상 작동 중!\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            channel_type
        )
        return
    
    # 대화모드 시작
    if intent == "chat_mode_start":
        conv_manager.set_state(user_id=user_id, channel_id=channel_id, pending_data={"chat_mode": True}, missing=[], last_question="💬 대화모드")
        await nw_client.send_text_message(
            channel_id,
            "💬 대화모드 시작!\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "ChatGPT처럼 자유롭게 대화하세요! 🤖\n\n"
            "• 무엇이든 물어보세요\n"
            "• 웹 검색: \"~에 대해 조사해줘\"\n"
            "• 정보 요청: \"~가 뭐야?\"\n\n"
            "📋 작업일지는 '작업모드'에서!",
            channel_type
        )
        return
    
    # 대화모드 종료
    if intent == "chat_mode_end":
        existing_state = conv_manager.get_state(user_id)
        if existing_state and existing_state.get("pending_data", {}).get("chat_mode"):
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "💬 대화모드가 종료되었습니다.\n📋 '작업모드'로 작업을 시작하세요!", channel_type)
        else:
            await nw_client.send_text_message(channel_id, "현재 대화모드가 아닙니다.", channel_type)
        return
    
    # 작업모드 시작
    if intent == "work_mode_start":
        # 대화모드였다면 종료
        conv_manager.clear_state(user_id)
        conv_manager.set_state(user_id=user_id, channel_id=channel_id, pending_data={"work_mode": True}, missing=[], last_question="📋 작업모드")
        await nw_client.send_text_message(
            channel_id,
            "📋 작업모드 시작!\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ 입력: 틸리언 1톤하차 3만원\n"
            "📊 조회: 오늘/이번주 작업 정리해줘\n"
            "🔍 검색: 틸리언 작업 보여줘\n"
            "📈 분석: 이번달 통계, 지난주 비교\n\n"
            "💬 자유 대화는 '대화모드'를 입력하세요",
            channel_type
        )
        return
    
    # 작업모드 종료
    if intent == "work_mode_end":
        existing_state = conv_manager.get_state(user_id)
        if existing_state and existing_state.get("pending_data", {}).get("work_mode"):
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "📋 작업모드가 종료되었습니다.\n💬 '대화모드'로 대화를 시작하세요!", channel_type)
        else:
            await nw_client.send_text_message(channel_id, "현재 작업모드가 아닙니다.", channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 미완성 작업일지 상태에서 다른 의도 감지 시 상태 초기화
    # ═══════════════════════════════════════════════════════════════════
    if existing_state and existing_state.get("missing"):
        # 미완성 작업일지 입력 중인데 다른 의도가 감지됨
        non_continue_intents = [
            "greeting", "help", "test", "chat_mode_start", "chat_mode_end",
            "work_mode_start", "work_mode_end", "web_search", "dashboard", "chat"
        ]
        if intent in non_continue_intents or "취소" in text or "그만" in text or "안할래" in text:
            add_debug_log("clearing_pending_state", {"reason": f"different intent: {intent}"})
            conv_manager.clear_state(user_id)
            if "취소" in text or "그만" in text or "안할래" in text:
                await nw_client.send_text_message(channel_id, "✅ 입력을 취소했습니다.", channel_type)
                return
            # 새 의도 처리 계속
    
    # 취소 요청
    if intent == "cancel":
        recent_log = get_user_recent_log(user_id)
        if recent_log:
            conv_manager.set_state(
                user_id=user_id, channel_id=channel_id,
                pending_data={"cancel_mode": True, "log_id": recent_log["id"], "log_info": recent_log},
                missing=[], last_question="🗑️ 취소 확인"
            )
            저장시간 = recent_log.get("저장시간", "")
            try:
                dt = datetime.fromisoformat(저장시간)
                저장시간 = dt.strftime("%H:%M")
            except:
                pass
            await nw_client.send_text_message(
                channel_id,
                f"🗑️ 이 작업을 삭제할까요?\n\n"
                f"• 날짜: {recent_log.get('날짜', '-')}\n"
                f"• 업체: {recent_log.get('업체명', '-')}\n"
                f"• 작업: {recent_log.get('분류', '-')}\n"
                f"• 금액: {recent_log.get('합계', 0):,}원\n"
                f"• 저장시간: {저장시간}\n\n"
                f"삭제하시겠어요?",
                channel_type
            )
        else:
            await nw_client.send_text_message(channel_id, "🚫 삭제할 작업일지가 없습니다.", channel_type)
        return
    
    # 수정 요청
    if intent == "edit":
        # DB에서 30초 내 저장된 최근 로그 확인
        recent_log = get_user_recent_log(user_id, within_seconds=30)
        if recent_log:
            conv_manager.set_state(
                user_id=user_id, channel_id=channel_id,
                pending_data={"edit_mode": True, "log_id": recent_log.get("id"), "original": recent_log},
                missing=[], last_question="수정 대기"
            )
            await nw_client.send_text_message(
                channel_id,
                f"✏️ 수정할 내용을 입력해주세요.\n\n현재: {recent_log.get('업체명', '-')} {recent_log.get('분류', '-')} {recent_log.get('합계', 0):,}원",
                channel_type
            )
        else:
            await nw_client.send_text_message(channel_id, "✏️ 수정할 작업이 없습니다. (저장 후 30초 내)", channel_type)
        return
    
    # 작업일지 조회
    if intent == "work_log_query":
        # AI로 날짜 범위 파싱
        date_result = await ai_parser.parse_date_range(text)
        add_debug_log("date_range_parsed", data=date_result)
        
        if date_result.get("found") and date_result.get("start_date") and date_result.get("end_date"):
            try:
                start_date = date_result["start_date"]
                end_date = date_result["end_date"]
                period_name = date_result.get("period_name", f"{start_date} ~ {end_date}")
                
                # 기간별 작업일지 조회
                logs = get_work_logs_by_period(start_date, end_date)
                
                if not logs:
                    await nw_client.send_text_message(
                        channel_id,
                        f"📋 {period_name} 작업일지가 없습니다.",
                        channel_type
                    )
                else:
                    # 바로 다운로드 링크 제공
                    total_amount = sum(l.get("합계", 0) or 0 for l in logs)
                    
                    import os
                    base_url = os.getenv("BACKEND_URL", "https://my-streamlit-app-2-production.up.railway.app")
                    download_url = f"{base_url}/work-log/export?start_date={start_date}&end_date={end_date}&format=excel"
                    
                    # 업체별 간단 요약
                    by_vendor = {}
                    for log in logs:
                        vendor = log.get("업체명", "기타")
                        if vendor not in by_vendor:
                            by_vendor[vendor] = {"count": 0, "amount": 0}
                        by_vendor[vendor]["count"] += 1
                        by_vendor[vendor]["amount"] += log.get("합계", 0) or 0
                    
                    msg = f"📋 {period_name} 작업일지\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    msg += f"📊 총 {len(logs)}건 | 💰 {total_amount:,}원\n"
                    msg += f"🏢 {len(by_vendor)}개 업체\n\n"
                    
                    # 상위 5개 업체만 표시
                    top_vendors = sorted(by_vendor.items(), key=lambda x: -x[1]["amount"])[:5]
                    for vendor, data in top_vendors:
                        msg += f"  • {vendor}: {data['count']}건, {data['amount']:,}원\n"
                    if len(by_vendor) > 5:
                        msg += f"  ... 외 {len(by_vendor) - 5}개 업체\n"
                    
                    msg += f"\n📥 다운로드:\n{download_url}"
                    
                    await nw_client.send_text_message(channel_id, msg, channel_type)
                return
            except Exception as e:
                add_debug_log("summary_error", error=str(e))
                await nw_client.send_text_message(
                    channel_id,
                    f"❌ 작업일지 조회 중 오류: {str(e)}",
                    channel_type
                )
                return
        else:
            # 날짜를 파악하지 못한 경우 안내
            await nw_client.send_text_message(
                channel_id,
                "❓ 조회할 기간을 파악하지 못했습니다.\n\n"
                "예시:\n"
                "• 오늘 작업 정리해줘\n"
                "• 이번주 작업일지 보여줘\n"
                "• 1월 20일부터 25일까지",
                channel_type
            )
            return
    
    # ═══════════════════════════════════════════════════════════════════
    # 조건부 검색 (업체/작업종류/금액/날짜 조건)
    # ═══════════════════════════════════════════════════════════════════
    if intent == "search_query":
        query_params = await ai_parser.parse_advanced_query(text, "search")
        add_debug_log("search_query_params", data=query_params)
        
        logs = search_work_logs(
            vendor=query_params.get("vendor"),
            work_type=query_params.get("work_type"),
            date=query_params.get("date"),
            start_date=query_params.get("start_date"),
            end_date=query_params.get("end_date"),
            price=query_params.get("price"),
            limit=20
        )
        
        if not logs:
            conditions = []
            if query_params.get("vendor"):
                conditions.append(f"업체: {query_params['vendor']}")
            if query_params.get("work_type"):
                conditions.append(f"작업: {query_params['work_type']}")
            if query_params.get("date"):
                conditions.append(f"날짜: {query_params['date']}")
            if query_params.get("price"):
                conditions.append(f"금액: {query_params['price']:,}원")
            
            condition_str = ", ".join(conditions) if conditions else "조건"
            await nw_client.send_text_message(channel_id, f"🔍 [{condition_str}] 조건에 맞는 작업일지가 없습니다.", channel_type)
        else:
            total_amount = sum(l.get("합계", 0) or 0 for l in logs)
            msg = f"🔍 검색 결과: {len(logs)}건 | 💰 {total_amount:,}원\n━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for log in logs[:10]:
                msg += f"• {log.get('날짜', '-')} {log.get('업체명', '-')} {log.get('분류', '-')} {log.get('합계', 0):,}원\n"
            
            if len(logs) > 10:
                msg += f"\n... 외 {len(logs) - 10}건"
            
            await nw_client.send_text_message(channel_id, msg, channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 통계/분석 쿼리
    # ═══════════════════════════════════════════════════════════════════
    if intent == "stats_query":
        query_params = await ai_parser.parse_advanced_query(text, "stats")
        add_debug_log("stats_query_params", data=query_params)
        
        stats = get_work_log_stats(
            start_date=query_params.get("start_date") or query_params.get("date"),
            end_date=query_params.get("end_date") or query_params.get("date"),
            vendor=query_params.get("vendor")
        )
        
        stats_type = query_params.get("stats_type", "total_amount")
        period_name = query_params.get("period_name", "")
        
        if stats_type in ["total_amount", "total_count"]:
            msg = f"📊 {period_name} 통계\n━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📝 총 {stats['total_count']}건\n"
            msg += f"💰 총 {stats['total_amount']:,}원"
            
        elif stats_type == "top_vendor":
            msg = f"🏆 업체별 순위 {period_name}\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, v in enumerate(stats["by_vendor"][:5], 1):
                msg += f"{i}. {v['vendor']} - {v['count']}건, {v['amount']:,}원\n"
            if not stats["by_vendor"]:
                msg += "데이터가 없습니다."
                
        elif stats_type == "by_vendor":
            msg = f"📦 업체별 합계 {period_name}\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for v in stats["by_vendor"]:
                msg += f"• {v['vendor']}: {v['count']}건, {v['amount']:,}원\n"
            msg += f"\n━━━━━━━━━━━━━━━━━━━━\n📊 총 {stats['total_count']}건 | 💰 {stats['total_amount']:,}원"
            
        elif stats_type == "by_work_type":
            msg = f"🔧 작업종류별 합계 {period_name}\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for w in stats["by_work_type"]:
                msg += f"• {w['work_type']}: {w['count']}건, {w['amount']:,}원\n"
            msg += f"\n━━━━━━━━━━━━━━━━━━━━\n📊 총 {stats['total_count']}건 | 💰 {stats['total_amount']:,}원"
            
        elif stats_type == "compare":
            # 기간 비교 (간단 버전)
            msg = f"📈 기간 비교\n━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += f"📊 총 {stats['total_count']}건 | 💰 {stats['total_amount']:,}원\n\n"
            msg += "💡 더 자세한 비교가 필요하시면 각 기간을 따로 조회해주세요."
        else:
            msg = f"📊 통계\n\n📝 총 {stats['total_count']}건 | 💰 {stats['total_amount']:,}원"
        
        await nw_client.send_text_message(channel_id, msg, channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 특정 건 삭제
    # ═══════════════════════════════════════════════════════════════════
    if intent == "specific_delete":
        query_params = await ai_parser.parse_advanced_query(text, "specific_delete")
        add_debug_log("specific_delete_params", data=query_params)
        
        log = find_specific_log(
            vendor=query_params.get("vendor"),
            work_type=query_params.get("work_type"),
            date=query_params.get("date"),
            price=query_params.get("price"),
            user_id=user_id
        )
        
        if log:
            conv_manager.set_state(
                user_id=user_id, channel_id=channel_id,
                pending_data={"cancel_mode": True, "log_id": log["id"], "log_info": log},
                missing=[], last_question="🗑️ 취소 확인"
            )
            await nw_client.send_text_message(
                channel_id,
                f"🗑️ 이 작업을 삭제할까요?\n\n"
                f"• 날짜: {log.get('날짜', '-')}\n"
                f"• 업체: {log.get('업체명', '-')}\n"
                f"• 작업: {log.get('분류', '-')}\n"
                f"• 금액: {log.get('합계', 0):,}원\n\n"
                f"삭제하시겠어요?",
                channel_type
            )
        else:
            await nw_client.send_text_message(channel_id, "🔍 조건에 맞는 작업일지를 찾지 못했습니다.", channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 특정 건 수정
    # ═══════════════════════════════════════════════════════════════════
    if intent == "specific_edit":
        query_params = await ai_parser.parse_advanced_query(text, "specific_edit")
        add_debug_log("specific_edit_params", data=query_params)
        
        log = find_specific_log(
            vendor=query_params.get("vendor"),
            work_type=query_params.get("work_type"),
            date=query_params.get("date"),
            price=query_params.get("price"),
            user_id=user_id
        )
        
        if log:
            conv_manager.set_state(
                user_id=user_id, channel_id=channel_id,
                pending_data={"edit_mode": True, "log_id": log["id"], "original": log},
                missing=[], last_question="수정 대기"
            )
            await nw_client.send_text_message(
                channel_id,
                f"✏️ 수정할 내용을 입력해주세요.\n\n"
                f"현재: {log.get('업체명', '-')} {log.get('분류', '-')} {log.get('합계', 0):,}원\n\n"
                f"예: 'A업체 2톤하차 50000원'",
                channel_type
            )
        else:
            await nw_client.send_text_message(channel_id, "🔍 조건에 맞는 작업일지를 찾지 못했습니다.", channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 다중 건 입력
    # ═══════════════════════════════════════════════════════════════════
    if intent == "multi_entry":
        multi_result = await ai_parser.parse_multi_entry(text)
        add_debug_log("multi_entry_parsed", data=multi_result)
        
        entries = multi_result.get("entries", [])
        if not entries:
            await nw_client.send_text_message(channel_id, "❌ 작업 내용을 파싱하지 못했습니다.", channel_type)
            return
        
        saved_count = 0
        total_amount = 0
        results = []
        
        for entry in entries:
            if entry.get("vendor") and entry.get("work_type") and entry.get("unit_price"):
                try:
                    # 이상치 체크
                    price_history = get_price_history(entry["vendor"], entry["work_type"])
                    anomaly = await ai_parser.check_anomaly(
                        entry["vendor"], entry["work_type"], entry["unit_price"], price_history
                    )
                    
                    entry_total = entry.get("qty", 1) * entry["unit_price"]
                    
                    # 이상치 경고 있어도 일단 저장 (다중 입력이므로)
                    record_id = save_work_log(entry, user_id, user_name)
                    saved_count += 1
                    total_amount += entry_total
                    
                    warning = f" ⚠️{anomaly['reason']}" if anomaly.get("is_anomaly") else ""
                    results.append(f"✅ {entry['vendor']} {entry['work_type']} {entry_total:,}원{warning}")
                except Exception as e:
                    results.append(f"❌ {entry.get('vendor', '?')} {entry.get('work_type', '?')}: {str(e)}")
        
        msg = f"📝 다중 입력 결과\n━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "\n".join(results)
        msg += f"\n\n📊 {saved_count}건 저장 | 💰 {total_amount:,}원"
        
        await nw_client.send_text_message(channel_id, msg, channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 대시보드 링크
    # ═══════════════════════════════════════════════════════════════════
    if intent == "dashboard":
        dashboard_url = get_dashboard_url()
        await nw_client.send_text_message(
            channel_id,
            f"🌐 대시보드 링크\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 작업일지 관리:\n{dashboard_url}/work-log\n\n"
            f"📈 업로드/설정:\n{dashboard_url}\n\n"
            f"💡 링크를 클릭하면 웹 페이지로 이동합니다.",
            channel_type
        )
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 기간 비교
    # ═══════════════════════════════════════════════════════════════════
    if intent == "compare_periods":
        compare_params = await ai_parser.parse_compare_periods(text)
        add_debug_log("compare_periods_parsed", data=compare_params)
        
        if compare_params.get("error") or not compare_params.get("period1") or not compare_params.get("period2"):
            await nw_client.send_text_message(channel_id, "❌ 비교할 기간을 파악하지 못했습니다.", channel_type)
            return
        
        p1 = compare_params["period1"]
        p2 = compare_params["period2"]
        
        stats1 = get_work_log_stats(start_date=p1.get("start_date"), end_date=p1.get("end_date"))
        stats2 = get_work_log_stats(start_date=p2.get("start_date"), end_date=p2.get("end_date"))
        
        # 변화율 계산
        count_diff = stats2["total_count"] - stats1["total_count"]
        amount_diff = stats2["total_amount"] - stats1["total_amount"]
        count_rate = (count_diff / stats1["total_count"] * 100) if stats1["total_count"] > 0 else 0
        amount_rate = (amount_diff / stats1["total_amount"] * 100) if stats1["total_amount"] > 0 else 0
        
        count_arrow = "📈" if count_diff > 0 else "📉" if count_diff < 0 else "➡️"
        amount_arrow = "📈" if amount_diff > 0 else "📉" if amount_diff < 0 else "➡️"
        
        msg = f"📊 기간 비교\n━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"📅 {p1.get('name', '기간1')}\n"
        msg += f"   • {stats1['total_count']}건 | {stats1['total_amount']:,}원\n\n"
        msg += f"📅 {p2.get('name', '기간2')}\n"
        msg += f"   • {stats2['total_count']}건 | {stats2['total_amount']:,}원\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{count_arrow} 건수: {count_diff:+}건 ({count_rate:+.1f}%)\n"
        msg += f"{amount_arrow} 금액: {amount_diff:+,}원 ({amount_rate:+.1f}%)"
        
        await nw_client.send_text_message(channel_id, msg, channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 실행취소 히스토리
    # ═══════════════════════════════════════════════════════════════════
    if intent == "undo":
        history = get_undo_history(user_id, limit=5)
        
        if not history:
            await nw_client.send_text_message(channel_id, "📜 변경 이력이 없습니다.", channel_type)
            return
        
        msg = f"📜 최근 변경 이력 (되돌리기 가능)\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, h in enumerate(history, 1):
            time_str = h.get("time", "")[:16] if h.get("time") else ""
            change_type = h.get("type", "?")
            # 변경 유형 한글화
            type_label = {"INSERT": "추가", "UPDATE": "수정", "DELETE": "삭제"}.get(change_type, change_type)
            msg += f"{i}. [{type_label}] {time_str}\n"
            if h.get("before"):
                before_str = str(h['before'])[:35]
                msg += f"   → {before_str}{'...' if len(str(h.get('before', ''))) > 35 else ''}\n"
        
        msg += f"\n🔄 번호를 입력하면 해당 작업을 되돌립니다.\n예: '1' 또는 '1번 되돌려줘'"
        
        # 선택 대기 상태 저장
        conv_manager.set_state(
            user_id=user_id, channel_id=channel_id,
            pending_data={"undo_history": history},
            missing=[], last_question="🔄 되돌리기 선택"
        )
        
        await nw_client.send_text_message(channel_id, msg, channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 작업 메모 추가
    # ═══════════════════════════════════════════════════════════════════
    if intent == "add_memo":
        query_params = await ai_parser.parse_advanced_query(text, "add_memo")
        add_debug_log("add_memo_params", data=query_params)
        
        # 메모 내용 추출 - 다양한 패턴 지원
        import re
        memo_content = ""
        
        # 패턴 1: "메모: 내용", "메모 내용" (메모 뒤에 내용)
        memo_match = re.search(r'(?:메모|비고)[\s:]*["\']?([^"\']+?)["\']?\s*(?:추가|등록|입력|$)', text, re.IGNORECASE)
        if memo_match:
            memo_content = memo_match.group(1).strip()
        
        # 패턴 2: "내용 메모 추가" (메모 앞에 내용)
        if not memo_content:
            memo_match = re.search(r'(?:방금|최근|이번)?\s*(?:꺼에?|작업에?|것에?)?\s*["\']?([^"\']+?)["\']?\s*(?:메모|비고)\s*(?:추가|등록|입력)', text, re.IGNORECASE)
            if memo_match:
                memo_content = memo_match.group(1).strip()
        
        # 패턴 3: intent_data에서 추출
        if not memo_content and intent_data:
            memo_content = intent_data.get("memo", "") or intent_data.get("content", "")
        
        # 메모 내용이 너무 짧거나 키워드만 있으면 무시
        if memo_content and memo_content in ["방금", "최근", "이번", "꺼", "작업", "것"]:
            memo_content = ""
        
        if not memo_content:
            await nw_client.send_text_message(
                channel_id, 
                "❓ 어떤 메모를 추가할까요?\n\n예시:\n• '긴급 메모 추가'\n• '방금꺼에 확인필요 메모 추가'\n• '메모: 재확인 필요'",
                channel_type
            )
            return
        
        # 최근 작업 또는 조건으로 찾기
        log = find_specific_log(
            vendor=query_params.get("vendor"),
            work_type=query_params.get("work_type"),
            date=query_params.get("date"),
            user_id=user_id
        )
        
        if not log:
            # 최근 저장한 것 찾기 (DB에서 조회)
            recent_log = get_user_recent_log(user_id, within_seconds=300)  # 5분 내 저장된 것
            if recent_log:
                log = {"id": recent_log.get("id")}
        
        if log and log.get("id"):
            if add_memo_to_log(log["id"], memo_content):
                await nw_client.send_text_message(channel_id, f"📝 메모 추가됨: [{memo_content}]", channel_type)
            else:
                await nw_client.send_text_message(channel_id, "❌ 메모 추가 실패", channel_type)
        else:
            await nw_client.send_text_message(channel_id, "🔍 메모를 추가할 작업을 찾지 못했습니다.", channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 일괄 수정
    # ═══════════════════════════════════════════════════════════════════
    if intent == "bulk_edit":
        query_params = await ai_parser.parse_advanced_query(text, "bulk_edit")
        add_debug_log("bulk_edit_params", data=query_params)
        
        # 수정할 조건과 새 값
        conditions = {
            "vendor": query_params.get("vendor"),
            "work_type": query_params.get("work_type"),
            "date": query_params.get("date"),
            "start_date": query_params.get("start_date"),
            "end_date": query_params.get("end_date"),
        }
        
        new_price = query_params.get("price")
        
        if not new_price:
            await nw_client.send_text_message(
                channel_id, 
                "❓ 어떤 값으로 수정할까요?\n예: '오늘 틸리언 전부 5만원으로'",
                channel_type
            )
            return
        
        # 먼저 몇 건인지 확인
        matching_logs = search_work_logs(**{k: v for k, v in conditions.items() if v}, limit=100)
        
        if not matching_logs:
            await nw_client.send_text_message(channel_id, "🔍 조건에 맞는 작업이 없습니다.", channel_type)
            return
        
        # 확인 요청
        conv_manager.set_state(
            user_id=user_id, channel_id=channel_id,
            pending_data={"bulk_edit_mode": True, "conditions": conditions, "new_price": new_price, "count": len(matching_logs)},
            missing=[], last_question="⚠️ 일괄 수정 확인"
        )
        
        await nw_client.send_text_message(
            channel_id,
            f"⚠️ 일괄 수정 확인\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 {len(matching_logs)}건을 {new_price:,}원으로 수정합니다.\n\n"
            f"진행하시겠어요?",
            channel_type
        )
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 복사 기능
    # ═══════════════════════════════════════════════════════════════════
    if intent == "copy_entry":
        copy_params = await ai_parser.parse_copy_request(text)
        add_debug_log("copy_params", data=copy_params)
        
        if copy_params.get("error"):
            await nw_client.send_text_message(channel_id, "❌ 복사 조건을 파악하지 못했습니다.", channel_type)
            return
        
        source_conditions = {
            "date": copy_params.get("source_date"),
            "start_date": copy_params.get("source_period_start"),
            "end_date": copy_params.get("source_period_end"),
            "vendor": copy_params.get("vendor"),
            "work_type": copy_params.get("work_type"),
        }
        
        target_date = copy_params.get("target_date") or datetime.now().strftime("%Y-%m-%d")
        
        # 먼저 몇 건인지 확인
        matching_logs = search_work_logs(**{k: v for k, v in source_conditions.items() if v}, limit=100)
        
        if not matching_logs:
            await nw_client.send_text_message(channel_id, "🔍 복사할 작업을 찾지 못했습니다.", channel_type)
            return
        
        # 확인 요청
        conv_manager.set_state(
            user_id=user_id, channel_id=channel_id,
            pending_data={"copy_mode": True, "source": source_conditions, "target_date": target_date, "count": len(matching_logs)},
            missing=[], last_question="📋 복사 확인"
        )
        
        await nw_client.send_text_message(
            channel_id,
            f"📋 복사 확인\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 {len(matching_logs)}건을 {target_date}로 복사합니다.\n\n"
            f"진행하시겠어요?",
            channel_type
        )
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 웹 검색
    # ═══════════════════════════════════════════════════════════════════
    if intent == "web_search":
        # 검색어 추출
        search_query = intent_data.get("query") if intent_data else None
        
        if not search_query:
            # AI로 검색어 추출
            import re
            # "조사해줘", "검색해줘", "찾아봐" 앞의 내용을 검색어로
            patterns = [
                r'(.+?)(?:에 대해|를|을)?\s*(?:조사|검색|찾아|알아).*',
                r'(?:조사|검색|찾아|알아).*?[\"\'「」](.+?)[\"\'」]',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    search_query = match.group(1).strip()
                    break
            
            if not search_query:
                search_query = text  # 전체 텍스트를 검색어로
        
        add_debug_log("web_search_start", {"query": search_query})
        
        await nw_client.send_text_message(channel_id, f"🔍 '{search_query}' 검색 중...", channel_type)
        
        try:
            search_result = await ai_parser.web_search(search_query)
            add_debug_log("web_search_result", {"success": search_result.get("success")})
            
            if search_result.get("success"):
                msg = f"🌐 웹 검색 결과\n━━━━━━━━━━━━━━━━━━━━\n\n"
                msg += f"🔎 검색어: {search_query}\n\n"
                msg += search_result.get("summary", "요약 없음")
                
                # 메시지 길이 제한
                if len(msg) > 1500:
                    msg = msg[:1450] + "\n\n... (생략)"
                
                await nw_client.send_text_message(channel_id, msg, channel_type)
            else:
                await nw_client.send_text_message(
                    channel_id,
                    f"❌ 검색 실패: {search_result.get('error', '알 수 없는 오류')}",
                    channel_type
                )
        except Exception as e:
            add_debug_log("web_search_error", error=str(e))
            await nw_client.send_text_message(channel_id, f"❌ 검색 오류: {str(e)}", channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 일반 대화 (chat) 처리
    # ═══════════════════════════════════════════════════════════════════
    if intent == "chat":
        add_debug_log("chat_intent_handler", {"text": text})
        try:
            chat_response = await ai_parser.generate_chat_response(text, user_name)
            add_debug_log("chat_response", {"response": chat_response})
            await nw_client.send_text_message(channel_id, chat_response, channel_type)
        except Exception as e:
            add_debug_log("chat_response_error", error=str(e))
            await nw_client.send_text_message(channel_id, "죄송합니다, 응답 생성 중 오류가 발생했습니다.", channel_type)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # 4단계: 작업일지 입력 처리 (작업모드)
    # ═══════════════════════════════════════════════════════════════════
    
    # AI 파싱
    try:
        add_debug_log("ai_parsing_start", {"text": text})
        parse_result = await ai_parser.parse_message(text, existing_state)
        add_debug_log("ai_parsing_result", parse_result)
    except Exception as e:
        add_debug_log("ai_parsing_error", error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
        try:
            await nw_client.send_text_message(
                channel_id,
                f"❌ AI 파싱 오류: {str(e)}",
                channel_type
            )
        except Exception as send_err:
            add_debug_log("send_error_msg_failed", error=str(send_err))
        return
    
    if parse_result.get("success"):
        # 파싱 성공 - 중복 체크 후 저장
        data = parse_result.get("data", {})
        
        # 유효성 검증
        validation = validate_work_data(data)
        
        # 에러가 있으면 저장 불가
        if not validation["valid"]:
            error_msg = "❌ 저장할 수 없습니다:\n" + "\n".join(f"• {e}" for e in validation["errors"])
            await nw_client.send_text_message(channel_id, error_msg, channel_type)
            return
        
        # 경고가 있으면 사용자에게 확인 요청
        if validation["warnings"]:
            warning_msg = "⚠️ 확인이 필요합니다:\n"
            warning_msg += "\n".join(f"• {w}" for w in validation["warnings"])
            warning_msg += f"\n\n저장할 내용:\n"
            warning_msg += f"• 업체: {data.get('vendor', '-')}\n"
            warning_msg += f"• 작업: {data.get('work_type', '-')}\n"
            warning_msg += f"• 수량: {data.get('qty', 1)}개\n"
            warning_msg += f"• 단가: {data.get('unit_price', 0):,}원\n"
            warning_msg += f"• 합계: {data.get('qty', 1) * data.get('unit_price', 0):,}원\n\n"
            warning_msg += "그래도 저장할까요? ('예' / '아니오')"
            
            conv_manager.set_state(
                user_id=user_id,
                channel_id=channel_id,
                pending_data=data,
                missing=[],
                last_question="⚠️ 경고 확인"
            )
            
            await nw_client.send_text_message(channel_id, warning_msg, channel_type)
            return
        
        # 중복 체크
        duplicate = check_duplicate(data)
        if duplicate:
            # 중복 발견 - 사용자에게 확인 요청
            conv_manager.set_state(
                user_id=user_id,
                channel_id=channel_id,
                pending_data=data,
                missing=[],
                last_question=f"⚠️ 중복 확인"
            )
            
            저장시간 = duplicate.get("저장시간", "")
            if 저장시간:
                try:
                    dt = datetime.fromisoformat(저장시간)
                    저장시간 = dt.strftime("%H:%M")
                except:
                    pass
            
            await nw_client.send_text_message(
                channel_id,
                f"⚠️ 오늘 이미 같은 기록이 있어요!\n"
                f"[기존] {duplicate['업체명']} / {duplicate['분류']} / {duplicate['합계']:,}원 ({저장시간})\n\n"
                f"그래도 추가로 저장할까요?\n'예' 또는 '아니오'로 답해주세요.",
                channel_type
            )
            return
        
        # 수정 모드인 경우 기존 레코드 삭제 후 새로 저장
        if existing_state and existing_state.get("pending_data", {}).get("edit_mode"):
            old_log_id = existing_state.get("pending_data", {}).get("log_id")
            if old_log_id:
                delete_work_log(old_log_id, 변경자=user_name, works_user_id=user_id)
                add_debug_log("edit_mode_deleted_old", {"old_log_id": old_log_id})
        
        # 저장
        try:
            record_id = save_work_log(data, user_id, user_name)
            
            # 대화 상태 초기화
            conv_manager.clear_state(user_id)
            
            # 확인 메시지 생성 및 전송 (취소는 30초 내 DB 조회로 처리)
            response_msg = generate_success_message(data, record_id)
            add_debug_log("sending_success_message", {"channel_id": channel_id, "message": response_msg})
            
            try:
                send_result = await nw_client.send_text_message(channel_id, response_msg, channel_type)
                add_debug_log("message_sent", send_result)
            except Exception as e:
                add_debug_log("send_message_error", error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
            
        except Exception as e:
            await nw_client.send_text_message(
                channel_id,
                f"❌ 저장 중 오류가 발생했습니다: {str(e)}",
                channel_type
            )
    else:
        # 파싱 실패 - 추가 정보 요청
        data = parse_result.get("data", {})
        missing = parse_result.get("missing", [])
        question = parse_result.get("question", "")
        
        # 아무것도 인식 못한 경우 - GPT 데이터 분석/조언 모드
        if not data or (not data.get("vendor") and not data.get("work_type") and not data.get("unit_price")):
            add_debug_log("work_mode_gpt_analysis", {"original_text": text})
            
            try:
                # DB에서 최근 데이터 요약 가져오기
                with get_connection() as con:
                    # 이번달 요약
                    today = datetime.now()
                    month_start = today.replace(day=1).strftime("%Y-%m-%d")
                    month_end = today.strftime("%Y-%m-%d")
                    
                    # 이번달 통계
                    stats = con.execute("""
                        SELECT 
                            COUNT(*) as total_count,
                            COALESCE(SUM(합계), 0) as total_amount,
                            COUNT(DISTINCT 업체명) as vendor_count
                        FROM work_log 
                        WHERE 날짜 BETWEEN ? AND ?
                    """, (month_start, month_end)).fetchone()
                    
                    # 업체별 요약 (상위 5개)
                    top_vendors = con.execute("""
                        SELECT 업체명, COUNT(*) as cnt, SUM(합계) as total
                        FROM work_log 
                        WHERE 날짜 BETWEEN ? AND ?
                        GROUP BY 업체명 
                        ORDER BY total DESC LIMIT 5
                    """, (month_start, month_end)).fetchall()
                    
                    # 작업종류별 요약
                    top_types = con.execute("""
                        SELECT 분류, COUNT(*) as cnt, SUM(합계) as total
                        FROM work_log 
                        WHERE 날짜 BETWEEN ? AND ?
                        GROUP BY 분류 
                        ORDER BY total DESC LIMIT 5
                    """, (month_start, month_end)).fetchall()
                
                # 데이터 요약 문자열 생성
                data_summary = f"""
이번달 작업일지 요약 ({month_start} ~ {month_end}):
- 총 {stats[0]}건, {stats[1]:,}원
- 거래 업체: {stats[2]}개

업체별 (상위 5):
"""
                for v in top_vendors:
                    data_summary += f"- {v[0]}: {v[1]}건, {v[2]:,}원\n"
                
                data_summary += "\n작업종류별 (상위 5):\n"
                for t in top_types:
                    data_summary += f"- {t[0]}: {t[1]}건, {t[2]:,}원\n"
                
                # GPT에게 데이터 분석 요청
                analysis_response = await ai_parser.analyze_work_data(text, data_summary, user_name)
                add_debug_log("work_analysis_response", {"response_length": len(analysis_response)})
                
                await nw_client.send_text_message(channel_id, analysis_response, channel_type)
                
            except Exception as e:
                add_debug_log("work_analysis_error", error=str(e))
                # 오류 시 기본 안내 메시지
                await nw_client.send_text_message(
                    channel_id,
                    "📋 작업모드입니다.\n\n"
                    "✅ 입력: 틸리언 1톤하차 3만원\n"
                    "📊 조회: 오늘 작업 정리해줘\n"
                    "🔍 검색: 틸리언 작업 보여줘\n"
                    "📈 분석: 이번달 통계\n\n"
                    "💬 자유 대화는 '대화모드'를 입력하세요!",
                    channel_type
                )
            return
        
        # 부분 인식 - 추가 정보 요청
        if not question:
            question = "다시 말씀해주세요."
        
        # 대화 상태 저장
        conv_manager.set_state(
            user_id=user_id,
            channel_id=channel_id,
            pending_data=data,
            missing=missing,
            last_question=question
        )
        
        # 질문 메시지 전송
        add_debug_log("sending_question", {"channel_id": channel_id, "question": question})
        try:
            send_result = await nw_client.send_text_message(channel_id, f"🤔 {question}", channel_type)
            add_debug_log("question_sent", send_result)
        except Exception as e:
            add_debug_log("send_question_error", error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")


def generate_success_message(data: Dict[str, Any], record_id: int) -> str:
    """저장 성공 메시지 생성"""
    vendor = data.get("vendor", "")
    work_type = data.get("work_type", "")
    qty = data.get("qty", 1)
    unit_price = data.get("unit_price", 0)
    total = qty * unit_price
    
    msg = f"✅ 저장완료! (30초 내 '취소' 입력 시 삭제)\n"
    msg += f"• 업체: {vendor}\n"
    msg += f"• 작업: {work_type}\n"
    
    if qty > 1:
        msg += f"• 수량: {qty}개 × {unit_price:,}원\n"
    else:
        msg += f"• 단가: {unit_price:,}원\n"
    
    msg += f"• 합계: {total:,}원"
    
    if data.get("remark"):
        msg += f"\n• 비고: {data['remark']}"
    
    return msg


async def process_postback(
    user_id: str,
    channel_id: str,
    postback: str,
    channel_type: str = "group"
):
    """
    버튼 클릭(Postback) 처리
    
    Args:
        user_id: 사용자 ID
        channel_id: 채널 ID
        postback: Postback 데이터 (JSON)
        channel_type: 채널 타입
    """
    nw_client = get_naver_works_client()
    conv_manager = get_conversation_manager()
    
    try:
        data = json.loads(postback)
        action = data.get("action")
        
        if action == "cancel":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(
                channel_id,
                "🚫 취소되었습니다.",
                channel_type
            )
        elif action == "confirm":
            # 확인 버튼 클릭 시 저장
            work_data = data.get("data", {})
            if work_data:
                record_id = save_work_log(work_data, user_id)
                conv_manager.clear_state(user_id)
                await nw_client.send_text_message(
                    channel_id,
                    "✅ 저장완료!",
                    channel_type
                )
    except json.JSONDecodeError:
        pass


async def process_excel_upload(
    user_id: str,
    channel_id: str, 
    file_url: str,
    file_name: str,
    channel_type: str
):
    """엑셀 파일 업로드 처리 (작업일지 일괄 등록)"""
    import httpx
    import pandas as pd
    from io import BytesIO
    
    add_debug_log("excel_upload_start", {"file_name": file_name, "file_url": file_url[:50] + "..."})
    
    try:
        nw_client = get_naver_works_client()
        
        # 처리 중 메시지
        await nw_client.send_text_message(
            channel_id,
            f"📊 '{file_name}' 처리 중...",
            channel_type
        )
        
        # 파일 다운로드
        token = await nw_client._get_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(file_url, headers=headers)
            
            add_debug_log("excel_download_response", {"status": response.status_code, "content_length": len(response.content)})
            
            if response.status_code != 200:
                await nw_client.send_text_message(
                    channel_id,
                    f"❌ 파일 다운로드 실패 (상태: {response.status_code})\n\n"
                    f"💡 파일을 다시 보내주시거나, 웹 대시보드에서 업로드해주세요.",
                    channel_type
                )
                return
        
        # 엑셀 읽기
        df = pd.read_excel(BytesIO(response.content))
        
        # 필수 컬럼 확인
        required_cols = ["날짜", "업체명", "분류", "단가"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        
        if missing_cols:
            await nw_client.send_text_message(
                channel_id,
                f"❌ 필수 컬럼 누락: {', '.join(missing_cols)}\n\n"
                f"필요한 컬럼: 날짜, 업체명, 분류, 단가\n"
                f"선택 컬럼: 수량, 비고(또는 비고1)",
                channel_type
            )
            return
        
        # 데이터 처리
        saved_count = 0
        error_count = 0
        total_amount = 0
        
        # 사용자 이름 가져오기
        user_name = None
        try:
            user_name = await nw_client.get_user_name(user_id)
        except:
            pass
        
        skip_count = 0  # 중복 스킵 카운트
        
        for _, row in df.iterrows():
            try:
                날짜 = row.get("날짜")
                if pd.isna(날짜):
                    continue
                    
                # 날짜 포맷 변환
                if hasattr(날짜, 'strftime'):
                    날짜 = 날짜.strftime("%Y-%m-%d")
                else:
                    날짜 = str(날짜)[:10]
                
                업체명 = str(row.get("업체명", "")).strip()
                분류 = str(row.get("분류", "")).strip()
                단가 = int(row.get("단가", 0) or 0)
                수량 = int(row.get("수량", 1) or 1)
                # 비고 또는 비고1 둘 다 지원
                비고 = str(row.get("비고", "") or row.get("비고1", "") or "")
                # no 컬럼 (원본 행 번호)
                원본번호 = row.get("no", "")
                if pd.notna(원본번호):
                    원본번호 = int(원본번호)
                else:
                    원본번호 = None
                
                if not 업체명 or not 분류:
                    continue
                
                합계 = 단가 * 수량
                
                # 비고에 원본번호 포함 (중복 체크용)
                if 원본번호:
                    remark_prefix = f"[엑셀:no={원본번호}]"
                else:
                    remark_prefix = "[엑셀업로드]"
                
                full_remark = f"{remark_prefix} {비고}".strip() if 비고 else remark_prefix
                
                # 중복 체크: 날짜 + 업체명 + 분류 + 원본번호로 체크
                with get_connection() as con:
                    if 원본번호:
                        # 원본번호가 있으면 원본번호로 중복 체크
                        existing = con.execute(
                            """SELECT id FROM work_log 
                               WHERE 날짜 = ? AND 업체명 = ? AND 분류 = ? AND 비고1 LIKE ?
                               LIMIT 1""",
                            (날짜, 업체명, 분류, f"%no={원본번호}%")
                        ).fetchone()
                    else:
                        # 원본번호 없으면 기존 방식 (날짜+업체+분류+수량+단가)
                        existing = con.execute(
                            """SELECT id FROM work_log 
                               WHERE 날짜 = ? AND 업체명 = ? AND 분류 = ? AND 수량 = ? AND 단가 = ?
                               LIMIT 1""",
                            (날짜, 업체명, 분류, 수량, 단가)
                        ).fetchone()
                
                if existing:
                    skip_count += 1
                    continue  # 중복 스킵
                
                data = {
                    "vendor": 업체명,
                    "work_type": 분류,
                    "unit_price": 단가,
                    "qty": 수량,
                    "date": 날짜,
                    "remark": full_remark
                }
                
                save_work_log(data, user_id, user_name)
                saved_count += 1
                total_amount += 합계
                
            except Exception as e:
                error_count += 1
                add_debug_log("excel_row_error", error=str(e))
        
        # 결과 메시지
        result_msg = f"📊 엑셀 업로드 완료\n━━━━━━━━━━━━━━━━━━━━\n\n"
        result_msg += f"📎 파일: {file_name}\n"
        result_msg += f"✅ 저장: {saved_count}건\n"
        if skip_count > 0:
            result_msg += f"⏭️ 중복 스킵: {skip_count}건\n"
        if error_count > 0:
            result_msg += f"❌ 오류: {error_count}건\n"
        result_msg += f"💰 합계: {total_amount:,}원"
        
        await nw_client.send_text_message(channel_id, result_msg, channel_type)
        
    except Exception as e:
        add_debug_log("excel_upload_error", error=f"{type(e).__name__}: {str(e)}")
        try:
            nw_client = get_naver_works_client()
            await nw_client.send_text_message(
                channel_id,
                f"❌ 엑셀 처리 오류: {str(e)}",
                channel_type
            )
        except:
            pass


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.post("/webhook")
async def naver_works_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    네이버 웍스 Bot Webhook 엔드포인트
    
    네이버 웍스에서 메시지가 오면 이 엔드포인트로 POST 요청이 옵니다.
    """
    # 요청 본문 읽기
    body = await request.body()
    add_debug_log("webhook_received", {"body_length": len(body)})
    
    # 서명 검증 (선택적 - 보안 강화)
    signature = request.headers.get("X-WORKS-Signature", "")
    
    try:
        nw_client = get_naver_works_client()
    except Exception as e:
        add_debug_log("webhook_nw_client_error", error=str(e))
    
    # JSON 파싱
    try:
        payload = json.loads(body)
        add_debug_log("webhook_payload", payload)
    except json.JSONDecodeError as e:
        add_debug_log("webhook_json_error", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # 이벤트 타입 확인
    event_type = payload.get("type")
    add_debug_log("webhook_event_type", {"type": event_type})
    
    # 봇 연결 확인 (URL 검증 요청)
    if event_type == "url_verification":
        add_debug_log("url_verification", "success")
        return {"type": "url_verification"}
    
    # 봇 초대 이벤트 처리 (join)
    if event_type == "join":
        source = payload.get("source", {})
        channel_id = source.get("channelId", "")
        
        add_debug_log("bot_joined", {"channel_id": channel_id})
        
        if channel_id:
            background_tasks.add_task(
                send_welcome_message,
                channel_id
            )
        return {"status": "ok"}
    
    # 메시지 이벤트 처리
    if event_type == "message":
        source = payload.get("source", {})
        content = payload.get("content", {})
        
        user_id = source.get("userId", "")
        channel_id = source.get("channelId", "")
        
        # 채널 타입 결정 (channelId가 있으면 그룹, 없으면 1:1)
        channel_type = "group" if channel_id else "user"
        if not channel_id:
            channel_id = user_id  # 1:1 채팅인 경우 userId 사용
        
        content_type = content.get("type", "")
        
        add_debug_log("message_event", {
            "user_id": user_id,
            "channel_id": channel_id,
            "channel_type": channel_type,
            "content_type": content_type
        })
        
        if content_type == "text":
            text = content.get("text", "")
            if text:
                add_debug_log("text_message", {"text": text})
                # 백그라운드에서 메시지 처리 (빠른 응답을 위해)
                background_tasks.add_task(
                    process_message,
                    user_id,
                    channel_id,
                    text,
                    channel_type
                )
        
        elif content_type == "postback":
            postback = content.get("postback", "")
            if postback:
                add_debug_log("postback_message", {"postback": postback})
                background_tasks.add_task(
                    process_postback,
                    user_id,
                    channel_id,
                    postback,
                    channel_type
                )
        
        elif content_type == "file":
            # 파일 업로드 처리 (엑셀 일괄 업로드)
            file_info = content.get("file", {})
            file_name = file_info.get("name", "")
            file_url = file_info.get("resourceUrl", "")
            
            add_debug_log("file_message", {"name": file_name, "url": file_url})
            
            if file_name.endswith((".xlsx", ".xls")):
                background_tasks.add_task(
                    process_excel_upload,
                    user_id,
                    channel_id,
                    file_url,
                    file_name,
                    channel_type
                )
            else:
                # 엑셀이 아닌 파일
                nw_client = get_naver_works_client()
                background_tasks.add_task(
                    nw_client.send_text_message,
                    channel_id,
                    f"📎 파일 수신: {file_name}\n\n📊 엑셀 파일(.xlsx)을 보내주시면 작업일지를 일괄 등록해드려요!",
                    channel_type
                )
    
    # 빠른 응답 반환 (200 OK)
    return {"status": "ok"}


@router.get("/health")
async def webhook_health():
    """Webhook 상태 확인"""
    return {
        "status": "healthy",
        "service": "naver-works-webhook",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/test")
async def test_bot():
    """봇 설정 테스트 (개발용)"""
    try:
        nw_client = get_naver_works_client()
        
        # Private key 분석
        pk = nw_client.private_key
        pk_info = {
            "loaded": bool(pk),
            "length": len(pk) if pk else 0,
            "has_header": pk.startswith("-----BEGIN") if pk else False,
            "has_footer": pk.endswith("-----") if pk else False,
            "line_count": len(pk.split("\n")) if pk else 0,
            "first_20_chars": pk[:20] if pk else None,
            "last_20_chars": pk[-20:] if pk else None,
        }
        
        return {
            "status": "ok",
            "domain_id": nw_client.domain_id,
            "bot_id": nw_client.bot_id,
            "client_id": nw_client.client_id,
            "service_account": nw_client.service_account,
            "private_key_info": pk_info,
            "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/debug-logs")
async def get_debug_logs():
    """디버그 로그 조회 (최근 50개)"""
    return {
        "count": len(_debug_logs),
        "logs": _debug_logs
    }


@router.delete("/debug-logs")
async def clear_debug_logs():
    """디버그 로그 초기화"""
    global _debug_logs
    _debug_logs = []
    return {"status": "cleared"}


@router.post("/test-send")
async def test_send_message(channel_id: str, message: str = "테스트 메시지입니다"):
    """
    테스트 메시지 전송 (디버깅용)
    
    Args:
        channel_id: 채널 ID
        message: 전송할 메시지
    """
    try:
        nw_client = get_naver_works_client()
        
        # 토큰 발급 테스트
        add_debug_log("test_send_start", {"channel_id": channel_id, "message": message})
        
        token = await nw_client._get_access_token()
        add_debug_log("test_token_received", {"token_length": len(token) if token else 0})
        
        result = await nw_client.send_text_message(channel_id, message, "group")
        add_debug_log("test_send_result", result)
        
        return {
            "status": "ok",
            "result": result
        }
    except Exception as e:
        error_info = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        add_debug_log("test_send_error", error=str(e))
        return error_info


@router.get("/test-token")
async def test_token():
    """액세스 토큰 발급 테스트"""
    try:
        nw_client = get_naver_works_client()
        
        add_debug_log("test_token_start", {
            "client_id": nw_client.client_id,
            "service_account": nw_client.service_account,
            "private_key_loaded": bool(nw_client.private_key)
        })
        
        token = await nw_client._get_access_token()
        
        return {
            "status": "ok",
            "token_received": bool(token),
            "token_length": len(token) if token else 0,
            "token_preview": token[:20] + "..." if token else None
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/test-greeting")
async def test_morning_greeting(channel_id: str):
    """
    아침 인사 테스트 (수동 전송)
    
    Args:
        channel_id: 인사 보낼 채널 ID
    """
    try:
        from backend.app.services.scheduler import get_morning_greeting
        
        nw_client = get_naver_works_client()
        greeting = get_morning_greeting()
        
        # 채널 타입 결정
        channel_type = "user" if "-" in channel_id and len(channel_id) > 30 else "group"
        
        result = await nw_client.send_text_message(channel_id, greeting, channel_type)
        
        return {
            "status": "ok",
            "greeting": greeting,
            "channel_id": channel_id,
            "result": result
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
