"""모드별 조회·집계·수정. 응답과 실제 record ID·DB 전후값을 함께 검증한다."""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.bot_dates import seoul_today_str
from backend.app.services.bot_mode import MODE_JOURNAL, MODE_QUERY, MODE_REPAIR, get_mode, set_mode
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection


def _ids(suffix: str):
    return f"mdo-user-{suffix}", f"mdo-ch-{suffix}"


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
    reply = "\n".join(str(c.args[1]) for c in nw.send_text_message.await_args_list)
    print(f"\n[{get_mode(uid, cid)}] {text!r}\n{reply}\n")
    return reply


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
                payload["수량"], payload["합계"], payload.get("비고1") or "",
                payload["작성자"], datetime.now().isoformat(), "bot", payload["works_user_id"],
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def _repair_row(record_id: int):
    with get_connection() as con:
        row = con.execute(
            "SELECT id, 업체명, 작업, 수량, 비용 FROM repair_work_log WHERE id = ?",
            (int(record_id),),
        ).fetchone()
    return None if not row else {"id": row[0], "vendor": row[1], "work": row[2], "qty": row[3], "cost": row[4]}


def _work_row(record_id: int):
    with get_connection() as con:
        row = con.execute(
            "SELECT id, 업체명, 분류, 수량, 단가 FROM work_log WHERE id = ?",
            (int(record_id),),
        ).fetchone()
    return None if not row else {"id": row[0], "vendor": row[1], "work": row[2], "qty": row[3], "price": row[4]}


def _listed_ids(uid, cid):
    ctx = get_conversation_manager().get_query_context(uid, cid) or {}
    return [int(x) for x in (ctx.get("record_ids") or [])]


def _sql_repair_vendor_groups():
    today = seoul_today_str()
    with get_connection() as con:
        return list(con.execute(
            "SELECT 업체명, COUNT(*), SUM(수량) FROM repair_work_log WHERE 날짜 = ? GROUP BY 업체명 ORDER BY 업체명",
            (today,),
        ).fetchall())


def _sql_repair_ids_today():
    today = seoul_today_str()
    with get_connection() as con:
        return [int(r[0]) for r in con.execute(
            "SELECT id FROM repair_work_log WHERE 날짜 = ? ORDER BY id DESC",
            (today,),
        ).fetchall()]


def test_1_repair_mode_groups_today_vendors():
    uid, cid = _ids("1")
    set_mode(uid, cid, MODE_REPAIR)
    a = _insert_repair(업체명="로지킴", 수량=1)
    b = _insert_repair(업체명="틸리언", 수량=2)
    before = {_repair_row(a["id"])["cost"], _repair_row(b["id"])["cost"]}
    sent = _sent(uid, cid, "오늘 수선작업한 업체")
    groups = _sql_repair_vendor_groups()
    names = {row[0] for row in groups}
    assert "로지킴" in names and "틸리언" in names
    assert "로지킴" in sent and "틸리언" in sent
    assert "등록된 수선 작업 비용" not in sent
    assert "조회모드에서 확인할 수 있어요" not in sent
    assert get_mode(uid, cid) == MODE_REPAIR
    assert _repair_row(a["id"])["cost"] in before
    assert _repair_row(b["id"])["cost"] in before


def test_2_repair_mode_lists_numbered_records():
    uid, cid = _ids("2")
    set_mode(uid, cid, MODE_REPAIR)
    first = _insert_repair(업체명="로지킴", 비용=700)
    second = _insert_repair(업체명="틸리언", 비용=800)
    sent = _sent(uid, cid, "오늘 수선일지 보여줘")
    expected_ids = _sql_repair_ids_today()
    listed = _listed_ids(uid, cid)
    assert listed == expected_ids[: len(listed)]
    assert str(first["id"]) in sent and str(second["id"]) in sent
    assert "1." in sent and "2." in sent
    assert "등록된 수선 작업 비용" not in sent
    assert get_mode(uid, cid) == MODE_REPAIR


def test_3_repair_mode_updates_second_listed_id_only():
    uid, cid = _ids("3")
    set_mode(uid, cid, MODE_REPAIR)
    first = _insert_repair(업체명="로지킴", 비용=700, 수량=1)
    second = _insert_repair(업체명="틸리언", 비용=800, 수량=1)
    list_reply = _sent(uid, cid, "오늘 수선일지 보여줘")
    listed = _listed_ids(uid, cid)
    assert len(listed) >= 2
    target_id = listed[1]
    other_id = listed[0]
    before_target = _repair_row(target_id)
    before_other = _repair_row(other_id)
    preview = _sent(uid, cid, "두 번째 거 금액 2천원으로 바꿔")
    after_preview_target = _repair_row(target_id)
    assert after_preview_target["cost"] == before_target["cost"]
    assert str(target_id) in preview
    assert "변경 전" in preview and "변경 후" in preview
    assert "2,000" in preview or "2000" in preview
    confirm = _sent(uid, cid, "네")
    after_target = _repair_row(target_id)
    after_other = _repair_row(other_id)
    print("s3 ids", {"listed": listed, "target": target_id, "first": first["id"], "second": second["id"]})
    print("s3 db", {"before": before_target, "after": after_target, "other_before": before_other, "other_after": after_other})
    print("s3 list", list_reply)
    assert after_target["cost"] == 2000
    assert after_other["cost"] == before_other["cost"]
    assert after_target["id"] == target_id
    assert str(target_id) in confirm
    assert after_other["id"] != target_id or after_other["cost"] != 2000 or before_other["id"] == target_id


