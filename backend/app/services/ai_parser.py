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

from backend.app.services.bot_tools import execute_tool, get_tools_for_mode
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.bot_mode import MODE_IDLE, MODE_JOURNAL, MODE_QUERY, idle_guide
from logic.db import get_connection

# .env 파일 로드
load_dotenv()


# ═══════════════════════════════════════════════════════════════════
# 시스템 프롬프트 (단순화됨)
# ═══════════════════════════════════════════════════════════════════

JOURNAL_PROMPT = """당신은 물류센터 작업일지 입력 봇입니다. 지금은 일지모드입니다.

## 오늘 날짜
{today} ({weekday})

## 핵심 역할
1. **작업일지 입력**: "틸리언 1톤하차 3만원" → save_work_log
2. **여러 건**: save_multiple_work_logs
3. **삭제**: "방금거 삭제" → delete_work_log
4. **수정**: "수정해줘" → update_work_log
5. **비고**: add_memo 또는 update_work_log
6. **불완전 정보**: ask_missing_info / complete_pending_entry
7. 수선·조회·연차 도구는 이 모드에 없습니다.

## 금액 해석
- 만=10000, 천=1000. 숫자+원은 가격.
- 단가(unit_price)=1개당 금액. 수량(qty)=건수. 합계를 단가에 넣지 말 것.

## 날짜
- 말하지 않으면 오늘({today}). 날짜를 물어보지 마세요.

## 수량
- 사용자가 말한 수량을 유지하세요. 가격 이력을 조회해도 qty를 1로 바꾸지 마세요.
- qty가 있으면 lookup_price_from_history / ask_price_confirmation / complete_pending_entry에 그대로 전달하세요.

## 가격 없으면
1) lookup_price_from_history  2) 있으면 ask_price_confirmation  3) 없으면 ask_missing_info
가격이 이미 있으면 바로 save_work_log.

## 업체명
- DB 등록 업체/별칭만. [대괄호] 안은 작성자 이름이지 업체가 아닙니다.

## 이전 대화
{pending_context}

## 취소
대기 입력이 있으면 cancel_pending_entry. 저장된 건 삭제와 구분.

응답은 짧고 한국어로.
"""

QUERY_PROMPT = """당신은 물류·수선 전산 조회 봇입니다. 지금은 조회모드입니다.

## 오늘 날짜
{today} ({weekday})

읽기 도구만 있습니다. 저장·수정·삭제를 하지 마세요.
DB 값을 추측하지 말고 반드시 도구로 현재 DB를 조회하세요.
환경변수, API 키, 비밀번호, private key는 조회하지 마세요.

도구:
- search_work_logs / get_work_log_stats / compare_periods : 작업일지
- get_invoice_stats : 인보이스
- lookup_vendors : 업체·별칭
- lookup_rate_tables : 출고비·추가작업비·택배비·부자재
- lookup_storage : 보관료
- lookup_vendor_charges : 추가 청구
- lookup_repair_catalog : 수선 작업·불량·기본비용

기간 질문은 start_date/end_date를 넣으세요.
짧게 한국어로 답하세요.

{pending_context}
"""

IDLE_PROMPT = """당신은 작업일지봇입니다. 지금은 기본상태입니다.
업무 도구가 없습니다. 저장하지 마세요.
모드 선택만 안내하세요.

""" + idle_guide() + """

## 오늘 날짜
{today} ({weekday})
{pending_context}
"""

