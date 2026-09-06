"""도움말 주제. 여러 물음이 같은 topic으로 접히고, 실제 조회는 빼앗지 않는다."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.services.bot_help import looks_like_help_request, render_help, resolve_help_topic
from backend.app.services.bot_mode import MODE_IDLE, MODE_REPAIR, get_mode, parse_mode_command, set_mode
from backend.app.services.bot_nlu import interpret_or_fallback
from backend.app.services.bot_query import looks_like_query_read


def _sent(uid, cid, text, user_name="장지훈"):
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ):
            await process_message(uid, cid, text, "group", user_name)

    asyncio.run(_run())
    return "\n".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)


def test_repair_input_questions_share_one_topic():
    for text in (
        "수선입력방법 알려줘",
        "수선 입력 방법",
        "수선 어떻게 입력해",
        "수선 저장하는 법",
        "수선 등록 방법 설명해줘",
        "수선 사진 어떻게 보내",
        "수선 바코드 입력법",
        "수선 쓰는법 알려주세요",
    ):
        assert looks_like_help_request(text)
        assert resolve_help_topic(text) == "repair_create"
        assert parse_mode_command(text) is None
        assert not looks_like_query_read(text)
    guide = render_help("repair_create")
    assert "사진 2장" in guide
    assert "구멍 바느질" in guide


def test_other_help_questions_collapse_to_topics():
    cases = {
        "journal_create": ("일지 입력방법", "작업일지 어떻게 써", "일지 저장하는 법 알려줘"),
        "journal_query": ("일지 조회 어떻게 해", "작업일지 실적 보는 방법", "일지 목록 보는법"),
        "journal_edit": ("일지 수정방법", "작업일지 어떻게 바꿔", "일지 삭제하는 법"),
        "repair_query": ("수선 조회 방법", "수선실적 어떻게 봐", "수선 목록 보는법"),
        "repair_edit": ("수선 수정방법", "수선 어떻게 고쳐", "수선 삭제하는 법"),
        "repair_price": ("수선 가격 확인 방법", "수선항목 어떻게 봐", "수선 얼마인지 보는법"),
        "query": ("조회모드 사용법", "조회 어떻게 해"),
        "followup": ("지난달은 어떻게 물어봐", "탑5 업체명 사용법", "조회 후속 질문 설명"),
        "excel": ("엑셀 업로드 방법", "엑셀로 일지 올리는법"),
        "mode": ("모드 시작하는 방법", "모드 종료 어떻게 해"),
        "all": ("기능설명", "뭐할수있어", "사용법"),
    }
    for topic, phrases in cases.items():
        for text in phrases:
            assert looks_like_help_request(text), text
            assert resolve_help_topic(text) == topic, (text, resolve_help_topic(text))


def test_real_queries_are_not_help():
    for text in (
        "오늘 수선실적 알려줘",
        "이번달수선실적",
        "봉제 몇건?",
        "오늘 틸리언 작업 보여줘",
        "업체명",
        "두 번째 거 금액 2천원으로 바꿔",
        "부분세탁 얼마야",
    ):
        assert not looks_like_help_request(text), text


def test_webhook_repair_input_help_does_not_start_mode_or_draft():
    uid, cid = "help-in-u", "help-in-c"
    set_mode(uid, cid, MODE_IDLE)
    sent = _sent(uid, cid, "수선입력방법 알려줘")
    assert get_mode(uid, cid) == MODE_IDLE
    assert "수선 입력 방법" in sent
    assert "사진 2장" in sent
    assert "수선모드를 시작했어요" not in sent


def test_interpret_help_skips_gpt(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    called = {"n": 0}

    async def _boom(_messages):
        called["n"] += 1
        raise AssertionError("help should not call gpt")

    with patch("backend.app.services.bot_nlu._complete_chat", _boom):
        intent = asyncio.run(interpret_or_fallback("help-gpt-u", "help-gpt-c", "일지 입력방법 알려줘"))
    assert called["n"] == 0
    assert intent.action == "show_help"
    assert intent.fields.get("topic") == "journal_create"
