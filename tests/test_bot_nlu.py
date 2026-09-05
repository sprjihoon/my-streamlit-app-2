"""GPT NLU 계층. 실제 OpenAI는 호출하지 않고 mock만 사용한다."""
from __future__ import annotations

import asyncio
import inspect
import json
from unittest.mock import AsyncMock, patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.services.bot_intent import ACTION_UPDATE, TARGET_LAST_SAVED
from backend.app.services.bot_mode import (
    MODE_IDLE,
    MODE_JOURNAL,
    MODE_QUERY,
    MODE_REPAIR,
    get_mode,
    mode_feature_guide,
    set_mode,
)
from backend.app.services.bot_nlu import (
    NluIntent,
    SYSTEM_PROMPT,
    _complete_chat,
    collect_nlu_context,
    enforce_nlu_policy,
    fallback_from_local_parsers,
    gpt_payload,
    interpret_or_fallback,
    interpret_user_text,
    nlu_to_bot_intent,
    nlu_to_mode_command,
    parse_nlu_payload,
    render_readonly_nlu,
)
from backend.app.services.conversation_state import get_conversation_manager
from backend.app.services.repair_bot import handle_user_text
from backend.app.services.repair_edit import get_last_saved_id, remember_last_saved
from backend.app.api.repair_log import insert_repair_log_record
from logic.db import get_connection


def _ids(suffix: str):
    return f"nlu-user-{suffix}", f"nlu-ch-{suffix}"


def _payload(**overrides):
    body = {
        "domain": "repair",
        "action": "unknown",
        "target": "none",
        "fields": {
            "unit_price": None,
            "qty": None,
            "defect": None,
            "work_type": None,
            "remark": None,
            "vendor": None,
            "product": None,
            "mode": None,
            "topic": None,
        },
        "confidence": 0.95,
        "needs_confirmation": False,
        "clarification": None,
    }
    extra_fields = overrides.pop("fields", {})
    body.update(overrides)
    body["fields"] = {**body["fields"], **extra_fields}
    return body


def _mock_chat(payload: dict):
    async def _complete(messages):
        dumped = json.dumps(messages, ensure_ascii=False)
        assert "OPENAI_API_KEY" not in dumped
        assert "sk-" not in dumped
        assert "DATABASE_PATH" not in dumped
        assert "billing.db" not in dumped
        user = json.loads(messages[1]["content"])
        assert set(user) == {
            "mode",
            "pending_step",
            "missing_fields",
            "draft_fields",
            "has_last_saved",
            "last_assistant_reply",
            "user_message",
        }
        return json.dumps(payload, ensure_ascii=False)

    return _complete


def test_nlu_module_has_no_phrase_dictionary():
    import backend.app.services.bot_nlu as bot_nlu

    source = inspect.getsource(bot_nlu.fallback_from_local_parsers)
    for phrase in ("수선할래", "수선할게", "일지 쓸게", "조회할게", "이천원", "부분세탁으로"):
        assert phrase not in source
        assert "수선할래" not in inspect.getsource(bot_nlu.parse_nlu_payload)
        assert "strict" in inspect.getsource(_complete_chat)
        assert "json_schema" in inspect.getsource(_complete_chat)
        assert "의미 예시" in SYSTEM_PROMPT


def test_context_omits_secrets_and_file_paths(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-should-never-go-to-gpt")
    uid, cid = _ids("ctx")
    set_mode(uid, cid, MODE_REPAIR)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "work_type": "단순바느질",
            "qty": 1,
            "barcode_image": "C:/secret/uploads/repair/a.jpg",
            "before_image": "/tmp/before.png",
        },
        missing=["photos"],
        last_question="사진 3장 보내주세요.",
    )
    ctx = collect_nlu_context(uid, cid, "가격 바꿔줘")
    payload = gpt_payload(ctx)
    blob = json.dumps({"ctx": ctx, "payload": payload}, ensure_ascii=False)
    assert "sk-secret" not in blob
    assert "OPENAI_API_KEY" not in blob
    assert "barcode_image" not in json.dumps(payload)
    assert "before_image" not in json.dumps(payload)
    assert payload["mode"] == MODE_REPAIR
    assert payload["pending_step"] == "photos"
    assert payload["draft_fields"]["vendor"] == "로지킴"
    assert payload["user_message"] == "가격 바꿔줘"
    assert "last_assistant_reply" in payload
    assert "has_active_draft" not in payload


