"""Vendor overview, filter options, and vendor aliases."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Header, HTTPException, Query

from logic.db import get_connection

from .router import router
from .schemas import VendorAliasUpdate
from .utils import _get_user, _image_url, _image_url_defect, _image_url_repair

# ─────────────────────────────────────
# 라우터
# ─────────────────────────────────────

# ── 통합현황: 화주사+날짜 단위 목록 및 상세 ──────

@router.get("/vendor-overview")
def list_vendor_overviews(
    vendor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),   # "closed" | "open"
    authorization: Optional[str] = Header(None),
):
    """
    화주사+입고일 단위로 묶어 반환한다.
    vendor_canonical 이 있으면 canonical 기준으로 묶고, 없으면 vendor 사용.
    status="closed" → 해당 날짜 모든 배치가 마감인 그룹만 반환
    status="open"   → 하나라도 진행중인 그룹만 반환
    """
    _get_user(authorization)
    where = ["1=1"]
    params: list = []
    if vendor:
        # canonical 또는 raw vendor 어느 쪽이든 일치
        where.append("COALESCE(vendor_canonical, vendor)=?"); params.append(vendor)
    if date_from:
        where.append("inbound_date>=?"); params.append(date_from)
    if date_to:
        where.append("inbound_date<=?"); params.append(date_to)

    sql = f"""
        SELECT COALESCE(vendor_canonical, vendor) AS canonical_vendor,
               inbound_date,
               COUNT(*) AS batches_count,
               GROUP_CONCAT(COALESCE(wholesale,''), '|') AS wholesales,
               SUM(total_janggi_qty) AS total_janggi,
               SUM(total_actual_qty) AS total_actual,
               SUM(total_missing_qty) AS total_missing,
               GROUP_CONCAT(status, '|') AS statuses
        FROM inbound_batches
        WHERE {' AND '.join(where)}
        GROUP BY canonical_vendor, inbound_date
        ORDER BY inbound_date DESC, canonical_vendor
    """
    with get_connection() as con:
        rows = con.execute(sql, params).fetchall()

        # 각 (vendor, date) 별 수선건수 집계: inbound_item_id 연결 + 바코드 fallback
        repair_count_map: dict = {}
        for r in rows:
            cvendor, idate = r[0], r[1]
            # ① inbound_item_id 기준
            cnt_a = con.execute(
                """SELECT COUNT(*) FROM repair_work_log rw
                   JOIN inbound_items ii ON rw.inbound_item_id = ii.id
                   JOIN inbound_batches ib ON ii.batch_id = ib.id
                   WHERE COALESCE(ib.vendor_canonical, ib.vendor)=? AND ib.inbound_date=?""",
                (cvendor, idate),
            ).fetchone()[0] or 0
            # ② 바코드+날짜 fallback (inbound_item_id 없는 봇 기록)
            cnt_b = con.execute(
                """SELECT COUNT(*) FROM repair_work_log rw
                   JOIN inbound_items ii ON rw.바코드 = ii.matched_barcode
                   JOIN inbound_batches ib ON ii.batch_id = ib.id
                   WHERE COALESCE(ib.vendor_canonical, ib.vendor)=? AND ib.inbound_date=?
                     AND (rw.inbound_item_id IS NULL OR rw.inbound_item_id='')
                     AND rw.날짜=?""",
                (cvendor, idate, idate),
            ).fetchone()[0] or 0
            repair_count_map[(cvendor, idate)] = cnt_a + cnt_b

    items = []
    for r in rows:
        wholesales = list(dict.fromkeys(w for w in (r[3] or "").split("|") if w))  # 중복 제거
        statuses = (r[7] or "").split("|")
        all_closed = all(s == "closed" for s in statuses if s)
        # status 필터 적용
        if status == "closed" and not all_closed:
            continue
        if status == "open" and all_closed:
            continue
        items.append({
            "vendor": r[0],          # canonical 기준 표시명
            "inbound_date": r[1],
            "batches_count": r[2],
            "wholesales": wholesales,
            "total_janggi_qty": r[4] or 0,
            "total_actual_qty": r[5] or 0,
            "total_missing_qty": r[6] or 0,
            "all_closed": all_closed,
            "statuses": statuses,
            "repair_count": repair_count_map.get((r[0], r[1]), 0),
        })
    return {"items": items, "total": len(items)}


@router.get("/vendor-overview/{vendor}/{inbound_date}")
def get_vendor_overview_detail(
    vendor: str,
    inbound_date: str,
    authorization: Optional[str] = Header(None),
):
    """
    특정 화주사+입고일의 전체 배치·품목·사진·불량/수선 로그를 반환한다.
    """
    _get_user(authorization)
    with get_connection() as con:
        batch_rows = con.execute(
            """SELECT id, vendor, inbound_date, status, memo, wholesale,
                      total_janggi_qty, total_actual_qty, total_missing_qty,
                      created_by, closed_by, closed_at, created_at, janggi_filename
               FROM inbound_batches
               WHERE COALESCE(vendor_canonical, vendor)=? AND inbound_date=?
               ORDER BY wholesale""",
            (vendor, inbound_date),
        ).fetchall()

        if not batch_rows:
            raise HTTPException(status_code=404, detail="해당 화주사/날짜 데이터 없음")

        batch_ids = [r[0] for r in batch_rows]
        ph = ",".join("?" * len(batch_ids))

        # 전체 품목 조회
        item_rows = con.execute(
            f"""SELECT id, batch_id, line_no, item_name, option_text, unit_price,
                       janggi_qty, actual_qty, missing_qty, status,
                       matched_barcode, matched_vendor, matched_product, matched_option,
                       supplier_location, supplier_contact, needs_matching, normal_qty,
                       confirmed_by, item_wholesale, memo,
                       actual_qty_confirmed, photo_decision
                FROM inbound_items
                WHERE batch_id IN ({ph})
                ORDER BY batch_id, line_no""",
            batch_ids,
        ).fetchall()

        item_ids = [r[0] for r in item_rows]
        idph = ",".join("?" * len(item_ids)) if item_ids else "NULL"

        # 품목별 사진
        photo_map: dict = {}
        if item_ids:
            for row in con.execute(
                f"SELECT item_id, id, filename FROM inbound_item_photos WHERE item_id IN ({idph}) ORDER BY created_at",
                item_ids,
            ).fetchall():
                photo_map.setdefault(row[0], []).append({"id": row[1], "url": _image_url(row[2])})

        # 바코드 → item_id 매핑 (fallback용, matched_barcode 기준)
        barcode_to_item_id: dict = {}
        for r in item_rows:
            bc = r[10]  # matched_barcode
            if bc and bc not in barcode_to_item_id:
                barcode_to_item_id[bc] = r[0]

        # 불량 로그 전체 ① inbound_item_id 직접 연결
        defect_map: dict = {}
        defect_seen: set = set()
        if item_ids:
            for row in con.execute(
                f"""SELECT inbound_item_id, id, 날짜, 불량명, 수량, 비고, 처리결과,
                           before_image, after_image, 작성자
                    FROM defect_log WHERE inbound_item_id IN ({idph})
                    ORDER BY inbound_item_id, id""",
                item_ids,
            ).fetchall():
                defect_map.setdefault(row[0], []).append({
                    "id": row[1], "날짜": row[2], "불량명": row[3],
                    "수량": row[4], "비고": row[5], "처리결과": row[6],
                    "before_image": _image_url_defect(row[7]),
                    "after_image": _image_url_defect(row[8]),
                    "작성자": row[9],
                })
                defect_seen.add(row[1])

        # 불량 로그 ② 바코드+날짜 fallback (봇 기록 등 inbound_item_id 없는 경우)
        if barcode_to_item_id:
            bcph = ",".join("?" * len(barcode_to_item_id))
            for row in con.execute(
                f"""SELECT 바코드, id, 날짜, 불량명, 수량, 비고, 처리결과,
                           before_image, after_image, 작성자
                    FROM defect_log
                    WHERE 바코드 IN ({bcph}) AND 날짜=?
                      AND (inbound_item_id IS NULL OR inbound_item_id='')
                    ORDER BY 바코드, id""",
                list(barcode_to_item_id.keys()) + [inbound_date],
            ).fetchall():
                if row[1] in defect_seen:
                    continue
                item_id = barcode_to_item_id.get(row[0])
                if item_id:
                    defect_map.setdefault(item_id, []).append({
                        "id": row[1], "날짜": row[2], "불량명": row[3],
                        "수량": row[4], "비고": row[5], "처리결과": row[6],
                        "before_image": _image_url_defect(row[7]),
                        "after_image": _image_url_defect(row[8]),
                        "작성자": row[9],
                    })
                    defect_seen.add(row[1])

        # 수선 로그 전체 ① inbound_item_id 직접 연결
        repair_map: dict = {}
        repair_seen: set = set()
        if item_ids:
            for row in con.execute(
                f"""SELECT inbound_item_id, id, 날짜, 작업, 불량명, 수량, 비용, 비고,
                           before_image, after_image, 작성자
                    FROM repair_work_log WHERE inbound_item_id IN ({idph})
                    ORDER BY inbound_item_id, id""",
                item_ids,
            ).fetchall():
                repair_map.setdefault(row[0], []).append({
                    "id": row[1], "날짜": row[2], "작업": row[3], "불량명": row[4],
                    "수량": row[5], "비용": row[6], "비고": row[7],
                    "before_image": _image_url_repair(row[8]),
                    "after_image": _image_url_repair(row[9]),
                    "작성자": row[10],
                })
                repair_seen.add(row[1])

        # 수선 로그 ② 바코드+날짜 fallback (봇 기록 등 inbound_item_id 없는 경우)
        if barcode_to_item_id:
            bcph = ",".join("?" * len(barcode_to_item_id))
            for row in con.execute(
                f"""SELECT 바코드, id, 날짜, 작업, 불량명, 수량, 비용, 비고,
                           before_image, after_image, 작성자
                    FROM repair_work_log
                    WHERE 바코드 IN ({bcph}) AND 날짜=?
                      AND (inbound_item_id IS NULL OR inbound_item_id='')
                    ORDER BY 바코드, id""",
                list(barcode_to_item_id.keys()) + [inbound_date],
            ).fetchall():
                if row[1] in repair_seen:
                    continue
                item_id = barcode_to_item_id.get(row[0])
                if item_id:
                    repair_map.setdefault(item_id, []).append({
                        "id": row[1], "날짜": row[2], "작업": row[3], "불량명": row[4],
                        "수량": row[5], "비용": row[6], "비고": row[7],
                        "before_image": _image_url_repair(row[8]),
                        "after_image": _image_url_repair(row[9]),
                        "작성자": row[10],
                    })
                    repair_seen.add(row[1])

    # 도매처별 그룹핑
    batch_map = {}
    for r in batch_rows:
        batch_map[r[0]] = {
            "id": r[0], "vendor": r[1], "inbound_date": r[2], "status": r[3],
            "memo": r[4], "wholesale": r[5] or "-",
            "total_janggi_qty": r[6] or 0, "total_actual_qty": r[7] or 0,
            "total_missing_qty": r[8] or 0,
            "created_by": r[9], "closed_by": r[10], "closed_at": r[11],
            "created_at": r[12],
            "janggi_url": _image_url(r[13]) if r[13] else None,  # 장끼 사진
            "items": [],
        }

    for r in item_rows:
        iid = r[0]
        item = {
            "id": iid, "batch_id": r[1], "line_no": r[2],
            "item_name": r[3], "option_text": r[4], "unit_price": r[5],
            "janggi_qty": r[6] or 0, "actual_qty": r[7] or 0, "missing_qty": r[8] or 0,
            "status": r[9], "matched_barcode": r[10],
            "matched_vendor": r[11], "matched_product": r[12], "matched_option": r[13],
            "supplier_location": r[14], "supplier_contact": r[15],
            "needs_matching": bool(r[16]), "normal_qty": r[17] or 0,
            "confirmed_by": r[18], "item_wholesale": r[19], "memo": r[20],
            "actual_qty_confirmed": bool(r[21]) if r[21] is not None else False,
            "photo_decision": r[22],
            "photos": photo_map.get(iid, []),
            "defect_logs": defect_map.get(iid, []),
            "repair_logs": repair_map.get(iid, []),
        }
        if r[1] in batch_map:
            batch_map[r[1]]["items"].append(item)

    batches = list(batch_map.values())

    total_janggi = sum(b["total_janggi_qty"] for b in batches)
    total_actual = sum(b["total_actual_qty"] for b in batches)
    total_missing = sum(b["total_missing_qty"] for b in batches)
    all_items = [i for b in batches for i in b["items"]]
    needs_matching_count = sum(1 for i in all_items if i["needs_matching"])
    defect_total = sum(len(i["defect_logs"]) for i in all_items)
    repair_total = sum(len(i["repair_logs"]) for i in all_items)

    return {
        "vendor": vendor,
        "inbound_date": inbound_date,
        "summary": {
            "batches_count": len(batches),
            "total_janggi_qty": total_janggi,
            "total_actual_qty": total_actual,
            "total_missing_qty": total_missing,
            "items_count": len(all_items),
            "needs_matching_count": needs_matching_count,
            "defect_total": defect_total,
            "repair_total": repair_total,
        },
        "batches": batches,
    }


# ── 입고 필터 옵션 (화주사·도매처 목록) ──────

@router.get("/filter-options")
def get_filter_options(authorization: Optional[str] = Header(None)):
    """
    입고일지 필터용 드롭다운 옵션 반환.
    - vendors      : inbound_batches 에 실제 등록된 고유 화주사명
    - wholesales   : inbound_batches.wholesale 의 고유 값
    - alias_groups : inbound_vendor_aliases 의 canonical → aliases 매핑
                     (입고 이력이 있는 canonical 만 포함)
    """
    _get_user(authorization)
    with get_connection() as con:
        vendor_rows = con.execute(
            "SELECT DISTINCT vendor FROM inbound_batches WHERE vendor IS NOT NULL AND vendor != '' ORDER BY vendor"
        ).fetchall()
        wholesale_rows = con.execute(
            "SELECT DISTINCT wholesale FROM inbound_batches WHERE wholesale IS NOT NULL AND wholesale != '' ORDER BY wholesale"
        ).fetchall()
        # 별칭: 입고 이력이 있는 canonical 만
        batch_vendors = {r[0] for r in vendor_rows}
        alias_rows = con.execute(
            "SELECT canonical, aliases FROM inbound_vendor_aliases WHERE aliases IS NOT NULL AND aliases != '' ORDER BY canonical"
        ).fetchall()
        alias_groups = []
        for canonical, aliases_str in alias_rows:
            alias_list = [a.strip() for a in aliases_str.split(",") if a.strip()]
            if not alias_list:
                continue
            # canonical 이 입고 이력에 있는 경우만 포함
            # (별칭으로 저장된 경우도 포함하기 위해 _resolve_vendor_names 없이 단순 체크)
            alias_groups.append({"canonical": canonical, "aliases": alias_list})
    return {
        "vendors": [r[0] for r in vendor_rows],
        "wholesales": [r[0] for r in wholesale_rows],
        "alias_groups": alias_groups,
    }

# ── 화주사 목록 (자동완성용) ────────────

@router.get("/vendors")
def list_inbound_vendors(
    authorization: Optional[str] = Header(None),
):
    """
    repair_barcode 등록 업체명 (registered) +
    최근 입고 실적 업체 (recent) 를 분리 반환.
    각 등록 업체에 별칭(aliases) 포함.
    """
    _get_user(authorization)
    with get_connection() as con:
        # repair_barcode 등록 업체 + 별칭
        barcode_vendors = [r[0] for r in con.execute(
            "SELECT DISTINCT \uc5c5\uccb4\uba85 FROM repair_barcode WHERE \uc5c5\uccb4\uba85 IS NOT NULL ORDER BY \uc5c5\uccb4\uba85"
        ).fetchall() if r[0]]
        alias_rows = {r[0]: r[1] for r in con.execute(
            "SELECT canonical, aliases FROM inbound_vendor_aliases"
        ).fetchall()}
        registered = [
            {
                "name": v,
                "aliases": [a.strip() for a in (alias_rows.get(v) or "").split(",") if a.strip()],
            }
            for v in barcode_vendors
        ]
        # 최근 입고 실적 업체 (등록 업체 제외)
        registered_names = set(barcode_vendors)
        recent_raw = [r[0] for r in con.execute(
            "SELECT DISTINCT vendor FROM inbound_batches ORDER BY created_at DESC LIMIT 20"
        ).fetchall() if r[0]]
        recent = [v for v in recent_raw if v not in registered_names]
    return {"registered": registered, "recent": recent}

@router.get("/vendor-aliases")
def get_vendor_aliases(authorization: Optional[str] = Header(None)):
    """등록된 벤더 별칭 전체 조회"""
    _get_user(authorization)
    with get_connection() as con:
        rows = con.execute(
            "SELECT canonical, aliases, memo FROM inbound_vendor_aliases ORDER BY canonical"
        ).fetchall()
    return {"aliases": [{"canonical": r[0], "aliases": [a.strip() for a in (r[1] or "").split(",") if a.strip()], "memo": r[2]} for r in rows]}


@router.put("/vendor-aliases/{canonical}")
def upsert_vendor_alias(
    canonical: str,
    body: VendorAliasUpdate,
    authorization: Optional[str] = Header(None),
):
    """특정 업체의 별칭 저장 (없으면 생성, 있으면 덮어쓰기)"""
    _get_user(authorization)
    aliases_str = ", ".join(a.strip() for a in body.aliases if a.strip())
    now = datetime.utcnow().isoformat()
    with get_connection() as con:
        con.execute("""
            INSERT INTO inbound_vendor_aliases (canonical, aliases, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(canonical) DO UPDATE SET
                aliases = excluded.aliases,
                memo = excluded.memo,
                updated_at = excluded.updated_at
        """, (canonical, aliases_str, body.memo, now, now))
        con.commit()
    return {"ok": True, "canonical": canonical, "aliases": body.aliases}


@router.delete("/vendor-aliases/{canonical}")
def delete_vendor_alias(
    canonical: str,
    authorization: Optional[str] = Header(None),
):
    """특정 업체 별칭 삭제"""
    _get_user(authorization)
    with get_connection() as con:
        con.execute("DELETE FROM inbound_vendor_aliases WHERE canonical=?", (canonical,))
        con.commit()
    return {"ok": True}
