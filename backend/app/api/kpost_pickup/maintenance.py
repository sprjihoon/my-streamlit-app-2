"""Admin debug and secret-gated maintenance endpoints."""
from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

from backend.app.services.epost.client import get_res_info_with_dates, lookup_req_ymds
from backend.app.services.epost.fields import TREAT_STATUS_ORDER, treat_status_code
from logic.db import get_connection

from .common import _get_user, ensure_pickup_tables
from .router import router


@router.get("/debug-track/{regi_no}")
def debug_track(regi_no: str, token: str):
    """특정 송장번호의 종적조회 결과 + DB 상태를 반환 (관리자 전용 디버그)."""
    user = _get_user(token)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다.")
    from backend.app.services.epost.client import (
        _track_via_epost_trace,
        _track_via_tracker_delivery,
        _track_via_vercel_relay,
        VERCEL_APP_URL,
        EPOST_RELAY_SECRET,
    )
    results: dict[str, Any] = {}

    # 1) DB에서 해당 송장번호 레코드 조회
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, order_no, tracking_no, treat_status, treat_status_name, status, res_date, created_at, pickup_date FROM kpost_pickup_requests WHERE tracking_no=? ORDER BY id DESC LIMIT 1",
            (regi_no,),
        ).fetchone()
    if row:
        cols = ["id","order_no","tracking_no","treat_status","treat_status_name","status","res_date","created_at","pickup_date"]
        results["db_record"] = dict(zip(cols, row))
        order_no = row[1]
        # 2) GetResInfo (계약 API) 테스트
        if order_no:
            ymds = lookup_req_ymds(row[6], row[7], row[8])
            try:
                info = get_res_info_with_dates(order_no, ymds)
                results["get_res_info"] = info
            except Exception as e:
                results["get_res_info_error"] = str(e)
    else:
        results["db_record"] = f"송장번호 {regi_no} 없음"

    # 3) tracker.delivery (외부 GraphQL API) 테스트
    try:
        r = _track_via_tracker_delivery(regi_no)
        results["tracker_delivery"] = r or "None (자격증명 없음 또는 매핑 실패)"
    except Exception as e:
        results["tracker_delivery_error"] = str(e)

    # 3-B) Vercel ICN 릴레이 테스트
    results["vercel_relay_config"] = {
        "VERCEL_APP_URL": VERCEL_APP_URL or "(미설정)",
        "EPOST_RELAY_SECRET": "설정됨" if EPOST_RELAY_SECRET else "(미설정)",
    }
    try:
        rv = _track_via_vercel_relay(regi_no)
        results["vercel_relay"] = rv or "None (릴레이 응답 없음 또는 텍스트 매핑 실패)"
    except Exception as e:
        results["vercel_relay_error"] = str(e)

    # 4) epost HTML 스크래핑 (service.epost.go.kr - Railway에서 차단될 수 있음)
    try:
        r2 = _track_via_epost_trace(regi_no)
        results["epost_trace"] = r2 or "None (텍스트 매핑 실패)"
    except Exception as e:
        results["epost_trace_error"] = str(e)

    # 5) ntrack.epost.go.kr (신형 서버) 접근 가능성 테스트
    try:
        import httpx as _httpx
        nr = _httpx.get(
            "https://ntrack.epost.go.kr/trace/traceDelivery.comm",
            params={"barCode": regi_no, "displayHeader": "N"},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"},
            follow_redirects=True,
        )
        results["ntrack_status"] = nr.status_code
        if nr.status_code < 400:
            raw_n = nr.content
            try:
                html_n = raw_n.decode("euc-kr")
            except Exception:
                html_n = raw_n.decode("utf-8", errors="replace")
            from backend.app.services.epost.fields import treat_status_from_tracking_text
            treat_n = treat_status_from_tracking_text(html_n)
            results["ntrack_treat"] = treat_n
            results["ntrack_sample"] = html_n[:300]
        else:
            results["ntrack_sample"] = f"HTTP {nr.status_code}"
    except Exception as e:
        results["ntrack_error"] = str(e)

    return results


@router.get("/maintenance/inspect")
def maintenance_inspect(secret: str, tracking_no: str):
    """유지보수 전용: 특정 송장의 DB 레코드 + insert_snapshot 조회."""
    relay_secret = os.getenv("EPOST_RELAY_SECRET", "").strip()
    if not relay_secret or secret != relay_secret:
        raise HTTPException(status_code=403, detail="인증 실패")
    ensure_pickup_tables()
    with get_connection() as con:
        row = con.execute(
            """SELECT id, order_no, tracking_no, treat_status, treat_status_name,
                      box_size, box_quantity, status, created_at, recipient_name,
                      insert_snapshot
               FROM kpost_pickup_requests
               WHERE tracking_no=? ORDER BY id DESC LIMIT 1""",
            (tracking_no,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="해당 송장 없음")
    cols = ["id","order_no","tracking_no","treat_status","treat_status_name",
            "box_size","box_quantity","status","created_at","recipient_name","insert_snapshot"]
    d = dict(zip(cols, row))
    snap = {}
    if d.get("insert_snapshot"):
        import json as _json
        try:
            snap = _json.loads(d["insert_snapshot"])
        except Exception:
            snap = {"raw": d["insert_snapshot"]}
    return {
        "db": {k: v for k, v in d.items() if k != "insert_snapshot"},
        "insert_snapshot": snap,
    }


@router.post("/maintenance/reset-status")
def maintenance_reset_status(secret: str, body: dict):
    """유지보수 전용: EPOST_RELAY_SECRET 인증으로 특정 송장 상태를 직접 수정.

    body: {"tracking_nos": ["...", ...], "treat_status": "수거준비"} (또는 숫자코드 "05"도 허용)
    secret: EPOST_RELAY_SECRET 값
    """
    relay_secret = os.getenv("EPOST_RELAY_SECRET", "").strip()
    if not relay_secret or secret != relay_secret:
        raise HTTPException(status_code=403, detail="인증 실패: secret이 올바르지 않습니다.")

    tracking_nos: list[str] = body.get("tracking_nos") or []
    raw_status: str = (body.get("treat_status") or "").strip()
    if not tracking_nos:
        raise HTTPException(status_code=400, detail="tracking_nos가 비어 있습니다.")
    # 숫자코드('05') 또는 Korean text('수거준비') 모두 허용
    new_name = treat_status_code(raw_status)
    if new_name not in TREAT_STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태. 허용: {list(TREAT_STATUS_ORDER.keys())}")

    ensure_pickup_tables()
    updated = []
    not_found = []
    with get_connection() as con:
        for tno in tracking_nos:
            row = con.execute(
                "SELECT id, treat_status FROM kpost_pickup_requests WHERE tracking_no=? ORDER BY id DESC LIMIT 1",
                (tno,),
            ).fetchone()
            if not row:
                not_found.append(tno)
                continue
            con.execute(
                "UPDATE kpost_pickup_requests SET treat_status=?, treat_status_name=? WHERE id=?",
                (new_name, new_name, row[0]),
            )
            updated.append({"id": row[0], "tracking_no": tno, "prev": row[1], "now": new_name})
        con.commit()
    return {
        "success": True,
        "updated": updated,
        "not_found": not_found,
        "treat_status": new_name,
        "treat_status_name": new_name,
    }