def test_parse_rejects_trusted_source_and_strips_unknown_fields():
    raw = _payload(action="provide_field", fields={"qty": 1, "sql": "DROP", "trusted_source": "excel"})
    raw["trusted_source"] = "excel_upload"
    try:
        parse_nlu_payload(raw)
        assert False, "trusted_source must be rejected"
    except ValueError as exc:
        assert "trusted_source" in str(exc)
    clean = parse_nlu_payload(_payload(action="provide_field", fields={"qty": 1, "sql": "DROP"}))
    assert clean.fields == {"qty": 1}
    assert "sql" not in clean.fields


def test_policy_draft_default_and_last_saved_confirm():
    draft_ctx = {"has_active_draft": True, "has_last_saved": True}
    drafted = enforce_nlu_policy(
        NluIntent(action="update", target="none", fields={"unit_price": 2000}, confidence=0.9),
        draft_ctx,
    )
    assert drafted.action == "provide_field"
    assert drafted.target == "draft"
    assert drafted.needs_confirmation is False

    saved = enforce_nlu_policy(
        NluIntent(action="update", target="last_saved", fields={"unit_price": 2000}, confidence=0.95),
        {"has_active_draft": False, "has_last_saved": True},
    )
    assert saved.action == "update"
    assert saved.target == "last_saved"
    assert saved.needs_confirmation is True
    assert saved.explicit_last_saved is True


def test_policy_low_confidence_asks_once():
    out = enforce_nlu_policy(
        NluIntent(action="update", target="last_saved", fields={"qty": 3}, confidence=0.2),
        {"has_active_draft": False, "has_last_saved": True},
    )
    assert out.action == "unknown"
    assert out.clarification
    assert out.needs_confirmation is False


