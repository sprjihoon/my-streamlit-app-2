"""
네이버 웍스 Bot Webhook API (리팩토링 버전)
───────────────────────────────────────
Function Calling 방식으로 단순화된 버전입니다.
GPT가 직접 적절한 도구를 선택하고 실행합니다.
"""

import os
import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
import pandas as pd
from io import BytesIO

from backend.app.services import get_naver_works_client, get_ai_parser
from backend.app.services.bot_tools import execute_tool
from logic.db import get_connection
from backend.app.api.logs import add_log

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/naver-works", tags=["naver-works"])


# ═══════════════════════════════════════════════════════════════════
# 디버그 로그 저장
# ═══════════════════════════════════════════════════════════════════

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
    
    if error:
        logger.error(f"[{event}] {error}")
    else:
        logger.info(f"[{event}] {data}")




# ═══════════════════════════════════════════════════════════════════
# 메시지 처리 메인 로직
# ═══════════════════════════════════════════════════════════════════

async def process_message(
    user_id: str,
    channel_id: str,
    text: str,
    channel_type: str = "group",
    user_name: str = None
):
    """
    메시지 처리 메인 로직 (Function Calling + 멀티턴 대화 방식)
    
    GPT가 직접 적절한 도구를 선택하고 실행합니다.
    불완전한 정보는 대화 상태에 저장되고, 후속 메시지에서 보완됩니다.
    """
    add_debug_log("process_message_start", {
        "user_id": user_id,
        "channel_id": channel_id,
        "text": text,
        "channel_type": channel_type
    })
    
    try:
        nw_client = get_naver_works_client()
    except Exception as e:
        add_debug_log("nw_client_error", error=str(e))
        return
    
    # 사용자 이름 조회
    if not user_name:
        try:
            user_name = await nw_client.get_user_name(user_id)
        except:
            user_name = None
    
    try:
        ai_parser = get_ai_parser()
    except Exception as e:
        add_debug_log("ai_parser_error", error=str(e))
        await nw_client.send_text_message(channel_id, f"❌ AI 초기화 오류: {str(e)}", channel_type)
        return
    
    # 메시지 처리 (대화 상태 관리는 ai_parser 내부에서 처리)
    try:
        result = await ai_parser.process_message(
            message=text,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id
        )
        
        add_debug_log("process_result", {
            "tool_called": result.get("tool_called"),
            "response_length": len(result.get("response", "")),
            "waiting_for_info": result.get("waiting_for_info", False)
        })
        
        response = result.get("response", "")
        
        if response:
            await nw_client.send_text_message(channel_id, response, channel_type)
        else:
            await nw_client.send_text_message(channel_id, "🤖 응답을 생성하지 못했습니다.", channel_type)
    
    except Exception as e:
        add_debug_log("process_error", error=f"{type(e).__name__}: {str(e)}")
        await nw_client.send_text_message(
            channel_id,
            f"❌ 처리 중 오류: {str(e)}",
            channel_type
        )


async def process_excel_upload(
    user_id: str,
    channel_id: str,
    file_url: str,
    file_name: str,
    channel_type: str
):
    """엑셀 파일 업로드 처리"""
    import httpx
    
    add_debug_log("excel_upload_start", {"file_name": file_name})
    
    try:
        nw_client = get_naver_works_client()
        
        await nw_client.send_text_message(channel_id, f"📊 '{file_name}' 처리 중...", channel_type)
        
        # 파일 다운로드
        token = await nw_client._get_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(file_url, headers=headers)
            
            if response.status_code != 200:
                await nw_client.send_text_message(
                    channel_id,
                    f"❌ 파일 다운로드 실패 (상태: {response.status_code})",
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
                f"❌ 필수 컬럼 누락: {', '.join(missing_cols)}",
                channel_type
            )
            return
        
        # 데이터 처리
        saved_count = 0
        total_amount = 0
        user_name = await nw_client.get_user_name(user_id) if user_id else None
        
        for _, row in df.iterrows():
            try:
                날짜 = row.get("날짜")
                if pd.isna(날짜):
                    continue
                
                if hasattr(날짜, 'strftime'):
                    날짜 = 날짜.strftime("%Y-%m-%d")
                else:
                    날짜 = str(날짜)[:10]
                
                업체명 = str(row.get("업체명", "")).strip()
                분류 = str(row.get("분류", "")).strip()
                단가 = int(row.get("단가", 0) or 0)
                수량 = int(row.get("수량", 1) or 1)
                비고 = str(row.get("비고", "") or row.get("비고1", "") or "")
                
                if not 업체명 or not 분류:
                    continue
                
                합계 = 단가 * 수량
                
                # 저장
                result = execute_tool("save_work_log", {
                    "vendor": 업체명,
                    "work_type": 분류,
                    "unit_price": 단가,
                    "qty": 수량,
                    "date": 날짜,
                    "remark": f"[엑셀] {비고}".strip()
                }, user_id, user_name)
                
                if result.get("success"):
                    saved_count += 1
                    total_amount += 합계
            
            except Exception as e:
                add_debug_log("excel_row_error", error=str(e))
        
        # 결과 메시지
        result_msg = f"📊 엑셀 업로드 완료\n━━━━━━━━━━━━━━━━━━━━\n\n"
        result_msg += f"📎 파일: {file_name}\n"
        result_msg += f"✅ 저장: {saved_count}건\n"
        result_msg += f"💰 합계: {total_amount:,}원"
        
        await nw_client.send_text_message(channel_id, result_msg, channel_type)
    
    except Exception as e:
        add_debug_log("excel_upload_error", error=str(e))
        try:
            nw_client = get_naver_works_client()
            await nw_client.send_text_message(channel_id, f"❌ 엑셀 처리 오류: {str(e)}", channel_type)
        except:
            pass


