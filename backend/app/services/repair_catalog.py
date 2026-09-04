"""
수선 작업/불량/기본비용 마스터
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from logic.db import get_connection

# 작업명, 기본비용, 별칭(쉼표)
DEFAULT_WORK_TYPES: List[Tuple[str, int, str]] = [
    ("스팀작업", 700, "스팀"),
    ("단순바느질", 1500, "바느질,바느질작업"),
    ("손뜨개작업", 1500, "손뜨개"),
    ("열펜제거", 700, "열펜작업"),
    ("잡사제거", 700, ""),
    ("부분세탁", 700, "물티슈작업,부분세탁(물티슈작업)"),
    ("전체세탁", 1500, "세탁"),
    ("보풀제거", 500, "보풀"),
]

DEFAULT_DEFECTS: List[Tuple[str, str]] = [
    ("올풀림", ""),
    ("봉제 불량", "봉제불량"),
    ("구멍", "구멍수선"),
    ("오염", ""),
    ("열펜", "열펜자국"),
    ("기름얼룩", "기름,기름때"),
    ("잡사", ""),
    ("넥라인불량", "넥라인"),
]


def ensure_catalog_tables(con=None) -> None:
    own = con is None
    if own:
        ctx = get_connection()
        con = ctx.__enter__()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_work_type (
                작업명 TEXT PRIMARY KEY,
                기본비용 INTEGER NOT NULL,
                별칭 TEXT,
                저장시간 TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_defect (
                불량명 TEXT PRIMARY KEY,
                별칭 TEXT,
                저장시간 TIMESTAMP
            )
        """)
        cols = [c[1] for c in con.execute("PRAGMA table_info(repair_work_log)")]
        if cols and "불량명" not in cols:
            con.execute("ALTER TABLE repair_work_log ADD COLUMN 불량명 TEXT")
        now = datetime.now().isoformat()
        for name, price, aliases in DEFAULT_WORK_TYPES:
            con.execute(
                """INSERT OR IGNORE INTO repair_work_type (작업명, 기본비용, 별칭, 저장시간)
                   VALUES (?, ?, ?, ?)""",
                (name, price, aliases or None, now),
            )
        for name, aliases in DEFAULT_DEFECTS:
            con.execute(
                """INSERT OR IGNORE INTO repair_defect (불량명, 별칭, 저장시간)
                   VALUES (?, ?, ?)""",
                (name, aliases or None, now),
            )
        con.commit()
    finally:
        if own:
            ctx.__exit__(None, None, None)


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").replace("(", "").replace(")", "").lower()


def _alias_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [a.strip() for a in raw.split(",") if a.strip()]


