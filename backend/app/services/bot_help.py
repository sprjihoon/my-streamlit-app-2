"""도움말 주제 분류. 문장 목록이 아니라 방법 신호와 업무 주제로 묶는다."""

from __future__ import annotations

import re
from typing import Optional

HELP_TOPICS = frozenset((
    "all",
    "journal",
    "journal_create",
    "journal_query",
    "journal_edit",
    "repair",
    "repair_create",
    "repair_query",
    "repair_edit",
    "repair_price",
    "query",
    "followup",
    "excel",
    "mode",
))

_SPACE = re.compile(r"\s+")
_TRAIL = re.compile(r"[\s?!.？！。,，．․｡…·•~～、]+$")
_METHOD = (
    "방법", "사용법", "입력법", "하는법", "보는법", "쓰는법", "올리는법",
    "보내는법", "고치는법", "지우는법", "설명", "가르쳐", "가이드", "매뉴얼",
)
_HOW = ("어떻게", "어떡해", "어케")
_TELL = ("알려줘", "알려주세요", "알려주라", "알려주", "궁금해")
_HELP_NOUN = ("기능", "사용", "입력", "저장", "등록", "수정", "조회법", "도움")
_SHORT = frozenset((
    "기능", "기능설명", "사용법", "도움말", "도움", "헬프",
    "뭐할수있어", "뭐할수있어요", "뭘할수있어",
))


def _compact(text: str) -> str:
    return _TRAIL.sub("", _SPACE.sub("", (text or "").strip()))


def looks_like_help_request(text: str) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if compact in _SHORT:
        return True
    if any(cue in compact for cue in _METHOD):
        return True
    if any(cue in compact for cue in _HOW):
        return True
    return any(cue in compact for cue in _TELL) and any(cue in compact for cue in _HELP_NOUN)


def resolve_help_topic(text: str, mode: Optional[str] = None) -> str:
    compact = _compact(text)
    if compact in _SHORT or compact.startswith("기능설명"):
        return "all"
    if any(cue in compact for cue in ("엑셀", "업로드", "일괄등록")):
        return "excel"
    if any(cue in compact for cue in ("후속", "이어서물어", "이어서보")) or (
        any(cue in compact for cue in ("지난달", "탑5", "탑3", "업체명", "금액순", "수량순"))
        and any(cue in compact for cue in _METHOD + _HOW)
    ):
        return "followup"
    if any(cue in compact for cue in ("모드시작", "모드종료", "모드선택", "모드바꾸는", "모드변경")):
        return "mode"

    repair = "수선" in compact
    journal = "작업일지" in compact or (
        "일지" in compact and "수선일지" not in compact
    )
    query_mode = "조회모드" in compact or compact.startswith("조회")

    if repair and any(cue in compact for cue in ("가격", "단가", "얼마", "항목", "요금")):
        return "repair_price"
    if repair and any(cue in compact for cue in ("수정", "바꾸", "바꿔", "고치", "고쳐", "삭제", "지워")):
        return "repair_edit"
    if repair and any(cue in compact for cue in ("조회", "실적", "목록", "리스트", "몇건", "집계", "찾아")):
        return "repair_query"
    if repair:
        return "repair_create" if any(cue in compact for cue in ("입력", "저장", "등록", "사진", "바코드", "쓰는", "적어")) or looks_like_help_request(text) else "repair"

    if journal and any(cue in compact for cue in ("수정", "바꾸", "바꿔", "고치", "고쳐", "삭제", "지워")):
        return "journal_edit"
    if journal and any(cue in compact for cue in ("조회", "실적", "목록", "리스트", "몇건", "집계", "찾아", "보여")):
        return "journal_query"
    if journal:
        return "journal_create" if any(cue in compact for cue in ("입력", "저장", "등록", "쓰는", "적어")) or looks_like_help_request(text) else "journal"

    if query_mode or (compact.startswith("조회") and looks_like_help_request(text)):
        return "query"
    if "모드" in compact and looks_like_help_request(text):
        return "mode"

    if mode == "repair":
        if any(cue in compact for cue in ("수정", "바꾸", "바꿔", "고쳐")):
            return "repair_edit"
        if any(cue in compact for cue in ("조회", "실적", "목록")):
            return "repair_query"
        if any(cue in compact for cue in ("입력", "저장", "사진")):
            return "repair_create"
    if mode == "journal":
        if any(cue in compact for cue in ("수정", "바꾸", "바꿔", "고쳐")):
            return "journal_edit"
        if any(cue in compact for cue in ("조회", "실적", "목록")):
            return "journal_query"
        if any(cue in compact for cue in ("입력", "저장")):
            return "journal_create"
    if mode == "query":
        return "query"
    return "all"


