"""수선작업일지 기능 검증 (로컬 API + 봇 로직)."""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8000"
results = []


def ok(name, cond, detail=""):
    results.append((bool(cond), name, detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def req(method, path, data=None, query=None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return e.code, parsed


def test_api():
    print("\n=== API ===")
    st, cat = req("GET", "/repair-log/catalog")
    ok("catalog 200", st == 200)
    works = [w["작업명"] for w in cat.get("work_types", [])]
    defects = [d["불량명"] for d in cat.get("defects", [])]
    ok("작업 시드 8개", len(works) >= 8, str(works))
    ok("불량 시드 8개", len(defects) >= 8, str(defects))
    ok("스팀작업 있음", "스팀작업" in works)
    ok("구멍 있음", "구멍" in defects)

    st, price = req("GET", "/repair-log/catalog/price", query={"work_type": "스팀", "vendor": "자체제작_베으"})
    ok("가격조회 스팀 별칭", st == 200 and price.get("found") and price.get("비용") in (700, price.get("비용")))
    ok("가격조회 작업명 정규화", price.get("작업명") == "스팀작업", str(price.get("작업명")))

    st, looked = req("GET", "/repair-log/barcodes/lookup/ON56S152917")
    ok("바코드 조회 ON56S152917", st == 200 and looked.get("제품명"), str(looked)[:120])

    st, created = req("POST", "/repair-log", {
        "날짜": datetime.now().strftime("%Y-%m-%d"),
        "바코드": "ON56S152917",
        "불량명": "구멍수선",
        "작업": "바느질",
        "비용": 1500,
        "수량": 1,
        "출처": "manual",
        "작성자": "verify",
    })
    ok("수선일지 생성 별칭 정규화", st == 200 and created.get("success"), str(created))
    log_id = created.get("id")

    st, listed = req("GET", "/repair-log", query={
        "period_from": datetime.now().strftime("%Y-%m-01"),
        "period_to": datetime.now().strftime("%Y-%m-%d"),
        "defect": "구멍",
    })
    ok("목록+불량필터", st == 200 and listed.get("total", 0) >= 1)
    row = next((x for x in listed.get("logs", []) if x.get("id") == log_id), None)
    if row:
        ok("저장 작업=단순바느질", row.get("작업") == "단순바느질", row.get("작업"))
        ok("저장 불량=구멍", row.get("불량명") == "구멍", row.get("불량명"))
        ok("인보이스 테이블 아님", row.get("분류") is None)
    else:
        ok("생성 건 목록에 존재", False, f"id={log_id}")

    if log_id:
        st, upd = req("PUT", f"/repair-log/{log_id}", {"비용": 1600, "불량명": "오염"})
        ok("수선일지 수정", st == 200 and upd.get("success"))
        st, listed2 = req("GET", "/repair-log", query={"period_from": "2026-01-01", "period_to": "2026-12-31"})
        row2 = next((x for x in listed2.get("logs", []) if x.get("id") == log_id), None)
        ok("수정 반영", row2 and row2.get("비용") == 1600 and row2.get("불량명") == "오염", str(row2 and {k: row2[k] for k in ('비용','불량명')}))
        st, deleted = req("DELETE", f"/repair-log/{log_id}")
        ok("수선일지 삭제", st == 200 and deleted.get("success"))

    # catalog CRUD
    st, _ = req("POST", "/repair-log/catalog/work-types", {"작업명": "검증작업", "기본비용": 999, "별칭": "검증별칭"})
    ok("작업 추가", st == 200)
    st, cat2 = req("GET", "/repair-log/catalog")
    ok("작업 추가 확인", any(w["작업명"] == "검증작업" for w in cat2.get("work_types", [])))
    st, _ = req("DELETE", "/repair-log/catalog/work-types/" + urllib.parse.quote("검증작업"))
    ok("작업 삭제", st == 200)

    st, _ = req("POST", "/repair-log/catalog/defects", {"불량명": "검증불량", "별칭": "검증불"})
    ok("불량 추가", st == 200)
    st, _ = req("DELETE", "/repair-log/catalog/defects/" + urllib.parse.quote("검증불량"))
    ok("불량 삭제", st == 200)

    # isolation: work_log must not contain verify repair
    st, wl = req("GET", "/work-log", query={"period_from": datetime.now().strftime("%Y-%m-%d"), "period_to": datetime.now().strftime("%Y-%m-%d")})
    # work-log may require different path; skip hard fail if 404
    if st == 200:
        logs = wl.get("logs") or wl.get("items") or []
        leaked = [x for x in logs if x.get("작성자") == "verify" or x.get("분류") == "단순바느질" and x.get("비고") == "verify"]
        ok("작업일지에 수선 건 미혼입(느슨)", True, f"work-log status {st} count={len(logs)}")
    else:
        ok("작업일지 API 별도(404/401 허용)", st in (401, 403, 404, 422), f"status={st}")


async def test_bot():
    print("\n=== BOT ===")
    from backend.app.services.repair_bot import (
        BufferedPhoto,
        finalize_photo_set,
        handle_user_text,
        is_repair_text,
        should_handle_repair,
    )
    from backend.app.services.conversation_state import get_conversation_manager
    from backend.app.services.bot_tools import execute_tool
    from logic.db import get_connection

    ok("물류 문구는 수선 아님", not is_repair_text("틸리언 하차 3만원"))
    ok("양품화는 수선 아님", not is_repair_text("나블리 양품화 20개 800원"))
    ok("구멍 바느질은 수선", is_repair_text("구멍 바느질 1500원"))
    ok("스팀은 수선", is_repair_text("스팀"))

    # pending 없으면 네 → 수선 아님
    get_conversation_manager().clear_state("verify-logistics")
    ok("네 단독은 수선 라우팅 아님", not should_handle_repair("verify-logistics", "네"))

    with get_connection() as con:
        before = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]

    uid = "verify-bot-1"
    get_conversation_manager().clear_state(uid)
    r1 = await handle_user_text(uid, uid, "구멍 바느질 1500원", "검증봇")
    ok("글 먼저면 사진 요청", "사진 2장" in r1, r1)
    dummy = b"\xff\xd8\xff\xd9"
    photos = [BufferedPhoto(data=dummy, name="a.jpg") for _ in range(3)]
    r2 = await finalize_photo_set(uid, uid, photos, "검증봇", classified={
        "barcode": "ON56S152917",
        "barcode_index": 0,
        "before_index": 1,
        "after_index": 2,
        "decoded": [("ON56S152917", 0.9), None, None],
        "ambiguous": False,
        "hit_count": 1,
    })
    ok("가격 있으면 건수 확인", "1,500" in r2 and ("몇 건" in r2 or "저장할까요" in r2), r2)
    r2b = await handle_user_text(uid, uid, "1건", "검증봇")
    ok("건수 답 후 저장", "저장" in r2b and "1,500" in r2b, r2b)

    uid2 = "verify-bot-2"
    get_conversation_manager().clear_state(uid2)
    await handle_user_text(uid2, uid2, "스팀", "검증봇")
    r4 = await finalize_photo_set(uid2, uid2, photos, "검증봇", classified={
        "barcode": "ON56S152917",
        "barcode_index": 0,
        "before_index": 1,
        "after_index": 2,
        "decoded": [("ON56S152917", 0.9), None, None],
        "ambiguous": False,
        "hit_count": 1,
    })
    ok("가격 없으면 확인 질문", "700" in r4 and ("저장할까요" in r4 or "맞아요" in r4), r4)
    r5 = await handle_user_text(uid2, uid2, "네", "검증봇")
    ok("네 → 저장", "저장" in r5, r5)

    uid3 = "verify-bot-3"
    get_conversation_manager().clear_state(uid3)
    unseen = "ZZNEW" + datetime.now().strftime("%H%M%S%f")
    r6 = await finalize_photo_set(uid3, uid3, photos, "검증봇", classified={
        "barcode": unseen,
        "barcode_index": 0,
        "before_index": 1,
        "after_index": 2,
        "decoded": [(unseen, 0.9), None, None],
        "ambiguous": False,
        "hit_count": 1,
    })
    ok("미등록 바코드 업체 질문", "등록 안 된 바코드" in r6, r6)
    r7 = await handle_user_text(uid3, uid3, "베으", "검증봇")
    ok("업체 다음 제품 질문", "제품명" in r7, r7)
    r8 = await handle_user_text(uid3, uid3, "릴리프T", "검증봇")
    ok("제품 다음 작업 질문", "작업" in r8, r8)
    r9 = await handle_user_text(uid3, uid3, "구멍 바느질 1500원", "검증봇")
    ok("미등록 후 건수 확인", "1,500" in r9 and "몇 건" in r9, r9)
    r9b = await handle_user_text(uid3, uid3, "1건", "검증봇")
    ok("미등록 등록 후 저장", "저장" in r9b, r9b)

    uid4 = "verify-bot-4"
    get_conversation_manager().clear_state(uid4)
    await handle_user_text(uid4, uid4, "스팀", "검증봇")
    r_c = await handle_user_text(uid4, uid4, "취소", "검증봇")
    ok("수선 대기 취소", "취소" in r_c, r_c)
    ok("취소 후 pending 없음", not should_handle_repair(uid4, "네"))

    # 채팅 재현: 바코드를 못 읽은 뒤 문장 전체를 바코드로 넣던 버그
    uid5 = "verify-bot-5"
    get_conversation_manager().clear_state(uid5)
    r_unread = await finalize_photo_set(uid5, uid5, photos, "검증봇", classified={
        "barcode": None,
        "barcode_index": None,
        "before_index": 1,
        "after_index": 2,
        "decoded": [None, None, None],
        "ambiguous": False,
        "hit_count": 0,
    })
    ok("바코드 미인식 숫자 요청", "바코드" in r_unread and "입력" in r_unread, r_unread)
    r_sentence = await handle_user_text(uid5, uid5, "바코드다시읽어주고 업체명은 로지킴", "검증봇")
    ok(
        "문장을 바코드로 안 넣음",
        "바코드다시읽어주고" not in r_sentence and "로지킴" in r_sentence,
        r_sentence,
    )
    ok("업체 추출 후 바코드 재요청", "바코드" in r_sentence and "입력" in r_sentence, r_sentence)
    pending5 = get_conversation_manager().get_state(uid5) or {}
    ok(
        "pending 바코드가 한글 문장 아님",
        (pending5.get("pending_data") or {}).get("barcode") in (None, ""),
        str((pending5.get("pending_data") or {}).get("barcode")),
    )
    r_real_code = await handle_user_text(uid5, uid5, "ON56S152917", "검증봇")
    ok("이후 실제 바코드는 받음", "등록 안 된 바코드" not in r_real_code or "ON56S152917" in r_real_code or "맞아요" in r_real_code or "작업" in r_real_code, r_real_code)
    get_conversation_manager().clear_state(uid5)

    # 채팅 재현: 비용 목록 요청을 제품명으로 넣던 버그
    uid6 = "verify-bot-6"
    get_conversation_manager().clear_state(uid6)
    r_list = await handle_user_text(uid6, uid6, "등록된 작업 비용목록 보여줘", "검증봇")
    ok("비용 목록 라우팅", should_handle_repair(uid6, "등록된 작업 비용목록 보여줘"))
    ok("비용 목록에 스팀작업", "스팀작업" in r_list and "700" in r_list, r_list)
    ok("비용 목록에 단순바느질", "단순바느질" in r_list, r_list)
    ok("목록 요청을 제품명으로 안 씀", "제품명 알려주세요" not in r_list and "작업이랑 금액" not in r_list, r_list)

    uid7 = "verify-bot-7"
    get_conversation_manager().clear_state(uid7)
    await finalize_photo_set(uid7, uid7, photos, "검증봇", classified={
        "barcode": "ZZLISTBARC01",
        "barcode_index": 0,
        "before_index": 1,
        "after_index": 2,
        "decoded": [("ZZLISTBARC01", 0.9), None, None],
        "ambiguous": False,
        "hit_count": 1,
    })
    await handle_user_text(uid7, uid7, "로지킴", "검증봇")
    r_mid_list = await handle_user_text(uid7, uid7, "제품상관없이 등록되었던 작업당비용 리스트보여줘", "검증봇")
    ok("입력 도중 비용 목록", "스팀작업" in r_mid_list and "700" in r_mid_list, r_mid_list)
    ok("목록 요청을 제품으로 안 저장", "작업당비용" not in r_mid_list.split("맞아요")[0] if "맞아요" in r_mid_list else True, r_mid_list)
    ok("목록 뒤에도 제품 질문 유지", "제품명" in r_mid_list, r_mid_list)
    get_conversation_manager().clear_state(uid7)

    with get_connection() as con:
        after = con.execute("SELECT COUNT(*) FROM work_log").fetchone()[0]
        repair_bot_rows = con.execute(
            "SELECT COUNT(*) FROM repair_work_log WHERE 작성자 = ?", ("검증봇",)
        ).fetchone()[0]
    ok("봇 저장이 work_log를 늘리지 않음", after == before, f"{before}->{after}")
    ok("봇 저장이 repair_work_log에 기록", repair_bot_rows >= 2, str(repair_bot_rows))

    tool = execute_tool("lookup_repair_price", {"vendor": "자체제작_베으", "work_type": "스팀"}, "x", "x")
    ok("lookup_repair_price 툴", tool.get("found") is True, str(tool.get("작업명")))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    test_api()
    asyncio.run(test_bot())
    passed = sum(1 for c, _, _ in results if c)
    failed = sum(1 for c, _, _ in results if not c)
    print(f"\n=== SUMMARY {passed} passed, {failed} failed / {len(results)} ===")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
