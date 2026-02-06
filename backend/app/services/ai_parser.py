"""
AI 기반 작업일지 파싱 모듈
───────────────────────────────────────
OpenAI GPT를 사용하여 자연어 메시지를 구조화된 작업일지 데이터로 변환합니다.
별칭 매핑: 채팅에서 입력한 업체명/별칭을 DB의 aliases 테이블과 매핑합니다.
"""

import os
import json
import unicodedata
from typing import Optional, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI

from logic.db import get_connection

# .env 파일 로드
load_dotenv()


def get_vendor_aliases() -> Dict[str, str]:
    """
    aliases 테이블에서 모든 별칭-업체 매핑을 가져옵니다.
    work_log 파일 타입의 별칭만 가져옵니다.
    
    Returns:
        Dict[str, str]: {별칭(정규화): 업체명} 형태의 딕셔너리
    """
    alias_map = {}
    try:
        with get_connection() as con:
            # aliases 테이블에서 work_log 타입 별칭 조회
            rows = con.execute(
                """SELECT alias, vendor FROM aliases 
                   WHERE file_type = 'work_log'"""
            ).fetchall()
            
            for alias, vendor in rows:
                if alias and vendor:
                    # 정규화된 별칭을 키로 사용
                    normalized = normalize_text(alias)
                    alias_map[normalized] = vendor
            
            # vendors 테이블에서 vendor 이름도 추가 (직접 입력용)
            vendor_rows = con.execute(
                "SELECT vendor, name FROM vendors WHERE active != 'NO' OR active IS NULL"
            ).fetchall()
            
            for vendor, name in vendor_rows:
                if vendor:
                    alias_map[normalize_text(vendor)] = vendor
                    if name:
                        alias_map[normalize_text(name)] = vendor
    except Exception as e:
        print(f"Warning: Could not load vendor aliases: {e}")
    
    return alias_map


def normalize_text(text: str) -> str:
    """텍스트 정규화 (공백 제거 + 유니코드 정규화 + 소문자)"""
    if not text:
        return ""
    normalized = unicodedata.normalize('NFKC', str(text).strip())
    normalized = ' '.join(normalized.split())
    return normalized.lower()


def find_vendor_by_alias(input_name: str, alias_map: Dict[str, str]) -> Optional[str]:
    """
    입력된 업체명/별칭으로 실제 vendor를 찾습니다.
    
    Args:
        input_name: 사용자가 입력한 업체명 또는 별칭
        alias_map: 별칭-업체 매핑 딕셔너리
    
    Returns:
        매핑된 vendor 이름, 없으면 None
    """
    if not input_name:
        return None
    
    normalized_input = normalize_text(input_name)
    
    # 정확히 일치하는 경우
    if normalized_input in alias_map:
        return alias_map[normalized_input]
    
    # 부분 일치 시도 (입력이 별칭을 포함하거나 별칭이 입력을 포함)
    for alias, vendor in alias_map.items():
        if alias in normalized_input or normalized_input in alias:
            return vendor
    
    return None


# 시스템 프롬프트
SYSTEM_PROMPT = """당신은 물류센터 작업일지 파싱 AI입니다.
사용자의 자연어 메시지에서 작업 정보를 추출하세요.

## 추출해야 할 정보
- vendor (업체명): 거래처/공급처 이름 (예: 틸리언, 나블리, 디오프)
- work_type (분류): 작업 종류. ⚠️ 사용자가 입력한 값을 **정확히 그대로** 사용하세요!
- qty (수량): 작업 수량 (숫자만, 없으면 1)
- unit_price (단가): 건당/개당 가격 (숫자만, 원 단위)
- date (날짜): 작업일 (YYYY-MM-DD 형식, 없으면 오늘)
- remark (비고): 추가 메모 사항 (선택)

## work_type 추출 중요 규칙 ⚠️
- 사용자가 입력한 작업 종류를 **절대 변환하지 마세요**!
- "1톤화물대납" → "1톤화물대납" (✓ 그대로)
- "1톤화물대납" → "1톤하차" (✗ 잘못됨 - 변환 금지!)
- "특수포장" → "특수포장" (✓ 그대로)
- 표준 목록에 없는 작업 종류도 사용자가 입력한 그대로 기록합니다.

## 단가 해석 규칙
- "3만원" → 30000
- "3만" → 30000
- "800원" → 800
- "1500" → 1500

## 응답 형식 (반드시 JSON)
{
  "success": true/false,
  "data": {
    "vendor": "업체명 또는 null",
    "work_type": "작업종류 (사용자 입력 그대로) 또는 null",
    "qty": 숫자 또는 null,
    "unit_price": 숫자 또는 null,
    "date": "YYYY-MM-DD",
    "remark": "비고 또는 null"
  },
  "missing": ["누락된 필드명들"],
  "question": "사용자에게 물어볼 질문 (missing이 있을 때만)"
}

## 예시

입력: "틸리언 1톤하차 3만원"
출력: {"success": true, "data": {"vendor": "틸리언", "work_type": "1톤하차", "qty": 1, "unit_price": 30000, "date": "2026-02-03", "remark": null}, "missing": [], "question": null}

입력: "나블리 양품화 20개 800원"
출력: {"success": true, "data": {"vendor": "나블리", "work_type": "양품화", "qty": 20, "unit_price": 800, "date": "2026-02-03", "remark": null}, "missing": [], "question": null}

입력: "틸리언 1톤화물대납 5만원"
출력: {"success": true, "data": {"vendor": "틸리언", "work_type": "1톤화물대납", "qty": 1, "unit_price": 50000, "date": "2026-02-03", "remark": null}, "missing": [], "question": null}

입력: "양품화 50개 했어요"
출력: {"success": false, "data": {"vendor": null, "work_type": "양품화", "qty": 50, "unit_price": null, "date": "2026-02-03", "remark": null}, "missing": ["vendor", "unit_price"], "question": "어느 업체 작업인가요? 단가도 알려주세요."}

입력: "틸리언 바코드"
출력: {"success": false, "data": {"vendor": "틸리언", "work_type": "바코드", "qty": null, "unit_price": null, "date": "2026-02-03", "remark": null}, "missing": ["qty"], "question": "몇 개 작업했나요?"}

## 중요 규칙
1. 업체명(vendor)과 작업종류(work_type)는 필수입니다.
2. 단가(unit_price)가 없으면 질문하세요.
3. 수량(qty)이 명시되지 않고 작업 특성상 단건이면 1로 설정 (예: 1톤하차, 입고, 화물대납 등)
4. 수량이 명시되지 않고 작업 특성상 복수이면 질문 (예: 바코드부착, 양품화 등)
5. 오늘 날짜: {today}
6. 반드시 유효한 JSON만 출력하세요. 다른 텍스트 없이 JSON만 출력.
7. ⚠️ work_type은 사용자가 입력한 값 그대로 사용! 유사한 값으로 변환 금지!"""