SYSTEM_PROMPT = JOURNAL_PROMPT


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
    
    def _get_system_prompt(self, pending_context: str = "", mode: str = MODE_JOURNAL) -> str:
        today = datetime.now()
        yesterday = today.replace(day=today.day - 1) if today.day > 1 else today
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        if not pending_context:
            pending_context = "(이전 대화 맥락 없음)"
        if mode == MODE_QUERY:
            tmpl = QUERY_PROMPT
        elif mode == MODE_IDLE:
            tmpl = IDLE_PROMPT
        else:
            tmpl = JOURNAL_PROMPT
        return tmpl.format(
            today=today.strftime("%Y-%m-%d"),
            yesterday=yesterday.strftime("%Y-%m-%d"),
            weekday=weekdays[today.weekday()],
            pending_context=pending_context,
        )

    def _resolve_qty(self, message: str, tool_args: Dict[str, Any], pending_state: Optional[Dict]) -> Optional[int]:
        from backend.app.services.repair_bot import extract_qty
        if tool_args.get("qty"):
            try:
                n = int(tool_args["qty"])
                return n if n > 0 else None
            except (TypeError, ValueError):
                pass
        pending_qty = ((pending_state or {}).get("pending_data") or {}).get("qty")
        if pending_qty:
            try:
                n = int(pending_qty)
                return n if n > 0 else None
            except (TypeError, ValueError):
                pass
        return extract_qty(message)
    
    def _format_pending_context(self, state: Dict) -> str:
        """대기 중인 상태를 프롬프트용 문자열로 변환"""
        if not state:
            return ""
        
        pending_data = state.get("pending_data", {})
        missing = state.get("missing", [])
        last_question = state.get("last_question", "")
        
        if not pending_data and not missing:
            return ""
        
        parts = []
        parts.append("🚨🚨🚨 [중요] 이전 대화에서 불완전한 작업일지 정보가 대기 중입니다! 🚨🚨🚨")
        parts.append("")
        parts.append("📦 이미 파악된 정보:")
        
        if pending_data.get("vendor"):
            parts.append(f"  ✓ 업체명: {pending_data['vendor']}")
        if pending_data.get("work_type"):
            parts.append(f"  ✓ 작업종류: {pending_data['work_type']}")
        if pending_data.get("unit_price"):
            parts.append(f"  ✓ 단가: {pending_data['unit_price']:,}원")
        if pending_data.get("qty"):
            parts.append(f"  ✓ 수량: {pending_data['qty']}개")
        if pending_data.get("date"):
            parts.append(f"  ✓ 날짜: {pending_data['date']}")
        if pending_data.get("remark"):
            parts.append(f"  ✓ 비고: {pending_data['remark']}")
        if pending_data.get("entry_type") == "repair":
            parts.append("  ✓ 유형: 수선작업일지 (save_work_log 금지)")
            if pending_data.get("product"):
                parts.append(f"  ✓ 제품명: {pending_data['product']}")
            if pending_data.get("defect"):
                parts.append(f"  ✓ 불량명: {pending_data['defect']}")
            if pending_data.get("barcode"):
                parts.append(f"  ✓ 바코드: {pending_data['barcode']}")
        
        if missing:
            field_names = {"vendor": "업체명", "work_type": "작업종류", "unit_price": "단가", "qty": "수량"}
            missing_kr = [field_names.get(m, m) for m in missing]
            parts.append(f"")
            parts.append(f"❓ 누락된 정보: {', '.join(missing_kr)}")
        
        if last_question:
            parts.append(f"📝 마지막 질문: {last_question}")
        
        parts.append("")
        parts.append("⚠️ 사용자가 누락된 정보를 답하면:")
        parts.append("  → 반드시 complete_pending_entry 호출! (새로 추가된 정보만 전달)")
        parts.append("  → save_work_log 직접 호출 금지! (이미 파악된 정보가 사라짐)")
        parts.append("")
        parts.append("예시: 사용자가 '하이비오'라고 답하면")
        parts.append("  → complete_pending_entry(vendor='하이비오') 호출")
        parts.append("  → 시스템이 위의 이미 파악된 정보와 자동 병합")
        
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
        conversation_history: List[Dict] = None,
        mode: str = MODE_JOURNAL,
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
        pending_state = self.conv_manager.get_state(user_id, channel_id)
        pending_context = self._format_pending_context(pending_state)
        if mode == MODE_IDLE:
            return {
                "response": idle_guide(),
                "tool_called": None,
                "tool_result": None,
            }

        mode_tools = get_tools_for_mode(mode)
        orchestrate_tools = [
            {
                "type": "function",
                "function": {
                    "name": "ask_missing_info",
                    "description": "작업일지 저장에 필요한 정보가 부족할 때 사용자에게 물어봅니다. ⚠️ 필수 정보는 vendor, work_type, unit_price 3개뿐! 날짜(date)와 수량(qty)은 필수가 아니므로 절대 물어보지 마세요. 날짜 미입력 시 오늘, 수량 미입력 시 1로 자동 저장됩니다. ⚠️ 가격이 없으면 먼저 lookup_price_from_history로 이전 가격을 찾아보세요!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vendor": {"type": "string", "description": "파악된 업체명 (없으면 생략)"},
                            "work_type": {"type": "string", "description": "파악된 작업종류 (없으면 생략)"},
                            "unit_price": {"type": "integer", "description": "파악된 단가 (없으면 생략)"},
                            "qty": {"type": "integer", "description": "파악된 수량 (없으면 생략, 기본값 1)"},
                            "date": {"type": "string", "description": "파악된 날짜 (없으면 생략, 기본값 오늘)"},
                            "remark": {"type": "string", "description": "파악된 비고 (없으면 생략)"},
                            "missing": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["vendor", "work_type", "unit_price"]},
                                "description": "누락된 필드 목록. vendor, work_type, unit_price 중에서만 선택 가능. date, qty는 절대 넣지 마세요!"
                            },
                            "question": {"type": "string", "description": "사용자에게 물어볼 질문 (날짜나 수량을 물어보면 안 됨!)"}
                        },
                        "required": ["missing", "question"],
                        "additionalProperties": False,
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_pending_entry",
                    "description": "이전 대화에서 ask_missing_info 또는 ask_price_confirmation으로 물어본 후, 사용자가 누락된 정보를 답했을 때 사용합니다. 이미 파악된 정보(pending_data)와 자동으로 병합되므로, 새로 추가된 정보만 전달하세요. save_work_log 대신 반드시 이 도구를 사용하세요!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vendor": {"type": "string", "description": "사용자가 새로 답한 업체명 (이전에 누락됐던 경우만)"},
                            "work_type": {"type": "string", "description": "사용자가 새로 답한 작업종류 (이전에 누락됐던 경우만)"},
                            "unit_price": {"type": "integer", "description": "사용자가 새로 답한 단가 (이전에 누락됐던 경우만)"},
                            "qty": {"type": "integer", "description": "사용자가 새로 답한 수량 (이전에 누락됐던 경우만)"},
                            "date": {"type": "string", "description": "사용자가 새로 답한 날짜 (이전에 누락됐던 경우만)"},
                            "remark": {"type": "string", "description": "사용자가 새로 답한 비고 (이전에 누락됐던 경우만)"},
                            "defect": {"type": "string", "description": "수선 불량명"},
                            "product": {"type": "string", "description": "수선 제품명"},
                            "option": {"type": "string", "description": "수선 옵션"},
                            "barcode": {"type": "string", "description": "수선 바코드"}
                        },
                        "additionalProperties": False,
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "ask_price_confirmation",
                    "description": "lookup_price_from_history로 이전 가격을 찾은 후, 사용자에게 그 가격으로 저장할지 확인합니다. 사용자가 가격 없이 업체명+작업종류+수량만 말했을 때, 이전 가격을 찾아서 확인 질문을 합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vendor": {"type": "string", "description": "업체명"},
                            "work_type": {"type": "string", "description": "작업종류"},
                            "unit_price": {"type": "integer", "description": "조회된 이전 단가"},
                            "qty": {"type": "integer", "description": "수량 (기본값 1)"},
                            "date": {"type": "string", "description": "날짜 (기본값 오늘)"},
                            "remark": {"type": "string", "description": "비고"},
                            "question": {"type": "string", "description": "사용자에게 확인할 질문. 예: '틸리언 하차 최근 단가가 30,000원이에요. 이 가격으로 저장할까요?'"}
                        },
                        "required": ["vendor", "work_type", "unit_price", "question"],
                        "additionalProperties": False,
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_pending_entry",
                    "description": "대기 중인 작업일지 입력을 취소합니다. 이전 대화에서 ask_missing_info나 ask_price_confirmation으로 정보를 물어본 상태에서 사용자가 '취소'라고 하면 이 도구를 호출하세요. ⚠️ delete_work_log가 아닌 이 도구를 사용해야 합니다!",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    }
                }
            }
        ]
        if mode == MODE_JOURNAL:
            extended_tools = mode_tools + orchestrate_tools
        else:
            extended_tools = mode_tools
        
        # 메시지 구성
        messages = [
            {"role": "system", "content": self._get_system_prompt(pending_context, mode)}
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
                parallel_tool_calls=False,
                temperature=0.3
            )
            
            assistant_message = response.choices[0].message
            
            # 도구 호출이 있는 경우
            if assistant_message.tool_calls:
                # 첫 번째 도구만 특수 처리(조기 반환) — 여러 개일 수 있으므로 나머지는 모두 실행 후 tool 메시지로 응답해야 함
                tool_call_first = assistant_message.tool_calls[0]
                tool_name_first = tool_call_first.function.name
                tool_args_first = json.loads(tool_call_first.function.arguments)
                if "vendor" in tool_args_first:
                    tool_args_first["vendor"] = self._map_vendor_alias(tool_args_first["vendor"])
                
                # ─────────────────────────────────────
                # 특수 도구 처리: cancel_pending_entry (첫 번째만, 조기 반환)
                # ─────────────────────────────────────
                if tool_name_first == "cancel_pending_entry":
                    # 대기 상태 취소
                    if pending_state:
                        pending_data = pending_state.get("pending_data", {})
                        vendor = pending_data.get("vendor", "")
                        work_type = pending_data.get("work_type", "")
                        self.conv_manager.clear_state(user_id, channel_id)
                        
                        if vendor or work_type:
                            return {
                                "response": f"🚫 '{vendor} {work_type}' 입력이 취소되었어요.",
                                "tool_called": tool_name_first,
                                "tool_result": {"cancelled": True, "pending_data": pending_data}
                            }
                    
                    self.conv_manager.clear_state(user_id, channel_id)
                    return {
                        "response": "🚫 취소되었어요.",
                        "tool_called": tool_name_first,
                        "tool_result": {"cancelled": True}
                    }
                
                # ─────────────────────────────────────
                # 특수 도구 처리: ask_missing_info (첫 번째만, 조기 반환)
                # ─────────────────────────────────────
                if tool_name_first == "ask_missing_info":
                    pending_data = {
                        k: v for k, v in tool_args_first.items()
                        if k in ["vendor", "work_type", "unit_price", "qty", "date", "remark", "defect", "product", "option", "barcode"] and v
                    }
                    if pending_state:
                        existing = pending_state.get("pending_data") or {}
                        if existing.get("entry_type") == "repair":
                            pending_data = {**existing, **pending_data}
                    missing = tool_args_first.get("missing", [])
                    question = tool_args_first.get("question", "추가 정보를 알려주세요.")
                    self.conv_manager.set_state(
                        user_id=user_id,
                        channel_id=channel_id or "",
                        pending_data=pending_data,
                        missing=missing,
                        last_question=question
                    )
                    return {
                        "response": f"❓ {question}",
                        "tool_called": tool_name_first,
                        "tool_result": {"pending_data": pending_data, "missing": missing},
                        "waiting_for_info": True
                    }
                
                # ─────────────────────────────────────
                # 특수 도구 처리: lookup_price_from_history (첫 번째만, 조기 반환)
                # ─────────────────────────────────────
                if tool_name_first == "lookup_price_from_history":
                    # 가격 조회 실행
                    price_result = execute_tool("lookup_price_from_history", tool_args_first, user_id, user_name, mode=mode)
                    
                    vendor = tool_args_first.get("vendor", "")
                    work_type = tool_args_first.get("work_type", "")
                    
                    if price_result.get("found") and price_result.get("most_recent_price"):
                        # 가격 발견! → 확인 질문
                        found_price = price_result["most_recent_price"]
                        exact_match = price_result.get("exact_match", False)
                        usage_count = price_result.get("usage_count", 0)
                        sample_vendor = price_result.get("sample_vendor", "")
                        
                        # pending_data 구성 (기존 대화에서 수량 등이 있을 수 있음)
                        pending_data = {
                            "vendor": vendor,
                            "work_type": work_type,
                            "unit_price": found_price,
                        }
                        qty = self._resolve_qty(message, tool_args_first, pending_state)
                        if qty:
                            pending_data["qty"] = qty
                        
                        # 확인 질문 생성
                        if exact_match:
                            question = f"{vendor} {work_type} 최근 단가가 {found_price:,}원이에요 ({usage_count}회 사용). 이 가격으로 저장할까요?"
                        else:
                            # 다른 업체 기준 - 참고 정보 제공
                            ref_info = f"({usage_count}회 사용"
                            if sample_vendor:
                                ref_info += f", 예: {sample_vendor}"
                            ref_info += ")"
                            question = f"'{work_type}' 작업의 최근 단가가 {found_price:,}원이에요 {ref_info}. 이 가격으로 저장할까요? (다른 가격이면 직접 입력해주세요)"
                        
                        # 대기 상태 저장
                        self.conv_manager.set_state(
                            user_id=user_id,
                            channel_id=channel_id or "",
                            pending_data=pending_data,
                            missing=[],
                            last_question=question
                        )
                        
                        return {
                            "response": f"💰 {question}",
                            "tool_called": tool_name_first,
                            "tool_result": price_result,
                            "waiting_for_info": True
                        }
                    else:
                        # 가격 없음 → 단가 질문
                        pending_data = {
                            "vendor": vendor,
                            "work_type": work_type,
                        }
                        qty = self._resolve_qty(message, tool_args_first, pending_state)
                        if qty:
                            pending_data["qty"] = qty
                        question = f"'{work_type}' 작업의 이전 가격 기록이 없어요. 단가를 알려주세요!"
                        
                        self.conv_manager.set_state(
                            user_id=user_id,
                            channel_id=channel_id or "",
                            pending_data=pending_data,
                            missing=["unit_price"],
                            last_question=question
                        )
                        
                        return {
                            "response": f"❓ {question}",
                            "tool_called": tool_name_first,
                            "tool_result": price_result,
                            "waiting_for_info": True
                        }
                
                # ─────────────────────────────────────
                # 특수 도구 처리: ask_price_confirmation (첫 번째만, 조기 반환)
                # ─────────────────────────────────────
                if tool_name_first == "ask_price_confirmation":
                    pending_data = {
                        k: v for k, v in tool_args_first.items()
                        if k in ["vendor", "work_type", "unit_price", "qty", "date", "remark"] and v
                    }
                    question = tool_args_first.get("question", "이 가격으로 저장할까요?")
                    
                    # 대기 상태 저장 (가격 확인 대기)
                    self.conv_manager.set_state(
                        user_id=user_id,
                        channel_id=channel_id or "",
                        pending_data=pending_data,
                        missing=[],  # 모든 정보가 있음, 확인만 대기
                        last_question=question
                    )
                    
                    return {
                        "response": f"💰 {question}",
                        "tool_called": tool_name_first,
                        "tool_result": {"pending_data": pending_data, "awaiting_confirmation": True},
                        "waiting_for_info": True
                    }
                
                # ─────────────────────────────────────
                # 특수 도구 처리: complete_pending_entry (첫 번째만, 조기 반환)
                # ─────────────────────────────────────
                if tool_name_first == "complete_pending_entry":
                    if not pending_state:
                        return {
                            "response": "🤔 이전 대화 내용을 찾을 수 없어요. 처음부터 다시 말씀해주세요.",
                            "tool_called": tool_name_first,
                            "tool_result": None
                        }
                    merged_data = pending_state.get("pending_data", {}).copy()
                    for key, value in tool_args_first.items():
                        if value:
                            if key == "vendor":
                                value = self._map_vendor_alias(value)
                            merged_data[key] = value
                    self.conv_manager.clear_state(user_id, channel_id)
                    if merged_data.get("entry_type") == "repair":
                        if merged_data.get("product") is None:
                            required = ["vendor", "work_type", "unit_price", "product"]
                        else:
                            required = ["vendor", "work_type", "unit_price"]
                        still_missing = [f for f in required if not merged_data.get(f)]
                        if still_missing:
                            field_names = {"vendor": "업체명", "work_type": "작업", "unit_price": "비용", "product": "제품명"}
                            missing_kr = [field_names.get(f, f) for f in still_missing]
                            return {
                                "response": f"❓ 아직 {', '.join(missing_kr)}이(가) 필요해요.",
                                "tool_called": tool_name_first,
                                "tool_result": {"merged_data": merged_data, "still_missing": still_missing}
                            }
                        tool_result = execute_tool("save_repair_log", merged_data, user_id, user_name, mode=mode)
                        save_name = "save_repair_log"
                    else:
                        required = ["vendor", "work_type", "unit_price"]
                        still_missing = [f for f in required if not merged_data.get(f)]
                        if still_missing:
                            field_names = {"vendor": "업체명", "work_type": "작업종류", "unit_price": "단가"}
                            missing_kr = [field_names[f] for f in still_missing]
                            return {
                                "response": f"❓ 아직 {', '.join(missing_kr)}이(가) 필요해요.",
                                "tool_called": tool_name_first,
                                "tool_result": {"merged_data": merged_data, "still_missing": still_missing}
                            }
                        tool_result = execute_tool("save_work_log", merged_data, user_id, user_name, mode=mode)
                        save_name = "save_work_log"
                    if tool_result.get("success"):
                        return {
                            "response": f"✅ {tool_result.get('message', '저장완료!')}",
                            "tool_called": save_name,
                            "tool_result": tool_result
                        }
                    return {
                        "response": f"❌ 저장 실패: {tool_result.get('error', '알 수 없는 오류')}",
                        "tool_called": save_name,
                        "tool_result": tool_result
                    }
                
                # ─────────────────────────────────────
                # 모든 tool_calls 실행 (각 tool_call_id마다 응답 메시지 필요)
                # ─────────────────────────────────────
                tool_results_by_id = []
                for tc in assistant_message.tool_calls:
                    tname = tc.function.name
                    targs = json.loads(tc.function.arguments)
                    if "vendor" in targs:
                        targs["vendor"] = self._map_vendor_alias(targs["vendor"])
                    one_result = execute_tool(tname, targs, user_id, user_name, mode=mode)
                    tool_results_by_id.append((tc.id, tname, one_result))
                
                # 첫 번째가 save_work_log인 경우 상태/업체 검증 처리
                first_id, first_name, first_result = tool_results_by_id[0]
                if first_name in ("save_work_log", "save_multiple_work_logs") and first_result.get("success"):
                    self.conv_manager.clear_state(user_id, channel_id)
                    # 실제 저장이 완료된 경우에만 저장완료 메시지 반환 (2차 GPT 호출 없이)
                    return {
                        "response": f"✅ {first_result.get('message', '저장완료!')}",
                        "tool_called": first_name,
                        "tool_result": first_result
                    }
                if first_name == "save_work_log" and first_result.get("unknown_vendor"):
                    pending_data = {
                        k: v for k, v in tool_args_first.items()
                        if k in ["work_type", "unit_price", "qty", "date", "remark"] and v
                    }
                    self.conv_manager.set_state(
                        user_id=user_id,
                        channel_id=channel_id or "",
                        pending_data=pending_data,
                        missing=["vendor"],
                        last_question="어느 업체 작업인가요?"
                    )
                    similar = first_result.get("similar_vendors", [])
                    suggestion = f"\n비슷한 업체: {', '.join(similar)}" if similar else ""
                    return {
                        "response": f"❓ '{first_result['unknown_vendor']}'은(는) 등록되지 않은 업체입니다.{suggestion}\n\n어느 업체 작업인가요?",
                        "tool_called": first_name,
                        "tool_result": first_result,
                        "waiting_for_info": True
                    }
                
                # assistant 메시지 + 모든 tool_call_id에 대한 tool 메시지 추가 후 최종 응답 생성
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
                for tool_call_id, _tname, tool_result in tool_results_by_id:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })
                
                final_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.5
                )
                
                return {
                    "response": final_response.choices[0].message.content,
                    "tool_called": first_name,
                    "tool_result": first_result
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
        pending_action: Dict = None,
        mode: str = None,
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
            return await self.process_message(message, user_id, user_name, mode=mode or MODE_IDLE)
        
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
            
            tool_result = execute_tool(action, args, user_id, user_name, mode=mode)
            
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
