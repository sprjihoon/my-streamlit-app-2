"""
AI 기반 작업일지 파싱 모듈 (Function Calling 방식)
───────────────────────────────────────
OpenAI GPT를 사용하여 자연어 메시지를 처리합니다.
Function Calling을 통해 GPT가 직접 적절한 도구를 선택하고 실행합니다.
멀티턴 대화를 통해 불완전한 정보를 보완합니다.
"""

import os
import json
import unicodedata
from typing import Optional, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI

from backend.app.services.bot_tools import TOOLS, execute_tool, get_db_context_for_ai
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection

# .env 파일 로드
load_dotenv()


# ═══════════════════════════════════════════════════════════════════
# 시스템 프롬프트 (단순화됨)
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """당신은 물류센터 작업일지 관리 봇입니다.
사용자의 자연어 메시지를 이해하고, 적절한 도구(function)를 호출하거나 직접 대화합니다.

## 오늘 날짜
{today} ({weekday})

{db_context}

## 핵심 역할
1. **작업일지 입력**: "틸리언 1톤하차 3만원" → save_work_log 호출
2. **조회/검색**: "오늘 작업 보여줘" → search_work_logs 호출
3. **통계**: "이번달 총 얼마?" → get_work_log_stats 호출
4. **삭제**: "취소", "방금거 삭제" → delete_work_log 호출
5. **수정**: "수정해줘" → update_work_log 호출
6. **불완전 정보**: 필수 정보 누락 시 → ask_missing_info 호출
7. **일반 대화**: 도구 없이 직접 응답

## 금액 해석 규칙
- 만 = 10000, 천 = 1000
- "3만원" → 30000
- "만원" → 10000
- "5천원" → 5000

## 날짜 해석 규칙
- "오늘" → {today}
- "어제" → {yesterday}
- "이번주" → 이번 주 월요일 ~ 오늘
- "지난주" → 지난 주 월요일 ~ 일요일
- "이번달" → 이번 달 1일 ~ 오늘
- "5일 6일" → 이번 달 5일 ~ 6일

## 응답 스타일
- 친근하고 간결하게
- 이모지 적절히 사용
- 한국어로 응답

## 불완전 정보 처리 (매우 중요!)
작업일지 입력 시 필수 정보: **업체명, 작업종류, 단가**
- "틸리언 하차" (단가 없음) → ask_missing_info 호출 (missing: ["unit_price"])
- "3만원" (업체/작업 없음) → ask_missing_info 호출 (missing: ["vendor", "work_type"])
- "하차 3만원" (업체 없음) → ask_missing_info 호출 (missing: ["vendor"])

⚠️ 불완전한 정보로 save_work_log를 호출하지 마세요! 먼저 ask_missing_info로 부족한 정보를 물어보세요.

## 이전 대화 맥락
{pending_context}

## 중요
- 사용자가 작업일지 형식("업체명 작업 금액")으로 말하면 save_work_log 호출
- 정보가 부족하면 ask_missing_info 호출하여 물어보기
- "취소", "삭제", "지워줘" 등은 delete_work_log (delete_recent=true)
- "수정", "고쳐줘", "바꿔줘" 등은 update_work_log (update_recent=true)
- 도움말/사용법 요청은 get_help 호출
- 조회/검색은 search_work_logs 또는 get_work_log_stats
- 인보이스/청구금액 관련은 get_invoice_stats 호출
- 일반 대화나 인사는 도구 호출 없이 직접 응답

## ⚠️ 대화 맥락 이해 (매우 중요!)
- 금액만 언급하면서 "?", "잘못됐", "틀린", "이상해" 등이 포함되면 → 이전 답변에 대한 **의문/피드백**임
- "3100만원? 잘못된 값같네" → 작업 입력이 아님! 이전 답변을 의심하는 것
- "진짜?", "맞아?", "확실해?" → 확인 요청
- 이런 경우 도구 호출 없이 "확인해볼게요" 또는 설명으로 응답
"""


# ═══════════════════════════════════════════════════════════════════
# AI 파서 클래스 (단순화됨)
# ═══════════════════════════════════════════════════════════════════