async def send_welcome_message(channel_id: str):
    """봇 초대 시 환영 메시지"""
    try:
        nw_client = get_naver_works_client()
        
        welcome_msg = (
            "👋 안녕하세요! 작업일지봇입니다!\n\n"
            "💬 자연어로 편하게 대화하세요!\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📝 입력: 틸리언 하차 3만원\n"
            "🔍 조회: 오늘 작업 보여줘\n"
            "✏️ 수정: 취소 / 수정해줘\n"
            "📊 통계: 이번달 총 얼마?\n\n"
            "💡 정보가 부족하면 물어봐요:\n"
            '   "틸리언 하차" → "단가가 얼마예요?"\n\n'
            "📖 도움말: '도움말' 입력\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "무엇이든 물어보세요! 🤖"
        )
        
        await nw_client.send_text_message(channel_id, welcome_msg, "group")
        add_debug_log("welcome_message_sent", {"channel_id": channel_id})
    
    except Exception as e:
        add_debug_log("welcome_message_error", error=str(e))


# ═══════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post("/webhook")
async def naver_works_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """네이버 웍스 Bot Webhook 엔드포인트"""
    body = await request.body()
    add_debug_log("webhook_received", {"body_length": len(body)})
    
    try:
        payload = json.loads(body)
        add_debug_log("webhook_payload", payload)
    except json.JSONDecodeError as e:
        add_debug_log("webhook_json_error", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = payload.get("type")
    
    # URL 검증
    if event_type == "url_verification":
        return {"type": "url_verification"}
    
    # 봇 초대
    if event_type == "join":
        source = payload.get("source", {})
        channel_id = source.get("channelId", "")
        if channel_id:
            background_tasks.add_task(send_welcome_message, channel_id)
        return {"status": "ok"}
    
    # 메시지 이벤트
    if event_type == "message":
        source = payload.get("source", {})
        content = payload.get("content", {})
        
        user_id = source.get("userId", "")
        channel_id = source.get("channelId", "")
        channel_type = "group" if channel_id else "user"
        if not channel_id:
            channel_id = user_id
        
        content_type = content.get("type", "")
        
        if content_type == "text":
            text = content.get("text", "")
            if text:
                background_tasks.add_task(
                    process_message,
                    user_id, channel_id, text, channel_type
                )
        
        elif content_type == "file":
            file_info = content.get("file", {})
            file_name = file_info.get("name", "")
            file_url = file_info.get("resourceUrl", "")
            
            if file_name.endswith((".xlsx", ".xls")):
                background_tasks.add_task(
                    process_excel_upload,
                    user_id, channel_id, file_url, file_name, channel_type
                )
            else:
                nw_client = get_naver_works_client()
                background_tasks.add_task(
                    nw_client.send_text_message,
                    channel_id,
                    f"📎 파일 수신: {file_name}\n\n📊 엑셀 파일(.xlsx)을 보내주시면 작업일지를 일괄 등록해드려요!",
                    channel_type
                )
    
    return {"status": "ok"}


@router.get("/health")
async def webhook_health():
    """상태 확인"""
    return {
        "status": "healthy",
        "service": "naver-works-webhook",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/test")
async def test_bot():
    """봇 설정 테스트"""
    try:
        nw_client = get_naver_works_client()
        
        return {
            "status": "ok",
            "domain_id": nw_client.domain_id,
            "bot_id": nw_client.bot_id,
            "client_id": nw_client.client_id,
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
    """디버그 로그 조회"""
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
    """테스트 메시지 전송"""
    try:
        nw_client = get_naver_works_client()
        result = await nw_client.send_text_message(channel_id, message, "group")
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/test-token")
async def test_token():
    """액세스 토큰 발급 테스트"""
    try:
        nw_client = get_naver_works_client()
        token = await nw_client._get_access_token()
        return {
            "status": "ok",
            "token_received": bool(token),
            "token_length": len(token) if token else 0
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