def test_meaning_variants_use_same_mocked_contract(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    cases = [
        ("수선모드", _payload(action="start_mode", domain="repair", fields={"mode": "repair"})),
        ("수선할게", _payload(action="start_mode", domain="repair", fields={"mode": "repair"})),
        ("수선 시작하자", _payload(action="start_mode", domain="repair", fields={"mode": "repair"})),
        ("일지 쓸게", _payload(action="start_mode", domain="journal", fields={"mode": "journal"})),
        ("조회할게", _payload(action="start_mode", domain="query", fields={"mode": "query"})),
        ("1", _payload(action="provide_field", fields={"qty": 1})),
        ("하나", _payload(action="provide_field", fields={"qty": 1})),
        ("한 개", _payload(action="provide_field", fields={"qty": 1})),
        ("한 건", _payload(action="provide_field", fields={"qty": 1})),
        ("방금 저장한 거 잘못됐어", _payload(action="update", target="last_saved", needs_confirmation=True)),
        ("아까 것 좀 고칠게", _payload(action="update", target="last_saved", needs_confirmation=True)),
        ("가격 이천원으로 해줘", _payload(action="update", fields={"unit_price": 2000})),
        ("구멍 말고 지퍼야", _payload(action="provide_field", fields={"defect": "지퍼"})),
        ("부분세탁으로 처리해", _payload(action="provide_field", fields={"work_type": "부분세탁"})),
    ]
    uid, cid = _ids("variants")
    set_mode(uid, cid, MODE_IDLE)
    for text, payload in cases:
        with patch("backend.app.services.bot_nlu._complete_chat", _mock_chat(payload)):
            intent = asyncio.run(interpret_user_text(text, collect_nlu_context(uid, cid, text)))
        if payload["action"] == "start_mode":
            assert intent.action == "start_mode", text
            assert nlu_to_mode_command(intent)["mode"] in {MODE_REPAIR, MODE_JOURNAL, MODE_QUERY}
        elif payload["action"] == "update" and payload.get("target") == "last_saved":
            assert intent.action == "update", text
            assert intent.target == "last_saved", text
            assert intent.needs_confirmation is True, text
        elif payload["fields"].get("qty") is not None:
            assert intent.fields.get("qty") == 1, text
        elif payload["fields"].get("unit_price") is not None:
            assert intent.fields.get("unit_price") == 2000, text
        elif payload["fields"].get("defect"):
            assert intent.fields.get("defect") == "지퍼", text
        elif payload["fields"].get("work_type"):
            assert intent.fields.get("work_type") == "부분세탁", text


def test_flexible_mode_start_via_webhook(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    uid, cid = _ids("mode")
    set_mode(uid, cid, MODE_IDLE)
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()
    payload = _payload(action="start_mode", domain="repair", fields={"mode": "repair"})

    async def _run():
        with patch("backend.app.api.naver_works_webhook.get_naver_works_client", return_value=nw), patch(
            "backend.app.services.bot_nlu._complete_chat", _mock_chat(payload)
        ):
            await process_message(uid, cid, "수선할래", "group", "테스터")

    asyncio.run(_run())
    assert get_mode(uid, cid) == MODE_REPAIR
    sent = " ".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)
    assert "수선모드" in sent


def test_qty_hana_goes_to_existing_repair_state_machine():
    uid, cid = _ids("qty")
    set_mode(uid, cid, MODE_REPAIR)
    get_conversation_manager().set_state(
        user_id=uid,
        channel_id=cid,
        pending_data={
            "entry_type": "repair",
            "vendor": "로지킴",
            "product": "릴리프T",
            "work_type": "단순바느질",
            "unit_price": 1500,
            "price_stated": True,
            "user_name": "테스터",
            "awaiting_price_confirm": True,
        },
        missing=["qty"],
        last_question="몇 건인지 숫자로 알려주세요.",
    )
    before = _log_count()
    nlu = NluIntent(action="provide_field", target="draft", fields={"qty": 1}, confidence=0.93, domain="repair")
    reply = asyncio.run(handle_user_text(uid, cid, "하나", "테스터", nlu_intent=nlu))
    assert "✅" in reply
    assert _log_count() == before + 1


def test_last_saved_natural_phrase_previews_without_write():
    uid, cid = _ids("last")
    set_mode(uid, cid, MODE_REPAIR)
    saved = insert_repair_log_record(
        날짜="2026-09-05",
        작업="단순바느질",
        비용=1500,
        업체명="로지킴",
        제품명="릴리프T",
        불량명="구멍",
        수량=1,
        작성자="테스터",
        출처="bot",
    )
    rid = saved["id"]
    remember_last_saved(uid, cid, rid)
    before = _cost(rid)
    nlu = NluIntent(
        action="update",
        target="last_saved",
        fields={"unit_price": 2000},
        confidence=0.96,
        needs_confirmation=True,
        explicit_last_saved=True,
        domain="repair",
    )
    preview = asyncio.run(handle_user_text(uid, cid, "방금 저장한 거 잘못됐어", "테스터", nlu_intent=nlu))
    assert "수정할까요" in preview
    assert _cost(rid) == before
    assert get_last_saved_id(uid, cid) == rid
    done = asyncio.run(handle_user_text(uid, cid, "네", "테스터"))
    assert "수정했어요" in done
    assert _cost(rid) == 2000


def test_gpt_timeout_and_invalid_json_use_local_fallback(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    uid, cid = _ids("fb")
    set_mode(uid, cid, MODE_REPAIR)

    async def _timeout(_messages):
        raise TimeoutError("nlu timeout")

    with patch("backend.app.services.bot_nlu._complete_chat", _timeout):
        timed = asyncio.run(interpret_or_fallback(uid, cid, "직전내용수정"))
    assert timed.source == "fallback"
    assert timed.action == "update"
    assert timed.target == "last_saved"

    async def _bad_json(_messages):
        return "not-json"

    with patch("backend.app.services.bot_nlu._complete_chat", _bad_json):
        broken = asyncio.run(interpret_or_fallback(uid, cid, "직전내용수정"))
    assert broken.source == "fallback"
    assert broken.action == "update"


def test_disabled_nlu_does_not_call_openai(monkeypatch):
    called = {"n": 0}

    async def _complete(_messages):
        called["n"] += 1
        raise AssertionError("live openai")

    monkeypatch.setenv("BOT_NLU_DISABLE", "1")
    uid, cid = _ids("off")
    with patch("backend.app.services.bot_nlu._complete_chat", _complete):
        out = asyncio.run(interpret_or_fallback(uid, cid, "일지모드 시작"))
    assert called["n"] == 0
    assert out.source == "fallback"
    assert out.action == "start_mode"


def test_nlu_intent_maps_to_existing_bot_intent():
    mapped = nlu_to_bot_intent(
        NluIntent(
            action="update",
            target="last_saved",
            fields={"unit_price": 2000},
            needs_confirmation=True,
            explicit_last_saved=True,
            confidence=0.9,
            domain="repair",
        ),
        "가격 이천원으로 해줘",
    )
    assert mapped.action == ACTION_UPDATE
    assert mapped.target == TARGET_LAST_SAVED
    assert mapped.fields["unit_price"] == 2000
    assert mapped.needs_confirmation is True


def test_fallback_parser_still_handles_exact_mode_command():
    intent = fallback_from_local_parsers("수선모드 시작", {})
    assert intent.action == "start_mode"
    assert nlu_to_mode_command(intent)["mode"] == MODE_REPAIR


def _sent_text(uid: str, cid: str, text: str, payload: dict) -> str:
    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ), patch("backend.app.services.bot_nlu._complete_chat", _mock_chat(payload)):
            await process_message(uid, cid, text, "group", "테스터")

    asyncio.run(_run())
    return "\n".join(str(call.args[1]) for call in nw.send_text_message.await_args_list)


def test_idle_기능_shows_full_guide(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    uid, cid = _ids("help-fn")
    set_mode(uid, cid, MODE_IDLE)
    sent = _sent_text(
        uid, cid, "기능",
        _payload(action="show_help", domain="none", fields={"topic": "all"}),
    )
    guide = mode_feature_guide()
    assert "모드별 기능 안내" in sent
    assert "일지모드" in sent and "수선모드" in sent and "조회모드" in sent
    assert "사용할 모드를 선택해주세요." not in sent or guide in sent
    assert get_mode(uid, cid) == MODE_IDLE


def test_기능설명해줘_does_not_ask_again(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    uid, cid = _ids("help-long")
    set_mode(uid, cid, MODE_IDLE)
    sent = _sent_text(
        uid, cid, "기능설명해줘",
        _payload(action="show_help", domain="none", fields={"topic": "all"}),
    )
    assert "모드별 기능 안내" in sent
    assert "한 가지만 확인할게요" not in sent
    assert "어떤 모드를 시작할까요" not in sent
    assert get_mode(uid, cid) == MODE_IDLE


def test_idle_repair_catalog_lists_prices(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    from backend.app.services.repair_catalog import upsert_work_type

    upsert_work_type("단순바느질", 1500)
    uid, cid = _ids("cat-idle")
    set_mode(uid, cid, MODE_IDLE)
    before = _log_count()
    sent = _sent_text(
        uid, cid, "수선항목과 가격",
        _payload(action="query_catalog", domain="repair", fields={"topic": "repair_work_prices"}),
    )
    assert "단순바느질" in sent
    assert "1,500원" in sent
    assert "사용할 모드를 선택해주세요." not in sent
    assert get_mode(uid, cid) == MODE_IDLE
    assert _log_count() == before


def test_수선은_뭐가_돼_shows_price_list(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    from backend.app.services.repair_catalog import upsert_work_type

    upsert_work_type("부분세탁", 3000)
    uid, cid = _ids("cat-what")
    set_mode(uid, cid, MODE_IDLE)
    sent = _sent_text(
        uid, cid, "수선은 뭐가 돼?",
        _payload(action="query_catalog", domain="repair", fields={"topic": "repair_work_prices"}),
    )
    assert "부분세탁" in sent
    assert "3,000원" in sent


def test_followup_price_uses_last_assistant_reply(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    from backend.app.services.repair_catalog import upsert_work_type

    upsert_work_type("열펜제거", 2000)
    uid, cid = _ids("follow")
    set_mode(uid, cid, MODE_IDLE)
    previous = "수선모드에서는 작업 종류와 기본 가격을 확인할 수 있어요."
    get_conversation_manager().add_message(uid, cid, "assistant", previous)
    ctx = collect_nlu_context(uid, cid, "그럼 가격은?")
    assert previous in ctx["last_assistant_reply"]
    assert len(ctx["last_assistant_reply"]) <= 500
    sent = _sent_text(
        uid, cid, "그럼 가격은?",
        _payload(action="query_catalog", domain="repair", fields={"topic": "repair_work_prices"}),
    )
    assert "열펜제거" in sent
    assert "2,000원" in sent
    assert render_readonly_nlu(
        NluIntent(action="query_catalog", fields={"topic": "repair_work_prices"})
    )


def test_last_assistant_reply_strips_secrets_and_truncates():
    uid, cid = _ids("secret-hist")
    get_conversation_manager().add_message(
        uid, cid, "assistant", "OPENAI_API_KEY=sk-secret-value " + ("가" * 600)
    )
    ctx = collect_nlu_context(uid, cid, "그건 얼마야?")
    assert ctx["last_assistant_reply"] == ""
    get_conversation_manager().clear_history(uid, cid)
    get_conversation_manager().add_message(uid, cid, "assistant", "수선 가격 안내입니다. " + ("나" * 600))
    ctx2 = collect_nlu_context(uid, cid, "그건 얼마야?")
    assert "수선 가격" in ctx2["last_assistant_reply"]
    assert len(ctx2["last_assistant_reply"]) <= 500
    assert "sk-secret" not in ctx2["last_assistant_reply"]


def _log_count():
    with get_connection() as con:
        return con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0]


def _cost(record_id: int):
    with get_connection() as con:
        return con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (record_id,)).fetchone()[0]