def render_help(topic: str) -> str:
    key = topic if topic in _GUIDES else "all"
    return _GUIDES[key]


_GUIDES = {
    "all": (
        "모드별 기능 안내\n"
        "정해진 단어를 외울 필요는 없습니다. 지금 모드에서 말하면 됩니다.\n"
        "더 자세히 보려면 `수선입력방법 알려줘`, `일지 조회 어떻게 해`, `수정방법`처럼 물어보세요.\n"
        "\n"
        "• 일지모드\n"
        "  저장: 업체·작업·단가·수량·날짜·비고를 한 문장으로 등록. 빠진 값은 이어서 묻습니다.\n"
        "  예: 어제 틸 하차 다섯 개 건당 3만원, 야간\n"
        "  단가: 개당/총액을 구분합니다. 작업명이 하나면 최근 단가를 제안합니다.\n"
        "  조회: 이번달 작업실적, 오늘 틸리언 작업 보여줘, 업체별, 탑5\n"
        "  후속: 업체명 / 금액순 / 수량순 / 지난달은 앞 조회를 이어서 봅니다.\n"
        "  수정: 목록의 첫 번째·두 번째, 또는 방금 저장한 기록을 미리보기 후 네/취소.\n"
        "  수선일지 저장은 수선모드에서 합니다.\n"
        "  시작: 일지 / 일지모드\n"
        "\n"
        "• 수선모드\n"
        "  저장: 사진 2장 이상 + 작업·금액. 바코드가 있으면 업체·제품·옵션을 채웁니다.\n"
        "  비고는 선택입니다. `비고에 급해`, `급건이라고 메모`처럼 항목마다 넣을 수 있습니다.\n"
        "  예: 구멍 바느질 1500원 비고 급해\n"
        "  조회: 이번달 수선실적, 이달에 수선 전체리스트, 오늘 수선 작업한 업체, 봉제 몇건\n"
        "  후속: 업체명 / 탑5 업체명 / 금액순 / 지난달은 신규 입력이 아닙니다.\n"
        "  가격: 부분세탁 얼마야, 수선항목과 가격\n"
        "  수정: 두 번째 거 금액 2천원으로 바꿔 → 미리보기 → 네\n"
        "  작성 중 업체명을 물으면 그 값은 초안에 넣습니다.\n"
        "  작업일지 저장은 일지모드에서 합니다.\n"
        "  시작: 수선 / 수선. / 수선모드\n"
        "\n"
        "• 조회모드\n"
        "  작업일지·수선일지 목록·건수·수량·금액, 업체·작업별 묶음, 단가·수선 가격\n"
        "  조회만 합니다. 저장·수정·삭제는 할 수 없습니다.\n"
        "  예: 오늘 수선작업 몇 건 / 봉제 몇 건 / 방금 저장된 수선항목\n"
        "  시작: 조회 / 조회모드\n"
        "\n"
        "공통: 모드 종료 / 현재 모드 / 기능설명\n"
        "엑셀 파일은 모드와 관계없이 작업일지 일괄 등록에 씁니다."
    ),
    "journal_create": (
        "일지 입력 방법\n"
        "일지모드에서 한 문장으로 말하면 됩니다.\n"
        "예: 어제 틸 하차 다섯 개 건당 3만원, 야간\n"
        "예: 틸리언 1톤하차 3만원\n"
        "빠진 업체·작업·단가는 이어서 묻습니다. 나눠 답해도 초안에 합쳐집니다.\n"
        "개당/총액을 구분해 주세요. 작업명이 하나면 최근 단가를 제안합니다.\n"
        "시작: 일지 / 일지모드"
    ),
    "journal_query": (
        "일지 조회 방법\n"
        "일지모드나 조회모드에서 물어보세요.\n"
        "예: 이번달 작업실적 / 오늘 틸리언 작업 보여줘 / 업체별로 / 탑5\n"
        "이어서 `업체명`, `금액순`, `지난달은`이라고 하면 앞 조회를 유지합니다.\n"
        "수선일지 조회는 수선모드나 조회모드에서 합니다."
    ),
    "journal_edit": (
        "일지 수정 방법\n"
        "먼저 목록을 본 뒤 번호를 말하거나, 방금 저장한 기록을 가리키세요.\n"
        "예: 첫 번째 거 수량 5건으로 바꿔\n"
        "예: 방금 저장한 거 잘못됐어 / 방금 거 단가 3만원으로\n"
        "미리보기를 보여 주면 `네`로 확정, `취소`로 중단합니다. 확인 전에는 저장되지 않습니다."
    ),
    "repair_create": (
        "수선 입력 방법\n"
        "수선모드에서 사진 2장 이상을 보낸 뒤 작업과 금액을 말하세요.\n"
        "예: 구멍 바느질 1500원 비고 급해\n"
        "비고/메모는 선택입니다. 저장할 때 넣거나, 방금 저장한 항목에 `비고에 급해`처럼 추가할 수 있습니다.\n"
        "바코드가 보이면 업체·제품·옵션을 채웁니다. 없으면 업체명·제품명을 이어서 묻습니다.\n"
        "작성 중 업체명을 물으면 `틸리언`처럼 답한 값은 초안에 들어갑니다.\n"
        "시작: 수선 / 수선. / 수선모드"
    ),
    "repair_query": (
        "수선 조회 방법\n"
        "수선모드나 조회모드에서 물어보세요.\n"
        "예: 이번달 수선실적 / 이달에 수선 전체리스트 / 오늘 수선 작업한 업체 / 봉제 몇건\n"
        "이어서 `업체명`, `탑5 업체명`, `금액순`, `지난달은`이라고 하면 앞 조회를 이어서 봅니다.\n"
        "이 문장들은 새 수선이나 사진 요청이 아닙니다."
    ),
    "repair_edit": (
        "수선 수정 방법\n"
        "목록을 본 뒤 번호를 말하거나, 방금 저장한 기록을 가리키세요.\n"
        "예: 두 번째 거 금액 2천원으로 바꿔\n"
        "예: 방금 저장한 거 잘못됐어\n"
        "예: 비고에 급해 / 급건이라고 메모\n"
        "미리보기에서 변경 전·후를 확인한 뒤 `네`를 보내야 1건만 수정됩니다."
    ),
    "repair_price": (
        "수선 가격 확인 방법\n"
        "예: 부분세탁 얼마야 / 수선항목과 가격 / 수선은 뭐가 돼?\n"
        "작업명이 하나면 그 가격만, 아니면 등록된 수선 작업 목록을 보여 줍니다.\n"
        "기록 건수·목록을 묻는 말은 가격표가 아니라 조회입니다."
    ),
    "query": (
        "조회모드 사용 방법\n"
        "작업일지·수선일지 목록, 건수, 수량, 금액, 업체·작업별 묶음, 단가·수선 가격을 봅니다.\n"
        "예: 오늘 수선작업 몇 건 / 봉제 몇 건 / 방금 저장된 수선항목\n"
        "조회만 합니다. 저장·수정·삭제는 일지모드 또는 수선모드에서 하세요.\n"
        "시작: 조회 / 조회모드"
    ),
    "followup": (
        "조회 후속 질문\n"
        "한 번 조회한 뒤에는 짧은 말로 조건을 바꿀 수 있습니다.\n"
        "예: 이번달수선실적 → 업체명 → 탑5 → 금액순 → 지난달은\n"
        "`업체명`, `업체별로`, `탑5`, `금액순`, `수량순`, `지난달은`은 새 입력이 아닙니다.\n"
        "작성 중 업체명을 기다리고 있을 때만 그 값이 초안으로 들어갑니다."
    ),
    "excel": (
        "엑셀 업로드\n"
        "모드와 관계없이 작업일지 엑셀을 보내면 기존 일괄 등록 경로로 저장합니다.\n"
        "수선일지 엑셀 일괄 등록은 이 봇 대화가 아니라 웹에서 합니다."
    ),
    "mode": (
        "모드 사용 방법\n"
        "일지 / 일지모드 → 작업일지 저장·같은 영역 조회·수정\n"
        "수선 / 수선. / 수선모드 → 수선 저장·사진·같은 영역 조회·수정\n"
        "조회 / 조회모드 → 조회만. 쓰기 없음\n"
        "모드 종료 / 현재 모드 / 기능설명"
    ),
}
_GUIDES["journal"] = _GUIDES["journal_create"] + "\n\n" + _GUIDES["journal_query"] + "\n\n" + _GUIDES["journal_edit"]
_GUIDES["repair"] = _GUIDES["repair_create"] + "\n\n" + _GUIDES["repair_query"] + "\n\n" + _GUIDES["repair_edit"]
