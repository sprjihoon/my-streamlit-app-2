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
        return cursor.lastrowid


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


def delete_work_log(log_id: int) -> bool:
    """작업일지 삭제"""
    with get_connection() as con:
        con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
        con.commit()
        return True


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
    
    # 인사/도움말 처리
    greetings = ["안녕", "하이", "hi", "hello", "헬로", "ㅎㅇ"]
    help_commands = ["도움말", "도움", "help", "?", "사용법"]
    test_commands = ["테스트", "test", "핑", "ping"]
    
    if any(g in text_lower for g in greetings):
        try:
            await nw_client.send_text_message(
                channel_id,
                "👋 안녕하세요! 작업일지봇입니다.\n\n"
                "📝 작업 내용을 입력하면 자동으로 저장해드려요.\n"
                "예: 'A업체 1톤하차 50000원'\n\n"
                "'도움말'을 입력하면 사용법을 확인할 수 있어요.",
                channel_type
            )
        except Exception as e:
            add_debug_log("greeting_send_error", error=str(e))
        return
    
    if any(h in text_lower for h in help_commands):
        try:
            await nw_client.send_text_message(
                channel_id,
                "📚 작업일지봇 사용법\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ 작업 입력 예시:\n"
                "• A업체 1톤하차 50000원\n"
                "• B업체 양품화 3개 10000원\n"
                "• C업체 바코드부착 100개 500원\n\n"
                "📌 명령어:\n"
                "• 취소 - 방금 저장한 작업 삭제 (30초 내)\n"
                "• 도움말 - 사용법 보기\n\n"
                "💡 업체명, 작업종류, 금액을 말씀해주시면\n"
                "자동으로 인식해서 저장합니다!",
                channel_type
            )
        except Exception as e:
            add_debug_log("help_send_error", error=str(e))
        return
    
    if any(t in text_lower for t in test_commands):
        try:
            await nw_client.send_text_message(
                channel_id,
                f"🏓 퐁! 봇이 정상 작동 중입니다.\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                channel_type
            )
        except Exception as e:
            add_debug_log("test_send_error", error=str(e))
        return
    
    # 취소 명령 처리 (최근 저장 삭제)
    if text_lower in ["취소", "cancel", "삭제"]:
        # 최근 저장된 레코드 확인
        recent = _recent_saves.get(user_id)
        if recent and datetime.now().timestamp() < recent.get("expires_at", 0):
            log_id = recent.get("log_id")
            delete_work_log(log_id)
            del _recent_saves[user_id]
            await nw_client.send_text_message(
                channel_id,
                "🚫 방금 저장한 작업일지가 삭제되었습니다.",
                channel_type
            )
        else:
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(
                channel_id,
                "🚫 취소되었습니다.",
                channel_type
            )
        return
    
    # 중복 저장 확인 응답 처리
    existing_state = conv_manager.get_state(user_id)
    if existing_state and existing_state.get("last_question", "").startswith("⚠️ 중복"):
        if text_lower in ["예", "네", "yes", "y", "ㅇㅇ", "응"]:
            # 중복이어도 저장
            data = existing_state.get("pending_data", {})
            try:
                record_id = save_work_log(data, user_id, user_name)
                conv_manager.clear_state(user_id)
                
                # 취소 가능 시간 설정 (30초)
                _recent_saves[user_id] = {
                    "log_id": record_id,
                    "expires_at": datetime.now().timestamp() + 30
                }
                
                response_msg = generate_success_message(data, record_id)
                await nw_client.send_text_message(channel_id, response_msg, channel_type)
            except Exception as e:
                await nw_client.send_text_message(
                    channel_id,
                    f"❌ 저장 중 오류가 발생했습니다: {str(e)}",
                    channel_type
                )
            return
        elif text_lower in ["아니", "아니요", "no", "n", "ㄴㄴ"]:
            conv_manager.clear_state(user_id)
            await nw_client.send_text_message(
                channel_id,
                "🚫 저장하지 않았습니다.",
                channel_type
            )
            return
    
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
        
        # 중복 없음 - 바로 저장
        try:
            record_id = save_work_log(data, user_id, user_name)
            
            # 대화 상태 초기화
            conv_manager.clear_state(user_id)
            
            # 취소 가능 시간 설정 (30초)
            _recent_saves[user_id] = {
                "log_id": record_id,
                "expires_at": datetime.now().timestamp() + 30
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
        
        # 아무것도 인식 못한 경우 기본 응답
        if not data or (not data.get("vendor") and not data.get("work_type") and not data.get("unit_price")):
            add_debug_log("no_data_parsed", {"original_text": text})
            try:
                await nw_client.send_text_message(
                    channel_id,
                    f"🤖 메시지를 받았어요: \"{text[:50]}{'...' if len(text) > 50 else ''}\"\n\n"
                    "작업일지를 저장하시려면 아래 형식으로 입력해주세요:\n"
                    "예: 'A업체 1톤하차 50000원'\n\n"
                    "'도움말'을 입력하면 자세한 사용법을 확인할 수 있어요.",
                    channel_type
                )
            except Exception as e:
                add_debug_log("default_response_error", error=str(e))
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
