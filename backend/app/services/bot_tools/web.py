"""Web search, dashboard URL, and help text tools."""
from typing import Dict

def _web_search(args: Dict, user_id: str, user_name: str) -> Dict:
    """웹 검색"""
    query = args.get("query", "")
    if not query:
        return {"success": False, "error": "검색어를 입력해주세요."}
    
    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
        
        if not results:
            return {"success": False, "error": "검색 결과가 없습니다."}
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "message": f"'{query}' 검색결과 {len(results)}건"
        }
    except ImportError:
        return {"success": False, "error": "웹 검색 라이브러리가 설치되지 않았습니다."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _get_dashboard_url(args: Dict, user_id: str, user_name: str) -> Dict:
    """대시보드 URL"""
    import os
    base_url = os.getenv("FRONTEND_URL", "https://my-streamlit-app-2.vercel.app")
    
    return {
        "success": True,
        "urls": {
            "main": base_url,
            "work_log": f"{base_url}/work-log"
        },
        "message": f"대시보드: {base_url}"
    }

def _get_help(args: Dict, user_id: str, user_name: str) -> Dict:
    """도움말"""
    topic = args.get("topic", "전체")
    
    help_texts = {
        "입력": """📝 작업일지 입력
━━━━━━━━━━━━━━━━━━━━
✨ 자연스럽게 말하면 됩니다!

• "틸리언 1톤하차 3만원"
• "나블리 양품화 20개 800원"
• "어제 틸리언 하차 3만원"

💬 정보가 부족하면 물어봐요:
  "틸리언 하차" → "단가가 얼마예요?"
  "3만원" → 자동으로 완성!

💡 입력 후 '취소'로 바로 삭제 가능

🧵 수선작업일지
• 사진 2장 이상(바코드 / 사진)을 보내기
• "구멍 바느질 1500원"처럼 작업·금액 말하기
• 물류 하차·입고는 기존처럼 입력""",

        "조회": """🔍 조회/검색
━━━━━━━━━━━━━━━━━━━━
자연어로 물어보세요!

📅 기간 조회
• "오늘 작업 보여줘"
• "이번주 뭐했어?"
• "지난달 작업"

🏢 업체별 조회
• "틸리언 작업 보여줘"
• "이번주 나블리"

💰 금액 검색
• "3만원짜리 뭐있어?"
• "5만원 이상"

🔀 조합도 가능!
• "이번주 틸리언 뭐했어?"
• "어제 3만원짜리"

📥 결과에서 엑셀 다운로드 가능""",

        "수정": """✏️ 수정/삭제
━━━━━━━━━━━━━━━━━━━━
🗑️ 삭제
• "취소" / "삭제해줘"
• "방금꺼 지워줘"
• "틸리언 3만원 삭제해줘"

✏️ 수정
• "수정해줘"
• "5만원으로 바꿔줘"
• "업체명 틸리언으로 수정"

📦 일괄 수정
• "오늘 전부 5만원으로"
• "틸리언 단가 3만원으로"

🔄 되돌리기
• "되돌려줘" - 최근 변경 이력
• 번호 선택해서 복구""",

        "분석": """📊 통계/분석
━━━━━━━━━━━━━━━━━━━━
💰 합계
• "이번달 총 얼마?"
• "오늘 합계"

🏢 업체별
• "업체별 합계"
• "틸리언 이번달 얼마?"

📈 비교
• "지난주랑 이번주 비교"
• "저번달이랑 비교해줘"

🏆 순위
• "가장 많이 일한 업체"
• "이번달 Top 5"

🌐 대시보드
• "대시보드" → 웹 링크 제공""",

        "고급": """🔧 고급 기능
━━━━━━━━━━━━━━━━━━━━
📋 메모 추가
• "방금꺼에 메모 추가해줘"
• "급건이라고 메모"

📑 복사
• "어제꺼 오늘로 복사"
• "월요일 작업 복사해줘"

📊 엑셀 일괄 등록
• 엑셀 파일 보내면 자동 등록
• 필수 컬럼: 날짜, 업체명, 분류, 단가

🔍 웹 검색
• "OO업체 정보 찾아줘"

💬 일반 대화
• 아무 질문이나 OK!
• AI가 이해하고 답변해요""",

        "전체": """📚 작업일지봇 사용법
━━━━━━━━━━━━━━━━━━━━

💬 자연어로 편하게 말하세요!
정보가 부족하면 물어보고,
대화하듯 완성해갑니다.

━━━━━━━━━━━━━━━━━━━━
📝 입력 예시
  "틸리언 하차 3만원"
  "나블리 양품화 20개 800원"

🔍 조회 예시
  "오늘 작업 보여줘"
  "이번주 틸리언"

✏️ 수정 예시
  "취소" / "수정해줘"
  "5만원으로 바꿔"

📊 통계 예시
  "이번달 총 얼마?"
  "지난주랑 비교"

━━━━━━━━━━━━━━━━━━━━
📖 상세 도움말
  "도움말 입력"
  "도움말 조회"
  "도움말 수정"
  "도움말 분석"
  "도움말 고급"
━━━━━━━━━━━━━━━━━━━━"""
    }
    
    return {
        "success": True,
        "topic": topic,
        "help_text": help_texts.get(topic, help_texts["전체"]),
        "message": f"도움말: {topic}"
    }