def test_4_repair_mode_partial_wash_price():
    uid, cid = _ids("4")
    set_mode(uid, cid, MODE_REPAIR)
    mgr = get_conversation_manager()
    sent = _sent(uid, cid, "부분세탁 얼마야")
    state = mgr.get_state(uid, cid) or {}
    pending = state.get("pending_data") or {}
    assert "부분세탁" in sent
    assert "700" in sent
    assert "전체세탁" not in sent
    assert "사진 2장" not in sent
    assert pending.get("entry_type") != "repair" or not pending.get("work_type")
    assert get_mode(uid, cid) == MODE_REPAIR


def test_5_journal_mode_lists_today_tilian():
    uid, cid = _ids("5")
    set_mode(uid, cid, MODE_JOURNAL)
    keep = _insert_work(uid, 업체명="틸리언", 분류="하차", 수량=2)
    other = _insert_work(uid, 업체명="팔로우미코스메틱", 분류="입고", 수량=9)
    extra = _insert_work(uid, 업체명="틸리언", 분류="상차", 수량=3)
    sent = _sent(uid, cid, "오늘 틸리언 작업일지 보여줘")
    listed = _listed_ids(uid, cid)
    with get_connection() as con:
        sql_ids = [int(r[0]) for r in con.execute(
            "SELECT id FROM work_log WHERE 날짜 = ? AND 업체명 = ? ORDER BY id DESC",
            (seoul_today_str(), "틸리언"),
        ).fetchall()]
    assert listed == sql_ids[: len(listed)]
    assert keep in listed and extra in listed
    assert other not in listed
    assert "틸리언" in sent
    assert "팔로우미" not in sent
    assert "1." in sent
    assert get_mode(uid, cid) == MODE_JOURNAL


def test_6_journal_mode_updates_first_listed_qty_only():
    uid, cid = _ids("6")
    set_mode(uid, cid, MODE_JOURNAL)
    older = _insert_work(uid, 업체명="틸리언", 분류="하차", 수량=2, 단가=30000)
    newer = _insert_work(uid, 업체명="틸리언", 분류="상차", 수량=3, 단가=30000)
    list_reply = _sent(uid, cid, "오늘 틸리언 작업일지 보여줘")
    listed = _listed_ids(uid, cid)
    assert listed[0] == newer
    target_id = listed[0]
    other_id = listed[1]
    before_target = _work_row(target_id)
    before_other = _work_row(other_id)
    preview = _sent(uid, cid, "첫 번째 거 수량 5건으로 바꿔")
    assert _work_row(target_id)["qty"] == before_target["qty"]
    assert str(target_id) in preview
    assert "변경 전" in preview and "변경 후" in preview
    confirm = _sent(uid, cid, "네")
    after_target = _work_row(target_id)
    after_other = _work_row(other_id)
    print("s6", {"listed": listed, "target": target_id, "older": older, "newer": newer})
    print("s6 db", {"before": before_target, "after": after_target, "other": after_other})
    print("s6 list", list_reply)
    assert after_target["qty"] == 5
    assert after_other["qty"] == before_other["qty"]
    assert after_target["price"] == before_target["price"]
    assert str(target_id) in confirm


def test_7_query_mode_rejects_same_update():
    uid, cid = _ids("7")
    set_mode(uid, cid, MODE_QUERY)
    _insert_repair(업체명="로지킴", 비용=700)
    _insert_repair(업체명="틸리언", 비용=800)
    _sent(uid, cid, "오늘 수선일지 보여줘")
    listed = _listed_ids(uid, cid)
    target_id = listed[1]
    before = {rid: _repair_row(rid) for rid in listed}
    preview = _sent(uid, cid, "두 번째 거 금액 2천원으로 바꿔")
    mid = {rid: _repair_row(rid) for rid in listed}
    confirm = _sent(uid, cid, "네")
    after = {rid: _repair_row(rid) for rid in listed}
    print("s7 replies", preview, confirm)
    print("s7 db", {"before": before, "after": after})
    assert mid == before
    assert after == before
    assert after[target_id]["cost"] == 700 or after[target_id]["cost"] == before[target_id]["cost"]
    assert "일지모드" in preview or "수선모드" in preview
    assert "조회모드" in preview
    assert get_mode(uid, cid) == MODE_QUERY


def test_8_draft_survives_same_domain_query():
    uid, cid = _ids("8")
    set_mode(uid, cid, MODE_REPAIR)
    saved = _insert_repair(업체명="로지킴", 비용=700)
    saved_before = _repair_row(saved["id"])
    mgr = get_conversation_manager()
    mgr.set_state(uid, cid, {"entry_type": "repair", "vendor": "기존초안", "qty": 1}, ["photos"], "사진?")
    sent = _sent(uid, cid, "오늘 수선작업한 업체")
    state = mgr.get_state(uid, cid) or {}
    draft = state.get("pending_data") or {}
    listed = _listed_ids(uid, cid)
    print("s8 reply", sent)
    print("s8 draft", draft)
    print("s8 listed", listed, "saved", saved["id"], saved_before)
    assert draft.get("vendor") == "기존초안"
    assert draft.get("qty") == 1
    assert (state.get("missing") or ["photos"])[0] == "photos" or "photos" in (state.get("missing") or [])
    assert "로지킴" in sent
    assert "조회모드에서 확인할 수 있어요" not in sent
    assert _repair_row(saved["id"]) == saved_before
    assert get_mode(uid, cid) == MODE_REPAIR
    assert saved["id"] not in (draft.get("id"), draft.get("repair_record_id"))