class AIParser:
    """AI 기반 작업일지 파서 (Function Calling + 멀티턴 대화 방식)"""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"
        
        # 별칭 매핑 캐시
        self._alias_cache: Optional[Dict[str, str]] = None
        self._alias_cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 300
        
        # 대화 상태 관리자
        self.conv_manager = get_conversation_manager()
    
    def _get_system_prompt(self, pending_context: str = "") -> str:
        """시스템 프롬프트 생성"""
        today = datetime.now()
        yesterday = today.replace(day=today.day - 1) if today.day > 1 else today
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        
        if not pending_context:
            pending_context = "(이전 대화 맥락 없음)"
        
        return SYSTEM_PROMPT.format(
            today=today.strftime("%Y-%m-%d"),
            yesterday=yesterday.strftime("%Y-%m-%d"),
            weekday=weekdays[today.weekday()],
            db_context=get_db_context_for_ai(),
            pending_context=pending_context
        )
    
    def _format_pending_context(self, state: Dict) -> str:
        """대기 중인 상태를 프롬프트용 문자열로 변환"""
        if not state:
            return ""
        
        pending_data = state.get("pending_data", {})
        missing = state.get("missing", [])
        last_question = state.get("last_question", "")
        
        if not pending_data:
            return ""
        
        parts = []
        parts.append("⚠️ 이전 대화에서 불완전한 작업일지 정보가 있습니다:")
        
        if pending_data.get("vendor"):
            parts.append(f"  - 업체명: {pending_data['vendor']}")
        if pending_data.get("work_type"):
            parts.append(f"  - 작업종류: {pending_data['work_type']}")
        if pending_data.get("unit_price"):
            parts.append(f"  - 단가: {pending_data['unit_price']:,}원")
        if pending_data.get("qty"):
            parts.append(f"  - 수량: {pending_data['qty']}")
        if pending_data.get("date"):
            parts.append(f"  - 날짜: {pending_data['date']}")
        
        if missing:
            field_names = {"vendor": "업체명", "work_type": "작업종류", "unit_price": "단가", "qty": "수량"}
            missing_kr = [field_names.get(m, m) for m in missing]
            parts.append(f"  - 누락된 정보: {', '.join(missing_kr)}")
        
        if last_question:
            parts.append(f"  - 마지막 질문: {last_question}")
        
        parts.append("")
        parts.append("사용자가 누락된 정보(예: '3만원', '틸리언')를 제공하면 기존 정보와 합쳐서 complete_pending_entry를 호출하세요.")
        
        return "\n".join(parts)
    
    def _get_alias_map(self) -> Dict[str, str]:
        """별칭 매핑 가져오기 (캐시 사용)"""
        now = datetime.now()
        
        if (self._alias_cache is None or
            self._alias_cache_time is None or
            (now - self._alias_cache_time).seconds > self._cache_ttl_seconds):
            self._alias_cache = self._load_vendor_aliases()
            self._alias_cache_time = now
        
        return self._alias_cache or {}
    
    def _load_vendor_aliases(self) -> Dict[str, str]:
        """별칭 테이블에서 매핑 로드"""
        alias_map = {}
        try:
            with get_connection() as con:
                # aliases 테이블
                rows = con.execute(
                    "SELECT alias, vendor FROM aliases WHERE file_type = 'work_log'"
                ).fetchall()
                for alias, vendor in rows:
                    if alias and vendor:
                        alias_map[self._normalize(alias)] = vendor
                
                # vendors 테이블
                vendor_rows = con.execute(
                    "SELECT vendor, name FROM vendors WHERE active != 'NO' OR active IS NULL"
                ).fetchall()
                for vendor, name in vendor_rows:
                    if vendor:
                        alias_map[self._normalize(vendor)] = vendor
                        if name:
                            alias_map[self._normalize(name)] = vendor
        except Exception as e:
            print(f"Warning: Could not load vendor aliases: {e}")
        return alias_map
    
    def _normalize(self, text: str) -> str:
        """텍스트 정규화"""
        if not text:
            return ""
        normalized = unicodedata.normalize('NFKC', str(text).strip())
        normalized = ' '.join(normalized.split())
        return normalized.lower()
    
    def _map_vendor_alias(self, vendor_name: str) -> str:
        """입력된 업체명을 실제 vendor로 변환"""
        if not vendor_name:
            return vendor_name
        
        alias_map = self._get_alias_map()
        normalized = self._normalize(vendor_name)
        
        # 정확히 일치
        if normalized in alias_map:
            return alias_map[normalized]
        
        # 부분 일치
        for alias, vendor in alias_map.items():
            if alias in normalized or normalized in alias:
                return vendor
        
        return vendor_name
    
    async def process_message(
        self,
        message: str,
        user_id: str,
        user_name: str = None,
        channel_id: str = None,
        conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        메시지를 처리하고 결과 반환 (Function Calling + 멀티턴 대화)
        
        Args:
            message: 사용자 메시지
            user_id: 사용자 ID
            user_name: 사용자 이름
            channel_id: 채널 ID
            conversation_history: 이전 대화 이력 (선택)
        
        Returns:
            {
                "response": "사용자에게 보여줄 응답",
                "tool_called": "호출된 도구 이름 또는 None",
                "tool_result": "도구 실행 결과 또는 None"
            }
        """
        # 대기 중인 대화 상태 확인
        pending_state = self.conv_manager.get_state(user_id)
        pending_context = self._format_pending_context(pending_state)
        
        # 확장된 도구 목록 (ask_missing_info, complete_pending_entry 추가)
        extended_tools = TOOLS + [
            {
                "type": "function",
                "function": {
                    "name": "ask_missing_info",
                    "description": "작업일지 저장에 필요한 정보가 부족할 때 사용자에게 물어봅니다. 부족한 정보를 물어보면서 이미 파악한 정보는 저장합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vendor": {"type": "string", "description": "파악된 업체명 (없으면 생략)"},
                            "work_type": {"type": "string", "description": "파악된 작업종류 (없으면 생략)"},
                            "unit_price": {"type": "integer", "description": "파악된 단가 (없으면 생략)"},
                            "qty": {"type": "integer", "description": "파악된 수량 (없으면 생략)"},
                            "date": {"type": "string", "description": "파악된 날짜 (없으면 생략)"},
                            "remark": {"type": "string", "description": "파악된 비고 (없으면 생략)"},
                            "missing": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "누락된 필드 목록 (vendor, work_type, unit_price 중)"
                            },
                            "question": {"type": "string", "description": "사용자에게 물어볼 질문"}
                        },
                        "required": ["missing", "question"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_pending_entry",
                    "description": "이전 대화에서 불완전했던 작업일지에 누락된 정보를 추가하여 완성합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vendor": {"type": "string", "description": "추가된 업체명"},
                            "work_type": {"type": "string", "description": "추가된 작업종류"},
                            "unit_price": {"type": "integer", "description": "추가된 단가"},
                            "qty": {"type": "integer", "description": "추가된 수량"},
                            "date": {"type": "string", "description": "추가된 날짜"},
                            "remark": {"type": "string", "description": "추가된 비고"}
                        }
                    }
                }
            }
        ]
        
        # 메시지 구성
        messages = [
            {"role": "system", "content": self._get_system_prompt(pending_context)}
        ]
        
        # 대화 이력 추가 (있으면)
        if conversation_history:
            messages.extend(conversation_history[-6:])
        
        # 사용자 메시지 추가
        user_msg = message
        if user_name:
            user_msg = f"[{user_name}] {message}"
        messages.append({"role": "user", "content": user_msg})
        
        try:
            # GPT 호출 (Function Calling 포함)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=extended_tools,
                tool_choice="auto",
                temperature=0.3
            )
            
            assistant_message = response.choices[0].message
            
            # 도구 호출이 있는 경우
            if assistant_message.tool_calls:
                tool_call = assistant_message.tool_calls[0]
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                # 업체명 별칭 매핑 적용
                if "vendor" in tool_args:
                    tool_args["vendor"] = self._map_vendor_alias(tool_args["vendor"])
                
                # ─────────────────────────────────────
                # 특수 도구 처리: ask_missing_info
                # ─────────────────────────────────────
                if tool_name == "ask_missing_info":
                    # 불완전한 정보 저장
                    pending_data = {
                        k: v for k, v in tool_args.items()
                        if k in ["vendor", "work_type", "unit_price", "qty", "date", "remark"] and v
                    }
                    missing = tool_args.get("missing", [])
                    question = tool_args.get("question", "추가 정보를 알려주세요.")
                    
                    self.conv_manager.set_state(
                        user_id=user_id,
                        channel_id=channel_id or "",
                        pending_data=pending_data,
                        missing=missing,
                        last_question=question
                    )
                    
                    return {
                        "response": f"❓ {question}",
                        "tool_called": tool_name,
                        "tool_result": {"pending_data": pending_data, "missing": missing},
                        "waiting_for_info": True
                    }
                
                # ─────────────────────────────────────
                # 특수 도구 처리: complete_pending_entry
                # ─────────────────────────────────────
                if tool_name == "complete_pending_entry":
                    if not pending_state:
                        return {
                            "response": "🤔 이전 대화 내용을 찾을 수 없어요. 처음부터 다시 말씀해주세요.",
                            "tool_called": tool_name,
                            "tool_result": None
                        }
                    
                    # 기존 데이터와 새 데이터 병합
                    merged_data = pending_state.get("pending_data", {}).copy()
                    for key, value in tool_args.items():
                        if value:
                            if key == "vendor":
                                value = self._map_vendor_alias(value)
                            merged_data[key] = value
                    
                    # 대화 상태 클리어
                    self.conv_manager.clear_state(user_id)
                    
                    # 필수 필드 확인
                    required = ["vendor", "work_type", "unit_price"]
                    still_missing = [f for f in required if not merged_data.get(f)]
                    
                    if still_missing:
                        field_names = {"vendor": "업체명", "work_type": "작업종류", "unit_price": "단가"}
                        missing_kr = [field_names[f] for f in still_missing]
                        return {
                            "response": f"❓ 아직 {', '.join(missing_kr)}이(가) 필요해요.",
                            "tool_called": tool_name,
                            "tool_result": {"merged_data": merged_data, "still_missing": still_missing}
                        }
                    
                    # save_work_log 실행
                    tool_result = execute_tool("save_work_log", merged_data, user_id, user_name)
                    
                    if tool_result.get("success"):
                        return {
                            "response": f"✅ {tool_result.get('message', '저장완료!')}",
                            "tool_called": "save_work_log",
                            "tool_result": tool_result
                        }
                    else:
                        return {
                            "response": f"❌ 저장 실패: {tool_result.get('error', '알 수 없는 오류')}",
                            "tool_called": "save_work_log",
                            "tool_result": tool_result
                        }
                
                # ─────────────────────────────────────
                # 일반 도구 처리
                # ─────────────────────────────────────
                
                # 저장 성공 시 대화 상태 클리어
                if tool_name == "save_work_log":
                    self.conv_manager.clear_state(user_id)
                
                # 도구 실행
                tool_result = execute_tool(tool_name, tool_args, user_id, user_name)
                
                # 도구 결과를 GPT에게 전달하여 최종 응답 생성
                # assistant_message를 딕셔너리로 변환 (Pydantic 직렬화 오류 방지)
                assistant_msg_dict = {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ] if assistant_message.tool_calls else None
                }
                messages.append(assistant_msg_dict)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })
                
                # 최종 응답 생성
                final_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.5
                )
                
                return {
                    "response": final_response.choices[0].message.content,
                    "tool_called": tool_name,
                    "tool_result": tool_result
                }
            
            # 도구 호출 없이 직접 응답
            return {
                "response": assistant_message.content,
                "tool_called": None,
                "tool_result": None
            }
        
        except Exception as e:
            return {
                "response": f"🤖 처리 중 오류가 발생했습니다: {str(e)}",
                "tool_called": None,
                "tool_result": None,
                "error": str(e)
            }
    
    async def process_with_confirmation(
        self,
        message: str,
        user_id: str,
        user_name: str = None,
        pending_action: Dict = None
    ) -> Dict[str, Any]:
        """
        확인이 필요한 작업 처리 (삭제 확인 등)
        
        Args:
            message: 사용자 메시지
            user_id: 사용자 ID
            user_name: 사용자 이름
            pending_action: 대기 중인 작업 정보
        
        Returns:
            처리 결과
        """
        if not pending_action:
            return await self.process_message(message, user_id, user_name)
        
        # 확인 응답 해석
        message_lower = message.strip().lower()
        positive = ["예", "네", "응", "맞아", "그래", "ㅇㅇ", "ㅇ", "yes", "ok", "확인", "해줘", "저장", "삭제해"]
        negative = ["아니", "아뇨", "취소", "ㄴㄴ", "안해", "그만", "no", "싫어"]
        
        is_yes = any(p in message_lower for p in positive)
        is_no = any(n in message_lower for n in negative)
        
        if is_yes:
            # 대기 중인 작업 실행
            action = pending_action.get("action")
            args = pending_action.get("args", {})
            
            tool_result = execute_tool(action, args, user_id, user_name)
            
            if tool_result.get("success"):
                return {
                    "response": f"✅ {tool_result.get('message', '완료되었습니다.')}",
                    "tool_called": action,
                    "tool_result": tool_result,
                    "confirmed": True
                }
            else:
                return {
                    "response": f"❌ {tool_result.get('error', '오류가 발생했습니다.')}",
                    "tool_called": action,
                    "tool_result": tool_result,
                    "confirmed": True
                }
        
        elif is_no:
            return {
                "response": "🚫 취소되었습니다.",
                "tool_called": None,
                "tool_result": None,
                "confirmed": False,
                "cancelled": True
            }
        
        # 확인/취소가 아닌 경우 일반 처리
        return await self.process_message(message, user_id, user_name)
    
    async def chat_response(
        self,
        message: str,
        user_name: str = None
    ) -> str:
        """
        일반 대화 응답 생성 (도구 없이)
        
        Args:
            message: 사용자 메시지
            user_name: 사용자 이름
        
        Returns:
            응답 메시지
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": f"[{user_name or '사용자'}] {message}"}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"🤖 응답 생성 중 오류: {str(e)}"


# ═══════════════════════════════════════════════════════════════════
# 싱글톤 인스턴스
# ═══════════════════════════════════════════════════════════════════

_parser: Optional[AIParser] = None


def get_ai_parser() -> AIParser:
    """AI 파서 싱글톤 반환"""
    global _parser
    if _parser is None:
        _parser = AIParser()
    return _parser
