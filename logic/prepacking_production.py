"""
logic/prepacking_production.py - 제작 관리 & 일일 지시 & 정확도
───────────────────────────────────────────────────────────────
프리패킹 제작 CRUD, 일일 지시 생성, 정확도 비교, 효율 지표.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .db import get_connection, now_str
from .prepacking_analysis import analyze_combinations, predict_for_date
from .prepacking_settings import get_settings


# ── 예측 저장·조회 ──────────────────

def save_predictions(vendor: str, target_date: date, predictions: List[Dict]) -> int:
    dow = target_date.weekday()
    with get_connection() as con:
        con.execute(
            "DELETE FROM prepacking_predictions WHERE vendor=? AND target_date=?",
            (vendor, target_date.isoformat()),
        )
        for p in predictions:
            con.execute(
                """INSERT INTO prepacking_predictions
                   (vendor, target_date, day_of_week, combo_key, combo_detail, predicted_qty, ai_adjusted_qty, ai_reasoning, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    vendor, target_date.isoformat(), dow,
                    p["combo_key"], p.get("combo_detail", "[]"),
                    p["predicted_qty"], p.get("ai_adjusted_qty"), p.get("ai_reasoning"),
                    now_str(),
                ),
            )
        con.commit()
    return len(predictions)


def get_predictions(vendor: str, target_date: date) -> List[Dict]:
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, combo_key, combo_detail, predicted_qty, ai_adjusted_qty, ai_reasoning, actual_qty, mape
               FROM prepacking_predictions WHERE vendor=? AND target_date=?
               ORDER BY COALESCE(ai_adjusted_qty, predicted_qty) DESC""",
            (vendor, target_date.isoformat()),
        ).fetchall()
    return [
        {
            "id": r[0], "combo_key": r[1], "combo_detail": r[2],
            "predicted_qty": r[3], "ai_adjusted_qty": r[4], "ai_reasoning": r[5],
            "actual_qty": r[6], "mape": r[7],
        }
        for r in rows
    ]


# ── 제작 CRUD ───────────────────────

def create_production(
    vendor: str, target_date: date, combo_key: str, combo_detail: str,
    predicted_qty: int, produced_qty: int, location: str = "",
) -> int:
    ts = now_str()
    with get_connection() as con:
        cur = con.execute(
            """INSERT INTO prepacking_productions
               (vendor, target_date, combo_key, combo_detail, predicted_qty, produced_qty, remaining_qty, location, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (vendor, target_date.isoformat(), combo_key, combo_detail, predicted_qty, produced_qty, produced_qty, location, ts, ts),
        )
        prod_id = cur.lastrowid
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, new_value, created_at) VALUES (?, 'create', ?, ?)",
            (prod_id, json.dumps({"produced_qty": produced_qty, "location": location}, ensure_ascii=False), ts),
        )
        con.commit()
    return prod_id


def use_production(production_id: int, use_qty: int, changed_by: str = "") -> Dict[str, Any]:
    ts = now_str()
    with get_connection() as con:
        row = con.execute(
            "SELECT remaining_qty, status FROM prepacking_productions WHERE id=?",
            (production_id,),
        ).fetchone()
        if not row:
            return {"success": False, "error": "제작 기록을 찾을 수 없습니다."}
        remaining, status = row
        if status not in ("active", "carried", "held"):
            return {"success": False, "error": f"현재 상태({status})에서는 사용할 수 없습니다."}
        if use_qty > remaining:
            return {"success": False, "error": f"잔여 수량({remaining})보다 많이 사용할 수 없습니다."}

        new_remaining = remaining - use_qty
        new_status = "depleted" if new_remaining == 0 else status
        con.execute(
            "UPDATE prepacking_productions SET remaining_qty=?, status=?, updated_at=? WHERE id=?",
            (new_remaining, new_status, ts, production_id),
        )
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, field_changed, old_value, new_value, changed_by, created_at) "
            "VALUES (?, 'use', 'remaining_qty', ?, ?, ?, ?)",
            (production_id, str(remaining), str(new_remaining), changed_by, ts),
        )
        con.commit()
    return {"success": True, "remaining_qty": new_remaining, "status": new_status}


