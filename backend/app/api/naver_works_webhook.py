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

# 최근 저장된 레코드 캐시 (취소용)
# {user_id: {"log_id": id, "expires_at": timestamp}}
_recent_saves: Dict[str, Dict[str, Any]] = {}


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


def get_user_recent_log(user_id: str) -> Optional[Dict[str, Any]]:
    """사용자의 가장 최근 작업일지 조회"""
    with get_connection() as con:
        row = con.execute(
            """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log 
               WHERE works_user_id = ?
               ORDER BY id DESC LIMIT 1""",
            (user_id,)
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
                "작성자": row[8],
            }
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
    global _recent_saves
    
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
    
    # 작업일지 조회 응답 대기 중
    if existing_state and existing_state.get("last_question") == "📋 작업일지 조회":
        pending = existing_state.get("pending_data", {})
        start_date = pending.get("start_date")
        end_date = pending.get("end_date")
        period_name = pending.get("period_name")
        
        # AI로 의도 파악
        intent_context = {
            "last_question": "1번 텍스트로 보기, 2번 파일로 다운로드 중 선택",
            "options": ["1: 텍스트로 보기", "2: 파일로 다운로드"],
            "pending_data": pending
        }
        intent_result = await ai_parser.parse_intent(text, intent_context)
        add_debug_log("summary_intent", data=intent_result)
        
        intent = intent_result.get("intent")
        value = intent_result.get("value")
        
        if intent == "select_option" and value == "1":
            # 텍스트로 출력
            logs = get_work_logs_by_period(start_date, end_date)
            by_vendor = {}
            total_amount = 0
            for log in logs:
                vendor = log.get("업체명", "기타")
                if vendor not in by_vendor:
                    by_vendor[vendor] = []
                by_vendor[vendor].append(log)
                total_amount += log.get("합계", 0) or 0
            
            msg = f"📋 {period_name} 작업일지\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for vendor, vlogs in by_vendor.items():
                vendor_total = sum(l.get("합계", 0) or 0 for l in vlogs)
                msg += f"📦 {vendor} ({len(vlogs)}건, {vendor_total:,}원)\n"
                for log in vlogs[:10]:
                    msg += f"  • {log.get('날짜', '-')} {log.get('분류', '-')} "
                    if log.get('수량', 1) > 1:
                        msg += f"{log.get('수량')}개 "
                    msg += f"{log.get('합계', 0):,}원\n"
                if len(vlogs) > 10:
                    msg += f"  ... 외 {len(vlogs) - 10}건\n"
                msg += "\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━\n📊 총 {len(logs)}건 | 💰 {total_amount:,}원"
            
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, msg, channel_type)
            return
            
        elif intent == "select_option" and value == "2":
            # 파일 다운로드 링크
            import os
            base_url = os.getenv("BACKEND_URL", "https://my-streamlit-app-2-production.up.railway.app")
            download_url = f"{base_url}/work-log/export?start_date={start_date}&end_date={end_date}&format=excel"
            
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(
                channel_id,
                f"📥 작업일지 다운로드\n\n📅 기간: {period_name}\n📊 건수: {pending.get('log_count', 0)}건\n💰 금액: {pending.get('total_amount', 0):,}원\n\n아래 링크를 클릭하세요:\n📎 {download_url}",
                channel_type
            )
            return
    
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
                _recent_saves[user_id] = {
                    "log_id": record_id,
                    "expires_at": datetime.now().timestamp() + 30,
                    "log_info": data
                }
                response_msg = generate_success_message(data, record_id)
                await nw_client.send_text_message(channel_id, response_msg, channel_type)
            except Exception as e:
                await nw_client.send_text_message(channel_id, f"❌ 저장 오류: {str(e)}", channel_type)
            return
        elif intent_result.get("intent") == "confirm_no":
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(channel_id, "🚫 저장하지 않았습니다.", channel_type)
            return
    
    # ═══════════════════════════════════════════════════════════════════
    # 2단계: AI로 메시지 의도 분류
    # ═══════════════════════════════════════════════════════════════════
    message_class = await ai_parser.classify_message(text, user_name, has_pending_state)
    add_debug_log("message_classified", data=message_class)
    
    intent = message_class.get("intent", "chat")
    intent_data = message_class.get("data", {})
    confidence = message_class.get("confidence", 0.0)
    
    # ═══════════════════════════════════════════════════════════════════
    # 3단계: 의도별 처리
    # ═══════════════════════════════════════════════════════════════════
    
    # 인사
    if intent == "greeting":
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_greeting = "좋은 아침이에요! ☀️"
        elif 12 <= hour < 18:
            time_greeting = "좋은 오후예요! 🌤️"
        elif 18 <= hour < 22:
            time_greeting = "수고하셨어요! 🌆"
        else:
            time_greeting = "늦은 시간까지 수고하세요! 🌙"
        
        name_part = f"{user_name}님, " if user_name else ""
        await nw_client.send_text_message(
            channel_id,
            f"👋 {name_part}{time_greeting}\n작업일지봇이에요! 자유롭게 말씀하세요 😊",
            channel_type
        )
        return
    
    # 도움말
    if intent == "help":
        await nw_client.send_text_message(
            channel_id,
            "📚 작업일지봇 사용법\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ 작업 입력:\n"
            "• 틸리언 1톤하차 3만원\n"
            "• 나블리 양품화 20개 800원\n\n"
            "📋 기간 조회:\n"
            "• 오늘/이번주/지난달 작업 정리해줘\n"
            "• 1월 20일부터 25일까지\n\n"
            "🔍 검색:\n"
            "• 틸리언 작업 보여줘\n"
            "• 2월 4일 나블리 있어?\n"
            "• 3만원짜리 뭐있어?\n\n"
            "📊 통계:\n"
            "• 이번달 총 얼마야?\n"
            "• 오늘 몇건 했어?\n"
            "• 가장 많이 일한 업체\n\n"
            "✏️ 수정/삭제:\n"
            "• 방금꺼 취소/수정해줘\n"
            "• 오늘 틸리언 3만원 삭제해줘\n\n"
            "💡 자연어로 편하게 말씀하세요!",
            channel_type
        )
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
        conv_manager.set_state(user_id=user_id, channel_id=channel_id, pending_data={"chat_mode": True}, missing=[], last_question="대화모드")
        await nw_client.send_text_message(
            channel_id,
            "💬 대화모드 시작! 무엇이든 물어보세요 😊\n\n📝 작업일지 형식은 자동 저장돼요!\n• '작업모드' 입력하면 종료",
            channel_type
        )
        return
    
    # 대화모드 종료
    if intent == "chat_mode_end":
        conv_manager.clear_state(user_id)
        await nw_client.send_text_message(channel_id, "📋 작업모드로 돌아왔습니다!", channel_type)
        return
    
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
        recent = _recent_saves.get(user_id)
        if recent and datetime.now().timestamp() < recent.get("expires_at", 0):
            log_info = recent.get("log_info", {})
            conv_manager.set_state(
                user_id=user_id, channel_id=channel_id,
                pending_data={"edit_mode": True, "log_id": recent.get("log_id"), "original": log_info},
                missing=[], last_question="수정 대기"
            )
            await nw_client.send_text_message(
                channel_id,
                f"✏️ 수정할 내용을 입력해주세요.\n\n현재: {log_info.get('vendor', '-')} {log_info.get('work_type', '-')} {log_info.get('total', 0):,}원",
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
                    # 선택 옵션 제공
                    total_amount = sum(l.get("합계", 0) or 0 for l in logs)
                    
                    conv_manager.set_state(
                        user_id=user_id,
                        channel_id=channel_id,
                        pending_data={
                            "summary_mode": True,
                            "start_date": start_date,
                            "end_date": end_date,
                            "period_name": period_name,
                            "log_count": len(logs),
                            "total_amount": total_amount,
                        },
                        missing=[],
                        last_question="📋 작업일지 조회"
                    )
                    
                    await nw_client.send_text_message(
                        channel_id,
                        f"📋 {period_name} 작업일지\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📊 총 {len(logs)}건 | 💰 {total_amount:,}원\n\n"
                        f"어떻게 보여드릴까요?\n"
                        f"1️⃣ 텍스트로 보기\n"
                        f"2️⃣ 파일로 다운로드 (링크)\n\n"
                        f"원하시는 방식을 말씀해주세요.",
                        channel_type
                    )
                return
            except Exception as e:
                add_debug_log("summary_error", error=str(e))
                await nw_client.send_text_message(
                    channel_id,
                    f"❌ 작업일지 조회 중 오류: {str(e)}",
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
    # 4단계: 작업일지 입력 또는 일반 대화 처리
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
            
            # 취소/수정 가능 시간 설정 (30초) - log_info 포함
            _recent_saves[user_id] = {
                "log_id": record_id,
                "expires_at": datetime.now().timestamp() + 30,
                "log_info": {
                    "vendor": data.get("vendor", ""),
                    "work_type": data.get("work_type", ""),
                    "qty": data.get("qty", 1),
                    "unit_price": data.get("unit_price", 0),
                    "total": data.get("qty", 1) * data.get("unit_price", 0),
                }
            }
            
            # 확인 메시지 생성 및 전송
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
        
        # 아무것도 인식 못한 경우 - GPT 대화 모드
        if not data or (not data.get("vendor") and not data.get("work_type") and not data.get("unit_price")):
            add_debug_log("no_data_parsed_chat_mode", {"original_text": text})
            try:
                # GPT에게 자유 대화 요청
                chat_response = await ai_parser.chat_response(text, user_name)
                add_debug_log("chat_response", {"response": chat_response})
                
                await nw_client.send_text_message(
                    channel_id,
                    chat_response,
                    channel_type
                )
            except Exception as e:
                add_debug_log("chat_response_error", error=str(e))
                # GPT 대화 실패 시 기본 응답
                try:
                    await nw_client.send_text_message(
                        channel_id,
                        f"🤖 메시지를 받았어요!\n\n"
                        "작업일지를 저장하시려면:\n"
                        "예: 'A업체 1톤하차 50000원'\n\n"
                        "'도움말'을 입력하면 사용법을 확인할 수 있어요.",
                        channel_type
                    )
                except:
                    pass
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
