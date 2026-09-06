"""실제 OpenAI NLU 비교. 기본 pytest에서는 skip. RUN_LIVE_NLU=1 이고 키가 있을 때만 실행."""
from __future__ import annotations

import asyncio
import os
import statistics
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.api.naver_works_webhook import process_message
from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.bot_dates import seoul_today_str, this_month_range
from backend.app.services.bot_mode import MODE_JOURNAL, MODE_QUERY, MODE_REPAIR, get_mode, set_mode
from backend.app.services.bot_nlu import LAST_NLU_CALL
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_NLU") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="live OpenAI NLU is opt-in",
)

BASE_MODEL = "gpt-4o-mini"
CANDIDATE_MODEL = "gpt-5.6-luna"
PRICES = {
    BASE_MODEL: (0.15, 0.60),
    CANDIDATE_MODEL: (0.20, 1.20),
}


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


def _insert_repair(**kwargs):
    payload = {
        "날짜": seoul_today_str(),
        "작업": "봉제",
        "비용": 700,
        "업체명": "로지킴",
        "제품명": "릴리프T",
        "불량명": "구멍",
        "수량": 3,
        "작성자": "다른사람",
        "출처": "bot",
    }
    payload.update(kwargs)
    return insert_repair_log_record(**payload)


def _insert_work(user_id, **kwargs):
    from datetime import datetime

    payload = {
        "날짜": seoul_today_str(),
        "업체명": "틸리언",
        "분류": "하차",
        "단가": 30000,
        "수량": 2,
        "작성자": "장지훈",
        "works_user_id": user_id,
    }
    payload.update(kwargs)
    payload["합계"] = int(payload["단가"]) * int(payload["수량"])
    with get_connection() as con:
        cur = con.execute(
            """INSERT INTO work_log
               (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                payload["날짜"], payload["업체명"], payload["분류"], payload["단가"],
                payload["수량"], payload["합계"], "", payload["작성자"],
                datetime.now().isoformat(), "bot", payload["works_user_id"],
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def _repair_count():
    with get_connection() as con:
        return int(con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0])


def _repair_cost(rid):
    with get_connection() as con:
        row = con.execute("SELECT 비용 FROM repair_work_log WHERE id = ?", (rid,)).fetchone()
    return None if row is None else int(row[0])


def _ctx(uid, cid):
    return get_conversation_manager().get_query_context(uid, cid) or {}


def _listed_ids(uid, cid):
    return [int(x) for x in (_ctx(uid, cid).get("record_ids") or [])]


def _seed(uid):
    start, end = this_month_range()
    _insert_repair(날짜=start, 업체명="틸리언", 수량=4, 비용=5000)
    _insert_repair(날짜=start, 업체명="틸리언", 수량=2, 비용=2000)
    first = _insert_repair(날짜=end, 업체명="로지킴", 수량=3, 비용=15000)
    second = _insert_repair(날짜=end, 업체명="에이원", 수량=1, 비용=800)
    _insert_work(uid, 업체명="틸리언", 수량=2)
    _insert_work(uid, 업체명="팔로우미코스메틱", 수량=1)
    return first["id"], second["id"]


def _p95(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _cost_usd(model, prompt, completion):
    inp, out = PRICES.get(model, (0.0, 0.0))
    return (prompt / 1_000_000) * inp + (completion / 1_000_000) * out


def _run_model(model, monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    monkeypatch.setenv("BOT_NLU_MODEL", model)
    monkeypatch.setenv("BOT_NLU_REASONING_EFFORT", "low")
    uid, cid = f"live-{model}-u", f"live-{model}-c"
    set_mode(uid, cid, MODE_REPAIR)
    first_id, second_id = _seed(uid)
    rows = []
    latencies = []
    prompt = completion = reasoning = fallbacks = 0
    access_ok = True

    def call(text, *, mock_timeout=False):
        nonlocal prompt, completion, reasoning, fallbacks, access_ok
        LAST_NLU_CALL.clear()
        before = _repair_count()
        if mock_timeout:
            async def _timeout(_messages):
                raise TimeoutError("nlu timeout")

            with patch("backend.app.services.bot_nlu._complete_chat", _timeout):
                reply = _sent(uid, cid, text)
        else:
            try:
                reply = _sent(uid, cid, text)
            except Exception as exc:
                access_ok = False
                return "", before, {"error": type(exc).__name__}
        stats = dict(LAST_NLU_CALL)
        if stats.get("fallback"):
            fallbacks += 1
        prompt += int(stats.get("prompt_tokens") or 0)
        completion += int(stats.get("completion_tokens") or 0)
        reasoning += int(stats.get("reasoning_tokens") or 0)
        if stats.get("latency_ms") is not None:
            latencies.append(float(stats["latency_ms"]))
        if stats.get("error") in {"AuthenticationError", "NotFoundError", "PermissionDeniedError", "nlu_no_key"}:
            access_ok = False
        return reply, before, stats

    r1, _, _ = call("수선")
    rows.append({
        "id": 1,
        "ok": get_mode(uid, cid) == MODE_REPAIR and "수선모드" in r1,
        "critical": False,
        "kind": "routing",
        "reply": r1[:200],
    })

    r2, c2, _ = call("이번달 수선실적")
    photo2 = "사진" in r2
    create2 = "보내" in r2 and "사진" in r2
    ok2 = "수선일지" in r2 and "사진" not in r2 and _repair_count() == c2
    rows.append({
        "id": 2, "ok": ok2, "critical": photo2 or create2 or not ok2,
        "kind": "query", "query_to_create": photo2 or create2, "reply": r2[:200],
    })

    r3, c3, _ = call("업체명")
    lost3 = "업체별" not in r3 and "1." not in r3
    photo3 = "사진" in r3
    ok3 = "업체별" in r3 and "1." in r3 and "사진" not in r3 and _repair_count() == c3
    rows.append({
        "id": 3, "ok": ok3, "critical": lost3 or photo3,
        "kind": "followup", "lost_context": lost3, "query_to_create": photo3, "reply": r3[:200],
    })

    r4, c4, _ = call("수선실적 탑5 업체명")
    ok4 = "1." in r4 and "사진" not in r4 and _ctx(uid, cid).get("limit") == 5 and _repair_count() == c4
    rows.append({
        "id": 4, "ok": ok4, "critical": "사진" in r4 or not ok4,
        "kind": "query", "query_to_create": "사진" in r4, "reply": r4[:200],
    })

    r5, c5, _ = call("이달에 수선 전체리스트")
    price5 = "등록된 수선 작업 비용" in r5
    ok5 = "목록" in r5 and "1." in r5 and not price5 and _repair_count() == c5
    rows.append({
        "id": 5, "ok": ok5, "critical": price5 or "사진" in r5,
        "kind": "query", "query_to_create": "사진" in r5, "reply": r5[:200],
    })

    r6, c6, _ = call("오늘 수선 작업한 업체")
    ok6 = ("업체" in r6) and "사진" not in r6 and _repair_count() == c6
    rows.append({
        "id": 6, "ok": ok6, "critical": "사진" in r6,
        "kind": "query", "query_to_create": "사진" in r6, "reply": r6[:200],
    })

    r7, c7, _ = call("봉제 몇건?")
    ok7 = ("건" in r7 or "개 기록" in r7) and "사진" not in r7 and _repair_count() == c7
    rows.append({
        "id": 7, "ok": ok7, "critical": "사진" in r7,
        "kind": "query", "query_to_create": "사진" in r7, "reply": r7[:200],
    })

    listed = _listed_ids(uid, cid)
    if len(listed) < 2:
        _sent(uid, cid, "이달에 수선 전체리스트")
        listed = _listed_ids(uid, cid)
    target = listed[1] if len(listed) > 1 else second_id
    other = listed[0] if listed else first_id
    before_target = _repair_cost(target)
    r8, _, _ = call("두 번째 거 금액 2천원으로 바꿔")
    wrote8 = _repair_cost(target) != before_target
    name_as_vendor = "장지훈" in r8 and "업체" in r8
    ok8 = ("변경 전" in r8 and "변경 후" in r8) and not wrote8
    rows.append({
        "id": 8, "ok": ok8, "critical": wrote8 or name_as_vendor,
        "kind": "update_preview", "preconfirm_update": wrote8, "reply": r8[:200],
    })

    r9, _, _ = call("네")
    ok9 = _repair_cost(target) == 2000 and _repair_cost(other) != 2000
    rows.append({
        "id": 9, "ok": ok9, "critical": not ok9,
        "kind": "update_confirm", "reply": r9[:200],
    })

    set_mode(uid, cid, MODE_QUERY)
    q_before = {rid: _repair_cost(rid) for rid in (target, other)}
    r10, _, _ = call("두 번째 거 금액 2천원으로 바꿔")
    _sent(uid, cid, "네")
    q_after = {rid: _repair_cost(rid) for rid in (target, other)}
    ok10 = q_before == q_after and ("조회모드" in r10 or "읽기" in r10)
    rows.append({
        "id": 10, "ok": ok10, "critical": q_before != q_after,
        "kind": "query_write_block", "preconfirm_update": q_before != q_after, "reply": r10[:200],
    })

    set_mode(uid, cid, MODE_JOURNAL)
    r11, _, _ = call("오늘 틸리언 작업 보여줘")
    vendor_wrong = "장지훈" in (_ctx(uid, cid).get("filters") or {}).get("vendor", "")
    ok11 = get_mode(uid, cid) == MODE_JOURNAL and "틸리언" in r11 and "사진" not in r11
    rows.append({
        "id": 11, "ok": ok11, "critical": vendor_wrong or "사진" in r11,
        "kind": "journal_query", "username_as_vendor": vendor_wrong, "reply": r11[:200],
    })

    set_mode(uid, cid, MODE_REPAIR)
    before12 = _repair_count()
    r12, _, _ = call("그냥 그거", mock_timeout=True)
    draft = (get_conversation_manager().get_state(uid, cid) or {}).get("pending_data") or {}
    ok12 = _repair_count() == before12 and draft.get("entry_type") != "repair"
    rows.append({
        "id": 12, "ok": ok12, "critical": not ok12,
        "kind": "timeout_fallback", "reply": r12[:200],
    })

    critical = sum(1 for row in rows if row.get("critical"))
    query_to_create = sum(1 for row in rows if row.get("query_to_create"))
    passed = sum(1 for row in rows if row.get("ok"))
    return {
        "model": model,
        "access_ok": access_ok,
        "accuracy": passed / len(rows),
        "passed": passed,
        "total": len(rows),
        "critical": critical,
        "query_to_create": query_to_create,
        "avg_ms": statistics.mean(latencies) if latencies else 0.0,
        "p95_ms": _p95(latencies),
        "fallbacks": fallbacks,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "est_usd": _cost_usd(model, prompt, completion),
        "cases": rows,
    }


def test_live_nlu_model_comparison(monkeypatch):
    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY missing")
    base = _run_model(BASE_MODEL, monkeypatch)
    luna = _run_model(CANDIDATE_MODEL, monkeypatch)
    print("LIVE_NLU_BASE", {k: v for k, v in base.items() if k != "cases"})
    print("LIVE_NLU_LUNA", {k: v for k, v in luna.items() if k != "cases"})
    assert base["total"] == 12
    assert luna["total"] == 12
    if luna["access_ok"]:
        assert luna["critical"] == 0
        assert luna["accuracy"] >= base["accuracy"]