def update_production_status(production_id: int, new_status: str, changed_by: str = "") -> Dict[str, Any]:
    valid = {"active", "carried", "held", "disassemble", "disassembled", "depleted"}
    if new_status not in valid:
        return {"success": False, "error": f"유효하지 않은 상태: {new_status}"}
    ts = now_str()
    with get_connection() as con:
        row = con.execute("SELECT status FROM prepacking_productions WHERE id=?", (production_id,)).fetchone()
        if not row:
            return {"success": False, "error": "제작 기록을 찾을 수 없습니다."}
        old_status = row[0]
        con.execute(
            "UPDATE prepacking_productions SET status=?, updated_at=? WHERE id=?",
            (new_status, ts, production_id),
        )
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, field_changed, old_value, new_value, changed_by, created_at) "
            "VALUES (?, 'status_change', 'status', ?, ?, ?, ?)",
            (production_id, old_status, new_status, changed_by, ts),
        )
        con.commit()
    return {"success": True, "old_status": old_status, "new_status": new_status}


def update_production_location(production_id: int, new_location: str, changed_by: str = "") -> Dict[str, Any]:
    ts = now_str()
    with get_connection() as con:
        row = con.execute("SELECT location FROM prepacking_productions WHERE id=?", (production_id,)).fetchone()
        if not row:
            return {"success": False, "error": "제작 기록을 찾을 수 없습니다."}
        old_loc = row[0]
        con.execute(
            "UPDATE prepacking_productions SET location=?, updated_at=? WHERE id=?",
            (new_location, ts, production_id),
        )
        con.execute(
            "INSERT INTO prepacking_logs (production_id, action, field_changed, old_value, new_value, changed_by, created_at) "
            "VALUES (?, 'location_change', 'location', ?, ?, ?, ?)",
            (production_id, old_loc, new_location, changed_by, ts),
        )
        con.commit()
    return {"success": True, "old_location": old_loc, "new_location": new_location}