class AIParser:
    """AI 기반 작업일지 파서"""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # 비용 효율적인 모델
        
        # 별칭 매핑 캐시 (초기화 시 로드)
        self._alias_cache: Optional[Dict[str, str]] = None
        self._alias_cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5분마다 새로고침
    
    def _get_alias_map(self) -> Dict[str, str]:
        """별칭 매핑 가져오기 (캐시 사용)"""
        now = datetime.now()
        
        # 캐시가 없거나 만료됐으면 새로 로드
        if (self._alias_cache is None or 
            self._alias_cache_time is None or
            (now - self._alias_cache_time).seconds > self._cache_ttl_seconds):
            self._alias_cache = get_vendor_aliases()
            self._alias_cache_time = now
        
        return self._alias_cache or {}
    
    def _map_vendor_alias(self, vendor_name: str) -> str:
        """
        입력된 업체명을 별칭 테이블과 매핑하여 실제 vendor로 변환
        
        Args:
            vendor_name: AI가 파싱한 업체명
        
        Returns:
            매핑된 vendor 이름 (매핑 실패 시 원본 반환)
        """
        if not vendor_name:
            return vendor_name
        
        alias_map = self._get_alias_map()
        mapped_vendor = find_vendor_by_alias(vendor_name, alias_map)
        
        if mapped_vendor:
            return mapped_vendor
        
        # 매핑 실패 시 원본 반환
        return vendor_name
    
    async def parse_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        자연어 메시지를 작업일지 데이터로 파싱
        
        Args:
            message: 사용자 메시지
            context: 이전 대화 컨텍스트 (누락된 정보 보완용)
        
        Returns:
            파싱 결과 딕셔너리
        """
        today = datetime.now().strftime("%Y-%m-%d")
        system_prompt = SYSTEM_PROMPT.replace("{today}", today)
        
        # 컨텍스트가 있으면 프롬프트에 추가
        user_message = message
        if context and context.get("pending_data"):
            pending = context["pending_data"]
            context_info = f"\n\n[이전 대화 컨텍스트]\n"
            context_info += f"이미 파악된 정보: {json.dumps(pending, ensure_ascii=False)}\n"
            context_info += f"누락된 정보: {context.get('missing', [])}\n"
            context_info += f"사용자가 답변: {message}\n"
            context_info += "이 답변으로 누락된 정보를 채워주세요."
            user_message = context_info
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1,  # 일관된 결과를 위해 낮은 temperature
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            # 컨텍스트와 병합
            if context and context.get("pending_data"):
                result = self._merge_with_context(result, context)
            
            # 별칭 매핑 적용: AI가 파싱한 업체명을 실제 vendor로 변환
            if result.get("data") and result["data"].get("vendor"):
                original_vendor = result["data"]["vendor"]
                mapped_vendor = self._map_vendor_alias(original_vendor)
                result["data"]["vendor"] = mapped_vendor
                
                # 매핑 정보 로그 (디버깅용)
                if original_vendor != mapped_vendor:
                    result["_alias_mapped"] = {
                        "original": original_vendor,
                        "mapped": mapped_vendor
                    }
            
            return result
            
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON 파싱 오류: {str(e)}",
                "data": None,
                "missing": ["all"],
                "question": "죄송합니다. 메시지를 이해하지 못했어요. 다시 말씀해주세요."
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None,
                "missing": ["all"],
                "question": "오류가 발생했습니다. 다시 시도해주세요."
            }
    
    def _merge_with_context(
        self,
        new_result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """이전 컨텍스트와 새 결과 병합"""
        pending_data = context.get("pending_data", {})
        new_data = new_result.get("data", {})
        
        # 새로운 데이터로 누락된 필드 채우기
        merged_data = pending_data.copy()
        for key, value in new_data.items():
            if value is not None:
                merged_data[key] = value
        
        # 아직 누락된 필드 확인
        required_fields = ["vendor", "work_type", "unit_price"]
        missing = []
        for field in required_fields:
            if merged_data.get(field) is None:
                missing.append(field)
        
        # qty가 없고 작업 타입이 복수 작업이면 missing에 추가
        if merged_data.get("qty") is None:
            work_type = merged_data.get("work_type", "")
            multi_qty_works = ["바코드", "양품화", "라벨", "스티커", "검수"]
            if any(w in work_type for w in multi_qty_works):
                missing.append("qty")
            else:
                merged_data["qty"] = 1  # 기본값
        
        # 결과 생성
        if missing:
            questions = {
                "vendor": "어느 업체 작업인가요?",
                "work_type": "어떤 작업인가요?",
                "unit_price": "단가가 얼마인가요?",
                "qty": "몇 개 작업했나요?"
            }
            question_parts = [questions.get(m, "") for m in missing if m in questions]
            question = " ".join(question_parts)
            
            return {
                "success": False,
                "data": merged_data,
                "missing": missing,
                "question": question
            }
        
        return {
            "success": True,
            "data": merged_data,
            "missing": [],
            "question": None
        }
    
    async def generate_response(
        self,
        result: Dict[str, Any],
        action: str = "confirm"
    ) -> str:
        """
        파싱 결과를 사용자 응답 메시지로 변환
        
        Args:
            result: 파싱 결과
            action: "confirm" (저장 완료), "question" (추가 질문), "error" (오류)
        """
        if action == "question" or not result.get("success"):
            return f"🤔 {result.get('question', '다시 말씀해주세요.')}"
        
        data = result.get("data", {})
        vendor = data.get("vendor", "")
        work_type = data.get("work_type", "")
        qty = data.get("qty", 1)
        unit_price = data.get("unit_price", 0)
        total = qty * unit_price
        
        # 금액 포맷팅
        def format_price(price: int) -> str:
            return f"{price:,}원"
        
        response = f"✅ 저장완료!\n"
        response += f"• 업체: {vendor}\n"
        response += f"• 작업: {work_type}\n"
        
        if qty > 1:
            response += f"• 수량: {qty}개 × {format_price(unit_price)}\n"
        else:
            response += f"• 단가: {format_price(unit_price)}\n"
        
        response += f"• 합계: {format_price(total)}"
        
        if data.get("remark"):
            response += f"\n• 비고: {data['remark']}"
        
        return response
    
    async def classify_message(
        self,
        message: str,
        user_name: Optional[str] = None,
        has_pending_state: bool = False
    ) -> Dict[str, Any]:
        """
        메시지의 의도를 종합적으로 분류
        
        Args:
            message: 사용자 메시지
            user_name: 사용자 이름
            has_pending_state: 이전 대화 상태가 있는지
        
        Returns:
            {"intent": "의도", "data": {...}, "confidence": 0.0-1.0}
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        classify_prompt = f"""사용자 메시지의 의도를 분류하세요.

## 오늘 날짜: {today}
## 사용자: {user_name or "알수없음"}
## 이전 대화 상태 존재: {has_pending_state}

## 사용자 메시지
"{message}"

## 의도 분류 (하나만 선택) - 동의어/변형 표현도 인식!

1. "greeting" - 인사
   표현: 안녕, 하이, 반가워, 좋은아침, 안녕하세요, 헬로, hi, hello, 굿모닝, 반갑습니다

2. "help" - 도움말/사용법 요청
   표현: 도움말, 어떻게 써, 사용법, 뭐할수있어, 기능, 뭐해줄수있어, 명령어, 메뉴, 기능목록, 사용방법, 어떻게해, 어떻게 사용해

3. "test" - 테스트/상태확인
   표현: 테스트, 퐁, 핑, 살아있어?, 테스트중, 작동해?, 되나?, 응답해, ping, test

4. "work_log_query" - 기간별 작업일지 전체 조회
   표현: 오늘 작업 정리해줘, 오늘꺼 보여줘, 이번주 작업, 지난주 일지, 오늘 뭐했어, 작업일지 보여줘, 이번달 정리, 일지 조회
   키워드: 정리, 보여줘, 조회, 일지, 뭐했어, 작업내역

5. "work_log_entry" - 작업일지 입력 (업체명 + 작업종류 + 금액 형식)
   형식: [업체명] [작업종류] [금액] (예: 틸리언 1톤하차 3만원)

6. "cancel" - 취소/삭제 요청 (직전 작업)
   표현: 취소, 취소해줘, 방금꺼 취소, 삭제해줘, 삭제, 지워줘, 그거 삭제, 방금거 지워, 없애줘, 뻬줘, 빼줘

7. "edit" - 수정 요청 (직전 작업)
   표현: 수정, 수정해줘, 방금꺼 수정, 고쳐줘, 변경해줘, 바꿔줘, 수정할래, 틀렸어

8. "confirm_yes" - 긍정 응답
   표현: 네, 응, 맞아, 그래, ㅇㅇ, 확인, 예, 좋아, 그렇게해, 해줘, ㅇ, yes, ok, 오키, 굿, 저장해, 진행해

9. "confirm_no" - 부정 응답
   표현: 아니, 아니오, 취소, ㄴㄴ, 안해, 아뇨, 됐어, 그만, 하지마, 싫어, 안할래, no, 노, 패스

10. "select_option" - 옵션 선택
    표현: 1번, 2번, 텍스트로, 파일로, 첫번째, 두번째, 위에꺼, 아래꺼

11. "search_query" - 내부 작업일지 DB 검색 (저장된 작업일지 기록 조회)
    표현: 틸리언 작업 보여줘, 틸리언꺼, 나블리 뭐있어, 3만원짜리, 하차 몇번, 2월 4일 작업, 검색해줘
    키워드: ~작업, ~꺼, ~뭐있어, ~찾아줘, ~있어?

12. "stats_query" - 통계/분석 요청
    표현: 총 얼마야, 몇건 했어, 합계, 총합, 가장 많이, 업체별 합계, 랭킹, 순위, 통계
    키워드: 총, 합계, 몇건, 얼마, 통계, 순위

13. "specific_edit" - 특정 건 수정 (조건으로 특정)
    표현: 틸리언 3만원 5만원으로, 어제 나블리꺼 수정, ~를 ~로 바꿔줘

14. "specific_delete" - 특정 건 삭제 (조건으로 특정)
    표현: 틸리언 3만원꺼 삭제, 어제 나블리 양품화 삭제, ~꺼 지워줘

15. "multi_entry" - 다중 건 입력 (쉼표/그리고로 구분된 여러 작업)
    표현: 틸리언 3만, 나블리 2만 / A업체 1만 그리고 B업체 5만 / ~랑 ~도 입력해줘

16. "dashboard" - 대시보드/웹페이지 링크
    표현: 대시보드, 웹페이지, 링크 줘, 사이트 주소, 웹사이트, 홈페이지, URL

17. "compare_periods" - 기간 비교
    표현: 지난주랑 이번주 비교, 1월이랑 2월, 어제 오늘 비교, vs, ~랑 ~비교

18. "undo" - 실행취소/되돌리기
    표현: 되돌려줘, 실행취소, undo, 복구해줘, 아까꺼 취소, 히스토리

19. "add_memo" - 메모 추가
    표현: 메모 추가, 비고에 적어줘, 메모해줘, ~메모, 비고

20. "bulk_edit" - 일괄 수정 (여러 건)
    표현: 전부 5만원으로, 모두 수정, 일괄 수정, 다 바꿔줘

21. "copy_entry" - 복사
    표현: 어제꺼 복사, 복사해줘, 복제, ~를 ~로 복사

22. "web_search" - 웹 검색/외부 정보 검색
    표현: 조사해줘, 검색해줘, 알아봐줘, 찾아봐, ~가 뭐야, ~회사 정보, 인터넷에서, 뉴스

23. "chat" - 일반 대화/질문 (위에 해당 안됨)

## 응답 형식 (JSON)
{{
  "intent": "의도",
  "confidence": 0.0~1.0,
  "reason": "판단 이유 (짧게)",
  "data": {{
    // intent별 추가 데이터
    // multi_entry: {{"entries": ["틸리언 하차 3만", "나블리 양품화 2만"]}}
    // compare_periods: {{"period1": "지난주", "period2": "이번주"}}
    // copy_entry: {{"source_date": "어제", "target_date": "오늘", "vendor": "틸리언"}}
    // web_search: {{"query": "검색어"}}
  }}
}}

## 판단 규칙 (유연하게!)
- "업체명 + 작업 + 금액" 형식이 여러 개면 multi_entry (쉼표, 그리고, 또, 랑 등으로 구분)
- "업체명 + 작업 + 금액" 형식이 1개면 work_log_entry
- "대시보드", "링크", "사이트", "웹", "URL", "주소" 등이면 dashboard
- "비교" + 두 개의 기간이면 compare_periods (지난주랑 이번주, ~vs~, ~이랑~)
- "되돌려", "undo", "히스토리", "복구", "실행취소" 등이면 undo
- "메모", "비고" + "추가/적어" 등이면 add_memo
- "전부", "일괄", "모두", "다" + "수정/바꿔" 등이면 bulk_edit
- "복사", "복제" 등이면 copy_entry

## 취소/삭제 관련 (유연하게 인식!)
- "취소", "삭제", "지워", "없애", "빼" 등 모두 cancel 또는 specific_delete
- 조건 없이 "취소", "삭제해줘" → cancel (직전 작업)
- 조건 있으면 → specific_delete (예: "틸리언 3만원 삭제")

## 조회 관련 (유연하게 인식!)
- "~꺼", "~작업", "~뭐있어", "~보여줘" → search_query 또는 work_log_query
- 기간만 있으면 (오늘, 이번주, 이번달) → work_log_query
- 조건이 있으면 (업체명, 금액 등) → search_query

## web_search vs search_query 구분
- web_search (외부 웹 검색):
  - "~에 대한 정보", "~에 대해 알려줘", "~가 뭐야?"
  - "조사해줘", "인터넷에서 찾아봐", "알아봐줘"
  - 회사 정보, 뉴스, 시장 동향, 일반 지식
  
- search_query (내부 작업일지 DB 검색):
  - 우리 작업일지에서 검색
  - "틸리언 작업", "3만원짜리", "어제 나블리"
  - 금액, 날짜, 업체명 기준 조회

## 핵심 규칙
- 사용자의 다양한 표현을 유연하게 해석하세요!
- 맞춤법이 틀려도 의도 파악 (예: "삭재" → 삭제)
- 줄임말도 인식 (예: "ㅇㅇ" → 예, "ㄴㄴ" → 아니오)
- 구어체도 인식 (예: "해쥬" → 해줘, "고마워" → 인사)
- 애매하면 chat으로 분류

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "메시지 의도를 정확하게 분류하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": classify_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=200
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            return {
                "intent": "chat",
                "confidence": 0.0,
                "reason": f"Error: {str(e)}",
                "data": {}
            }

    async def parse_date_range(
        self,
        message: str,
        today: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        자연어에서 날짜 범위를 AI로 파악
        
        Args:
            message: 사용자 메시지 (예: "1월 20일부터 21일까지", "지난주", "이번달")
            today: 오늘 날짜 (YYYY-MM-DD), None이면 자동 설정
        
        Returns:
            {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "period_name": "기간명"}
        """
        if today is None:
            today = datetime.now().strftime("%Y-%m-%d")
        
        date_prompt = f"""사용자 메시지에서 날짜 범위를 파악하세요.

## 오늘 날짜
{today} (요일: {datetime.strptime(today, "%Y-%m-%d").strftime("%A")})

## 사용자 메시지
"{message}"

## 날짜 해석 규칙 (중요!)
- "오늘" → 오늘 하루
- "어제" → 어제 하루
- "이번주" → 이번 주 월요일 ~ 오늘
- "지난주" → 지난 주 월요일 ~ 일요일
- "이번달" / "이번 달" → 이번 달 1일 ~ 오늘
- "지난달" / "저번달" → 지난 달 1일 ~ 말일
- "1월" → 1월 1일 ~ 1월 31일

## ⚠️ 핵심 규칙: 여러 날짜가 나열된 경우
- "5일 6일" → 이번 달 5일 ~ 6일 (나열된 첫 번째가 시작, 마지막이 끝)
- "3일 4일 5일" → 이번 달 3일 ~ 5일
- "20일 21일" → 이번 달 20일 ~ 21일
- 숫자+일이 여러 개 나열되면 그 범위로 해석!

## 기타 규칙
- "1월 20일부터 21일까지" → 1월 20일 ~ 1월 21일 (같은 달로 해석)
- "1월 20일부터 2월 5일까지" → 1월 20일 ~ 2월 5일
- "20일부터 25일까지" → 이번 달 20일 ~ 25일
- 연도가 없으면 올해로 가정
- 월이 없으면 이번 달로 가정

## 응답 형식 (JSON)
{{
  "found": true/false,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "period_name": "사람이 읽기 쉬운 기간명"
}}

## 예시
- "오늘 작업 정리해줘" → {{"found": true, "start_date": "{today}", "end_date": "{today}", "period_name": "오늘"}}
- "5일 6일 작업일지" → {{"found": true, "start_date": "2026-02-05", "end_date": "2026-02-06", "period_name": "2월 5일 ~ 6일"}}
- "3일 4일 5일" → {{"found": true, "start_date": "2026-02-03", "end_date": "2026-02-05", "period_name": "2월 3일 ~ 5일"}}
- "1월 20일부터 21일까지" → {{"found": true, "start_date": "2026-01-20", "end_date": "2026-01-21", "period_name": "1월 20일 ~ 21일"}}
- "지난주 작업" → {{"found": true, "start_date": "...", "end_date": "...", "period_name": "지난 주"}}
- "안녕하세요" → {{"found": false, "start_date": null, "end_date": null, "period_name": null}}

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "날짜 범위를 정확하게 파악하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": date_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=200
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            return {
                "found": False,
                "start_date": None,
                "end_date": None,
                "period_name": None,
                "error": str(e)
            }

    async def parse_advanced_query(
        self,
        message: str,
        query_type: str
    ) -> Dict[str, Any]:
        """
        고급 쿼리 파싱 (조건부 검색, 통계, 특정 건 수정/삭제)
        
        Args:
            message: 사용자 메시지
            query_type: "search", "stats", "specific_edit", "specific_delete"
        
        Returns:
            쿼리 조건 딕셔너리
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        query_prompt = f"""사용자 메시지에서 쿼리 조건을 추출하세요.

## 오늘 날짜: {today}
## 쿼리 유형: {query_type}

## 사용자 메시지
"{message}"

## 추출할 조건들
- vendor: 업체명 (틸리언, 나블리 등)
- work_type: 작업종류 (1톤하차, 양품화, 바코드 등)
- date: 특정 날짜 (YYYY-MM-DD 형식, "오늘"이면 {today})
- start_date: 시작 날짜
- end_date: 끝 날짜
- price: 금액 (숫자, "3만원" → 30000)
- qty: 수량

## 통계 유형 (query_type이 stats인 경우)
- stats_type: 
  - "total_amount" (총 매출/금액)
  - "total_count" (총 건수)
  - "top_vendor" (가장 많은 업체)
  - "by_vendor" (업체별 합계)
  - "by_work_type" (작업종류별 합계)
  - "compare" (기간 비교)

## 응답 형식 (JSON)
{{
  "vendor": "업체명 또는 null",
  "work_type": "작업종류 또는 null",
  "date": "YYYY-MM-DD 또는 null",
  "start_date": "YYYY-MM-DD 또는 null",
  "end_date": "YYYY-MM-DD 또는 null",
  "price": 숫자 또는 null,
  "qty": 숫자 또는 null,
  "stats_type": "통계유형 또는 null",
  "compare_period1": "비교기간1 또는 null",
  "compare_period2": "비교기간2 또는 null",
  "period_name": "사람이 읽기 쉬운 기간명"
}}

## 예시
- "틸리언 작업 보여줘" → {{"vendor": "틸리언", "work_type": null, ...}}
- "2월 4일 나블리 있어?" → {{"vendor": "나블리", "date": "2026-02-04", ...}}
- "3만원짜리 뭐있어?" → {{"price": 30000, ...}}
- "이번달 총 얼마야?" → {{"stats_type": "total_amount", "start_date": "2026-02-01", "end_date": "{today}", ...}}
- "오늘 몇건 했어?" → {{"stats_type": "total_count", "date": "{today}", ...}}
- "가장 많이 일한 업체" → {{"stats_type": "top_vendor", ...}}
- "지난주랑 이번주 비교" → {{"stats_type": "compare", "compare_period1": "지난주", "compare_period2": "이번주", ...}}
- "오늘 틸리언 3만원 삭제해줘" → {{"vendor": "틸리언", "date": "{today}", "price": 30000, ...}}

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "쿼리 조건을 정확하게 추출하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": query_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=300
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # 업체명 별칭 매핑 적용
            if result.get("vendor"):
                result["vendor"] = self._map_vendor_alias(result["vendor"])
            
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "vendor": None,
                "work_type": None,
                "date": None,
                "price": None
            }

    async def parse_intent(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        사용자 메시지의 의도를 AI로 파악
        
        Args:
            message: 사용자 메시지
            context: 대화 컨텍스트 (last_question, options 등)
        
        Returns:
            {"intent": "의도", "value": "값", "confidence": 0.0-1.0}
        """
        last_question = context.get("last_question", "")
        options = context.get("options", [])
        pending_data = context.get("pending_data", {})
        
        intent_prompt = f"""사용자의 의도를 파악하세요. 다양한 표현을 유연하게 인식!

## 현재 상황
- 마지막 질문: {last_question}
- 선택 옵션: {options}
- 대화 컨텍스트: {json.dumps(pending_data, ensure_ascii=False)}

## 사용자 메시지
"{message}"

## 파악할 의도 종류 (동의어/변형 표현 유연하게!)
1. "select_option" - 옵션 선택
   표현: 1번, 2번, 첫번째, 위에꺼, 텍스트로, 파일로

2. "confirm_yes" - 긍정 응답
   표현: 네, 응, 맞아, 그래, ㅇㅇ, 확인, 예, 좋아, 해줘, ㅇ, yes, ok, 오키, 굿, 저장해, 진행해, 고마워, 그렇게, 알았어, 넵, 넹, 웅, 그래줘, 부탁해

3. "confirm_no" - 부정 응답
   표현: 아니, 아니오, 취소, ㄴㄴ, 안해, 아뇨, 됐어, 그만, 싫어, 안할래, no, 노, 패스, 하지마, 아닝, 놉

4. "cancel" - 취소 요청
   표현: 취소해줘, 방금거 취소, 삭제해줘, 지워줘, 없애줘

5. "edit" - 수정 요청
   표현: 수정해줘, 고쳐줘, 변경해줘, 바꿔줘

6. "work_log" - 작업일지 형식 (업체명+작업+금액)

7. "chat" - 일반 대화

8. "unknown" - 파악 불가

## 응답 형식 (JSON)
{{
  "intent": "의도종류",
  "value": "선택한 값 (select_option일 때: 1 또는 2 등)",
  "confidence": 0.0~1.0,
  "reason": "판단 이유 (짧게)"
}}

## 유연한 인식 예시
- "1번으로 해줘", "1번", "첫번째" → select_option, value: "1"
- "응", "네", "그래", "ㅇㅇ", "ok", "좋아", "해줘", "넵", "웅" → confirm_yes
- "아니", "취소", "ㄴㄴ", "됐어", "그만" → confirm_no
- "틸리언 하차 3만원" → work_log

## 핵심 규칙
- 맞춤법 틀려도 인식! (예: "넹" → 예)
- 줄임말 인식! (예: "ㅇㅇ" → 예, "ㄴㄴ" → 아니오)
- 구어체 인식! (예: "해쥬" → 해줘)
- 짧은 답변도 문맥에서 해석!

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "사용자 의도를 정확하게 파악하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": intent_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=150
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            return {
                "intent": "unknown",
                "value": None,
                "confidence": 0.0,
                "reason": f"Error: {str(e)}"
            }

    async def parse_multi_entry(
        self,
        message: str
    ) -> Dict[str, Any]:
        """
        다중 건 입력 파싱 (한 메시지에서 여러 작업 추출)
        
        Args:
            message: "틸리언 하차 3만, 나블리 양품화 2만" 형태의 메시지
        
        Returns:
            {"entries": [{"vendor": ..., "work_type": ..., ...}, ...]}
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        multi_prompt = f"""메시지에서 여러 작업일지 항목을 추출하세요.

## 오늘 날짜: {today}

## 메시지
"{message}"

## 추출 규칙
- 쉼표(,), "그리고", "또", "랑" 등으로 구분된 여러 작업을 각각 추출
- 각 항목에서: vendor(업체명), work_type(작업종류), qty(수량, 없으면 1), unit_price(단가), remark(비고)
- ⚠️ work_type은 사용자가 입력한 값을 **정확히 그대로** 사용! 유사한 값으로 변환 금지!

## 응답 형식 (JSON)
{{
  "entries": [
    {{"vendor": "업체명1", "work_type": "작업1 (사용자 입력 그대로)", "qty": 1, "unit_price": 30000, "date": "{today}", "remark": null}},
    {{"vendor": "업체명2", "work_type": "작업2 (사용자 입력 그대로)", "qty": 10, "unit_price": 800, "date": "{today}", "remark": null}}
  ],
  "count": 2
}}

## 예시
- "틸리언 하차 3만, 나블리 양품화 20개 800원" → 2건 (work_type: "하차", "양품화" 그대로)
- "A업체 1톤화물대납 5만, B업체 특수포장 3만" → 2건 (work_type: "1톤화물대납", "특수포장" 그대로 - 변환 금지!)

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "다중 작업일지를 정확하게 파싱하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": multi_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=500
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # 업체명 별칭 매핑 적용
            if result.get("entries"):
                for entry in result["entries"]:
                    if entry.get("vendor"):
                        entry["vendor"] = self._map_vendor_alias(entry["vendor"])
            
            return result
            
        except Exception as e:
            return {"entries": [], "count": 0, "error": str(e)}

    async def parse_compare_periods(
        self,
        message: str
    ) -> Dict[str, Any]:
        """
        기간 비교 요청 파싱
        
        Returns:
            {"period1": {...}, "period2": {...}}
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        compare_prompt = f"""메시지에서 비교할 두 기간을 추출하세요.

## 오늘 날짜: {today}

## 메시지
"{message}"

## 응답 형식 (JSON)
{{
  "period1": {{
    "name": "지난주",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD"
  }},
  "period2": {{
    "name": "이번주",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD"
  }}
}}

## 예시
- "지난주랑 이번주 비교" → 지난주 월~일, 이번주 월~오늘
- "1월이랑 2월 비교" → 1월 1일~31일, 2월 1일~오늘
- "어제랑 오늘" → 어제, 오늘

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "기간 비교를 파싱하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": compare_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=300
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            return {"error": str(e)}

    async def parse_copy_request(
        self,
        message: str
    ) -> Dict[str, Any]:
        """
        복사 요청 파싱
        
        Returns:
            {"source_date": "어제", "target_date": "오늘", "vendor": "틸리언", ...}
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        copy_prompt = f"""복사 요청에서 조건을 추출하세요.

## 오늘 날짜: {today}

## 메시지
"{message}"

## 응답 형식 (JSON)
{{
  "source_date": "YYYY-MM-DD (복사할 원본 날짜)",
  "source_period_start": "YYYY-MM-DD (기간인 경우 시작)",
  "source_period_end": "YYYY-MM-DD (기간인 경우 끝)",
  "target_date": "YYYY-MM-DD (복사될 대상 날짜, 없으면 오늘)",
  "vendor": "업체명 또는 null (특정 업체만)",
  "work_type": "작업종류 또는 null"
}}

반드시 유효한 JSON만 출력하세요."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "복사 요청을 파싱하는 AI입니다. JSON만 출력합니다."},
                    {"role": "user", "content": copy_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=200
            )
            
            result = json.loads(response.choices[0].message.content)
            if result.get("vendor"):
                result["vendor"] = self._map_vendor_alias(result["vendor"])
            return result
            
        except Exception as e:
            return {"error": str(e)}

    async def check_anomaly(
        self,
        vendor: str,
        work_type: str,
        unit_price: int,
        historical_prices: List[int]
    ) -> Dict[str, Any]:
        """
        이상치 탐지 - 입력된 가격이 기존 패턴과 다른지 확인
        
        Returns:
            {"is_anomaly": bool, "reason": str, "suggestion": int}
        """
        if not historical_prices:
            return {"is_anomaly": False, "reason": "비교할 이력 없음"}
        
        avg_price = sum(historical_prices) / len(historical_prices)
        min_price = min(historical_prices)
        max_price = max(historical_prices)
        
        # 평균 대비 50% 이상 차이나면 이상치
        if avg_price > 0:
            diff_ratio = abs(unit_price - avg_price) / avg_price
            if diff_ratio > 0.5:
                return {
                    "is_anomaly": True,
                    "reason": f"평소 평균 {avg_price:,.0f}원 대비 {diff_ratio*100:.0f}% 차이",
                    "avg_price": int(avg_price),
                    "min_price": min_price,
                    "max_price": max_price,
                    "suggestion": int(avg_price)
                }
        
        # 기존 범위를 크게 벗어나면 이상치
        if unit_price < min_price * 0.5 or unit_price > max_price * 2:
            return {
                "is_anomaly": True,
                "reason": f"기존 범위 ({min_price:,}~{max_price:,}원) 벗어남",
                "avg_price": int(avg_price),
                "min_price": min_price,
                "max_price": max_price,
                "suggestion": int(avg_price)
            }
        
        return {"is_anomaly": False}

    async def analyze_work_data(
        self,
        question: str,
        data_summary: str,
        user_name: str = None
    ) -> str:
        """
        작업일지 데이터를 분석하고 조언 제공
        
        Args:
            question: 사용자 질문
            data_summary: DB에서 가져온 데이터 요약
            user_name: 사용자 이름
        
        Returns:
            분석 결과 및 조언 문자열
        """
        name_part = f"{user_name}님, " if user_name else ""
        
        prompt = f"""당신은 물류/풀필먼트 작업일지 데이터를 분석하는 전문가입니다.