def resolve_work_type(name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    ensure_catalog_tables()
    q = name.strip()
    nq = _norm(q)
    with get_connection() as con:
        rows = con.execute(
            "SELECT 작업명, 기본비용, 별칭 FROM repair_work_type"
        ).fetchall()
    best = None
    for 작업명, 기본비용, 별칭 in rows:
        names = [작업명, *_alias_list(별칭)]
        if any(_norm(n) == nq for n in names):
            return {"작업명": 작업명, "기본비용": int(기본비용), "별칭": 별칭}
        if any(nq in _norm(n) or _norm(n) in nq for n in names if _norm(n)):
            best = {"작업명": 작업명, "기본비용": int(기본비용), "별칭": 별칭}
    return best


def resolve_defect(name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    ensure_catalog_tables()
    q = name.strip()
    nq = _norm(q)
    with get_connection() as con:
        rows = con.execute("SELECT 불량명, 별칭 FROM repair_defect").fetchall()
    best = None
    for 불량명, 별칭 in rows:
        names = [불량명, *_alias_list(별칭)]
        if any(_norm(n) == nq for n in names):
            return {"불량명": 불량명, "별칭": 별칭}
        if any(nq in _norm(n) or _norm(n) in nq for n in names if _norm(n)):
            best = {"불량명": 불량명, "별칭": 별칭}
    return best


def lookup_repair_price(vendor: Optional[str], work_type: Optional[str]) -> Dict[str, Any]:
    """업체+작업 최근 비용, 없으면 기본비용."""
    ensure_catalog_tables()
    resolved = resolve_work_type(work_type)
    work_name = resolved["작업명"] if resolved else (work_type or "").strip()
    default_price = resolved["기본비용"] if resolved else None

    last_price = None
    last_date = None
    if vendor and work_name:
        with get_connection() as con:
            row = con.execute(
                """SELECT 비용, 날짜 FROM repair_work_log
                   WHERE 업체명 = ? AND 작업 = ? AND 비용 IS NOT NULL AND 비용 > 0
                   ORDER BY COALESCE(저장시간, 날짜) DESC, id DESC LIMIT 1""",
                (vendor.strip(), work_name),
            ).fetchone()
            if row:
                last_price = int(row[0])
                last_date = row[1]

    if last_price:
        return {
            "found": True,
            "source": "vendor_history",
            "작업명": work_name,
            "비용": last_price,
            "기본비용": default_price,
            "날짜": last_date,
            "message": f"{vendor} {work_name} 최근 비용은 {last_price:,}원이었습니다. 그대로 저장할까요?",
        }
    if default_price is not None:
        return {
            "found": True,
            "source": "default",
            "작업명": work_name,
            "비용": default_price,
            "기본비용": default_price,
            "날짜": None,
            "message": f"{work_name} 기본 비용은 {default_price:,}원입니다. 그대로 저장할까요?",
        }
    return {
        "found": False,
        "source": None,
        "작업명": work_name or work_type,
        "비용": None,
        "기본비용": None,
        "message": "등록된 비용이 없어요. 금액을 알려주세요.",
    }


def list_work_types() -> List[Dict[str, Any]]:
    ensure_catalog_tables()
    with get_connection() as con:
        rows = con.execute(
            "SELECT 작업명, 기본비용, 별칭 FROM repair_work_type ORDER BY 작업명"
        ).fetchall()
    return [{"작업명": r[0], "기본비용": r[1], "별칭": r[2]} for r in rows]


def list_defects() -> List[Dict[str, Any]]:
    ensure_catalog_tables()
    with get_connection() as con:
        rows = con.execute("SELECT 불량명, 별칭 FROM repair_defect ORDER BY 불량명").fetchall()
    return [{"불량명": r[0], "별칭": r[1]} for r in rows]


def upsert_work_type(name: str, price: int, aliases: Optional[str] = None) -> None:
    ensure_catalog_tables()
    now = datetime.now().isoformat()
    with get_connection() as con:
        con.execute(
            """INSERT INTO repair_work_type (작업명, 기본비용, 별칭, 저장시간)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(작업명) DO UPDATE SET
                 기본비용=excluded.기본비용,
                 별칭=COALESCE(excluded.별칭, repair_work_type.별칭),
                 저장시간=excluded.저장시간""",
            (name.strip(), int(price), aliases or None, now),
        )
        con.commit()


def upsert_defect(name: str, aliases: Optional[str] = None) -> None:
    ensure_catalog_tables()
    now = datetime.now().isoformat()
    with get_connection() as con:
        con.execute(
            """INSERT INTO repair_defect (불량명, 별칭, 저장시간)
               VALUES (?, ?, ?)
               ON CONFLICT(불량명) DO UPDATE SET
                 별칭=COALESCE(excluded.별칭, repair_defect.별칭),
                 저장시간=excluded.저장시간""",
            (name.strip(), aliases or None, now),
        )
        con.commit()


def delete_work_type(name: str) -> bool:
    ensure_catalog_tables()
    with get_connection() as con:
        cur = con.execute("DELETE FROM repair_work_type WHERE 작업명 = ?", (name,))
        con.commit()
        return cur.rowcount > 0


def delete_defect(name: str) -> bool:
    ensure_catalog_tables()
    with get_connection() as con:
        cur = con.execute("DELETE FROM repair_defect WHERE 불량명 = ?", (name,))
        con.commit()
        return cur.rowcount > 0


def catalog_context_for_ai() -> str:
    works = list_work_types()
    defects = list_defects()
    w = ", ".join(f"{x['작업명']}({x['기본비용']}원)" for x in works)
    d = ", ".join(x["불량명"] for x in defects)
    return f"수선 작업: {w}\n수선 불량명: {d}"