def get_active_productions(vendor: Optional[str] = None) -> List[Dict]:
    with get_connection() as con:
        if vendor:
            rows = con.execute(
                """SELECT id, vendor, target_date, combo_key, combo_detail,
                          predicted_qty, produced_qty, remaining_qty, location, status, created_at
                   FROM prepacking_productions
                   WHERE vendor=? AND status IN ('active','carried','held')
                   ORDER BY target_date DESC, combo_key""",
                (vendor,),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT id, vendor, target_date, combo_key, combo_detail,
                          predicted_qty, produced_qty, remaining_qty, location, status, created_at
                   FROM prepacking_productions
                   WHERE status IN ('active','carried','held')
                   ORDER BY vendor, target_date DESC, combo_key"""
            ).fetchall()
    return [
        {
            "id": r[0], "vendor": r[1], "target_date": r[2], "combo_key": r[3],
            "combo_detail": r[4], "predicted_qty": r[5], "produced_qty": r[6],
            "remaining_qty": r[7], "location": r[8], "status": r[9], "created_at": r[10],
        }
        for r in rows
    ]


def get_productions_by_date(vendor: str, target_date: date) -> List[Dict]:
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, combo_key, combo_detail, predicted_qty, produced_qty,
                      remaining_qty, location, status, created_at
               FROM prepacking_productions
               WHERE vendor=? AND target_date=?
               ORDER BY combo_key""",
            (vendor, target_date.isoformat()),
        ).fetchall()
    return [
        {
            "id": r[0], "combo_key": r[1], "combo_detail": r[2], "predicted_qty": r[3],
            "produced_qty": r[4], "remaining_qty": r[5], "location": r[6], "status": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


# ── 일일 지시 ───────────────────────

def generate_daily_instructions(vendor: str, today: Optional[date] = None) -> Dict[str, Any]:
    """
    오늘의 프리패킹 지시:
    - carry: 내일도 필요한 조합 → 유지
    - hold: 유지기간 내 → 보류
    - disassemble: 유지기간 초과 → 해체
    - new_production: 신규 제작 (유지분 차감)
    """
    if today is None:
        today = date.today()
    tomorrow = today + timedelta(days=1)
    retention_days = get_settings(vendor)["retention_days"]

    active = get_active_productions(vendor)
    tomorrow_preds = predict_for_date(vendor, tomorrow)
    tomorrow_keys = {p["combo_key"]: p for p in tomorrow_preds}

    carry_list, disassemble_list, hold_list = [], [], []

    for prod in active:
        if prod["remaining_qty"] <= 0:
            continue
        key = prod["combo_key"]
        prod_date = datetime.strptime(prod["target_date"], "%Y-%m-%d").date() if isinstance(prod["target_date"], str) else prod["target_date"]
        age_days = (today - prod_date).days

        if key in tomorrow_keys:
            carry_list.append({**prod, "tomorrow_predicted": tomorrow_keys[key]["predicted_qty"]})
        elif age_days >= retention_days:
            disassemble_list.append({**prod, "age_days": age_days})
        else:
            hold_list.append({**prod, "age_days": age_days, "expires_in": retention_days - age_days})

    carry_remaining: Dict[str, int] = {}
    for c in carry_list:
        carry_remaining[c["combo_key"]] = carry_remaining.get(c["combo_key"], 0) + c["remaining_qty"]

    new_production = []
    for pred in tomorrow_preds:
        existing = carry_remaining.get(pred["combo_key"], 0)
        needed = max(0, pred["predicted_qty"] - existing)
        if needed > 0:
            new_production.append({
                "combo_key": pred["combo_key"],
                "combo_detail": pred["combo_detail"],
                "predicted_qty": pred["predicted_qty"],
                "existing_qty": existing,
                "new_qty": needed,
            })

    return {
        "vendor": vendor,
        "date": today.isoformat(),
        "tomorrow": tomorrow.isoformat(),
        "carry": carry_list,
        "hold": hold_list,
        "disassemble": disassemble_list,
        "new_production": new_production,
    }


# ── 정확도 ──────────────────────────

def update_actual_qty(vendor: str, target_date: date) -> Dict[str, Any]:
    analysis = analyze_combinations(vendor, target_date, target_date)
    actual_map: Dict[str, int] = {c["combo_key"]: c["count"] for c in analysis.get("combos", [])}

    with get_connection() as con:
        preds = con.execute(
            "SELECT id, combo_key, predicted_qty, ai_adjusted_qty FROM prepacking_predictions WHERE vendor=? AND target_date=?",
            (vendor, target_date.isoformat()),
        ).fetchall()

        updated = 0
        total_mape = 0.0
        count_mape = 0

        for pid, key, pred_qty, ai_qty in preds:
            actual = actual_map.get(key, 0)
            effective_pred = ai_qty if ai_qty is not None else pred_qty
            mape = abs(effective_pred - actual) / max(actual, 1) * 100 if actual > 0 else None
            con.execute("UPDATE prepacking_predictions SET actual_qty=?, mape=? WHERE id=?", (actual, mape, pid))
            updated += 1
            if mape is not None:
                total_mape += mape
                count_mape += 1

        con.commit()

    avg_mape = total_mape / count_mape if count_mape > 0 else None
    return {
        "vendor": vendor,
        "target_date": target_date.isoformat(),
        "predictions_updated": updated,
        "avg_mape": round(avg_mape, 2) if avg_mape is not None else None,
    }


def get_accuracy_history(vendor: str, limit: int = 30) -> List[Dict]:
    with get_connection() as con:
        rows = con.execute(
            """SELECT target_date, COUNT(*) as combo_count, AVG(mape) as avg_mape,
                      SUM(predicted_qty) as total_predicted,
                      SUM(COALESCE(ai_adjusted_qty, predicted_qty)) as total_ai_predicted,
                      SUM(actual_qty) as total_actual
               FROM prepacking_predictions
               WHERE vendor=? AND actual_qty IS NOT NULL
               GROUP BY target_date ORDER BY target_date DESC LIMIT ?""",
            (vendor, limit),
        ).fetchall()
    return [
        {
            "target_date": r[0], "combo_count": r[1],
            "avg_mape": round(r[2], 2) if r[2] is not None else None,
            "total_predicted": r[3], "total_ai_predicted": r[4], "total_actual": r[5],
        }
        for r in rows
    ]


# ── 효율 지표 ───────────────────────

def get_efficiency_stats(vendor: str, days: int = 30) -> Dict[str, Any]:
    d_from = (date.today() - timedelta(days=days)).isoformat()
    with get_connection() as con:
        row = con.execute(
            """SELECT COUNT(*), SUM(produced_qty), SUM(produced_qty - remaining_qty),
                      SUM(CASE WHEN status='depleted' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN status='disassembled' THEN 1 ELSE 0 END)
               FROM prepacking_productions WHERE vendor=? AND target_date >= ?""",
            (vendor, d_from),
        ).fetchone()

    if not row or row[0] == 0:
        return {"total": 0, "utilization_rate": 0, "waste_rate": 0}

    total, total_produced, total_used, depleted, disassembled = row
    total_produced = total_produced or 0
    total_used = total_used or 0

    return {
        "total": total,
        "total_produced": total_produced,
        "total_used": total_used,
        "depleted_count": depleted or 0,
        "disassembled_count": disassembled or 0,
        "utilization_rate": round((total_used / total_produced * 100) if total_produced > 0 else 0, 1),
        "waste_rate": round((disassembled / total * 100) if total > 0 else 0, 1),
    }