사용자의 질문에 대해 제공된 데이터를 기반으로 분석하고 조언해주세요.

## 데이터
{data_summary}

## 사용자 질문
"{question}"

## 응답 규칙
- 데이터를 기반으로 구체적인 수치와 함께 분석
- 실용적인 조언이나 인사이트 제공
- 한국어로 친근하게 답변
- 이모지 적절히 사용
- 300자 이내로 간결하게

분석 결과:"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "작업일지 데이터 분석 전문가입니다. 데이터 기반으로 분석하고 조언합니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            result = response.choices[0].message.content.strip()
            return f"📊 {name_part}분석 결과\n━━━━━━━━━━━━━━━━━━━━\n\n{result}"
            
        except Exception as e:
            return f"분석 중 오류가 발생했습니다: {str(e)}"

    async def web_search(
        self,
        query: str,
        max_results: int = 5
    ) -> Dict[str, Any]:
        """
        웹 검색 수행 및 결과 요약
        
        Args:
            query: 검색어
            max_results: 최대 결과 수
        
        Returns:
            {"success": bool, "results": [...], "summary": str}
        """
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
            
            if not results:
                return {"success": False, "error": "검색 결과가 없습니다."}
            
            # GPT로 검색 결과 요약
            search_content = "\n\n".join([
                f"제목: {r['title']}\n내용: {r['snippet']}\n링크: {r['url']}"
                for r in results
            ])
            
            summary_prompt = f"""다음 검색 결과를 한국어로 요약해주세요.

검색어: {query}

검색 결과:
{search_content}

## 요약 규칙
- 핵심 정보만 간결하게 (500자 이내)
- 신뢰할 수 있는 정보 위주
- 출처(링크) 1-2개 포함
- 이모지 적절히 사용"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "웹 검색 결과를 요약하는 AI입니다."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.3,
                max_tokens=600
            )
            
            summary = response.choices[0].message.content
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "summary": summary
            }
            
        except ImportError:
            return {"success": False, "error": "웹 검색 라이브러리가 설치되지 않았습니다."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def chat_response(
        self,
        message: str,
        user_name: Optional[str] = None
    ) -> str:
        """
        일반 대화 응답 생성 (작업일지가 아닌 메시지에 대한 GPT 응답)
        
        Args:
            message: 사용자 메시지
            user_name: 사용자 이름
        
        Returns:
            GPT 응답 메시지
        """
        chat_system_prompt = """당신은 물류센터에서 일하는 친절한 작업일지봇입니다.
사용자와 자연스럽게 대화하면서 도움을 줍니다.

## 성격
- 친근하고 도움이 되는 말투
- 간결하게 답변 (2-3문장 이내)
- 이모지 적절히 사용
- 한국어로 대화

## 주요 기능 안내 (필요시)
- 작업일지 저장: "A업체 1톤하차 50000원" 형식으로 입력
- 취소: "취소", "방금거 취소해줘"
- 수정: "방금거 수정해줘"
- 도움말: "도움말"

## 중요
- 작업일지와 관련 없는 질문에도 친절하게 응답
- 너무 길게 답변하지 않기
- 물류/창고 관련 질문에 도움이 되도록"""

        user_prompt = message
        if user_name:
            user_prompt = f"[{user_name}님의 메시지] {message}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": chat_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,  # 자연스러운 대화를 위해 약간 높게
                max_tokens=200  # 짧은 응답
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"🤖 잠시 오류가 발생했어요. 다시 말씀해주세요!"


# 싱글톤 인스턴스
_parser: Optional[AIParser] = None


def get_ai_parser() -> AIParser:
    """AI 파서 싱글톤 반환"""
    global _parser
    if _parser is None:
        _parser = AIParser()
    return _parser
