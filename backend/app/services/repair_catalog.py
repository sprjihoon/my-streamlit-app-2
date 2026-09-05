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


def _boundary_hit(haystack: str, needle: str) -> bool:
    if not needle or needle not in haystack:
        return False
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return False
        left = haystack[idx - 1] if idx > 0 else ""
        right = haystack[idx + len(needle)] if idx + len(needle) < len(haystack) else ""
        left_ok = not left.isalpha() and not ("가" <= left <= "힣")
        right_ok = not right.isalpha() and not ("가" <= right <= "힣")
        if left_ok or right_ok or len(needle) >= 3:
            if left_ok and right_ok:
                return True
            if len(needle) >= 4:
                return True
        start = idx + 1


def rank_work_type_matches(name: Optional[str]) -> List[Dict[str, Any]]:
    """canonical 정확 → alias 정확 → 가장 긴 경계 → 부분 포함. 동점이면 모두 반환."""
    if not name:
        return []
    ensure_catalog_tables()
    nq = _norm(name)
    with get_connection() as con:
        rows = con.execute(
            "SELECT 작업명, 기본비용, 별칭 FROM repair_work_type"
        ).fetchall()
    exact_canon = []
    exact_alias = []
    boundary = []
    partial = []
    for 작업명, 기본비용, 별칭 in rows:
        aliases = _alias_list(별칭)
        item = {"작업명": 작업명, "기본비용": int(기본비용), "별칭": 별칭}
        if _norm(작업명) == nq:
            exact_canon.append(item)
            continue
        if any(_norm(a) == nq for a in aliases):
            exact_alias.append(item)
            continue
        names = [작업명, *aliases]
        if any(_boundary_hit(nq, _norm(n)) for n in names if _norm(n)):
            boundary.append((len(max((_norm(n) for n in names if _norm(n) and _norm(n) in nq), default="")), item))
            continue
        if any(_norm(n) and (_norm(n) in nq or nq in _norm(n)) for n in names):
            partial.append((len(max((_norm(n) for n in names if _norm(n)), default="")), item))
    if exact_canon:
        return exact_canon
    if exact_alias:
        return exact_alias
    if boundary:
        best_len = max(score for score, _ in boundary)
        winners = [item for score, item in boundary if score == best_len]
        return winners
    if partial:
        best_len = max(score for score, _ in partial)
        return [item for score, item in partial if score == best_len]
    return []


def resolve_work_type(name: Optional[str]) -> Optional[Dict[str, Any]]:
    matches = rank_work_type_matches(name)
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_work_type_candidates(name: Optional[str]) -> List[Dict[str, Any]]:
    return rank_work_type_matches(name)


def resolve_defect(name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    ensure_catalog_tables()
    nq = _norm(name)
    if nq in {"수선"}:
        return None
    with get_connection() as con:
        rows = con.execute("SELECT 불량명, 별칭 FROM repair_defect").fetchall()
    exact = []
    partial = []
    for 불량명, 별칭 in rows:
        names = [불량명, *_alias_list(별칭)]
        item = {"불량명": 불량명, "별칭": 별칭}
        if any(_norm(n) == nq for n in names):
            exact.append(item)
            continue
        if any(_norm(n) and _norm(n) != "수선" and (_norm(n) in nq or nq in _norm(n)) for n in names):
            partial.append((len(max((_norm(n) for n in names if _norm(n)), default="")), item))
    if exact:
        return exact[0]
    if len(partial) == 1:
        return partial[0][1]
    if partial:
        best_len = max(score for score, _ in partial)
        winners = [item for score, item in partial if score == best_len]
        return winners[0] if len(winners) == 1 else None
    return None


def _latest_log_price(
    work_name: str,
    vendor: Optional[str] = None,
    product: Optional[str] = None,
) -> Optional[Tuple[int, Optional[str]]]:
    clauses = ["작업 = ?", "비용 IS NOT NULL", "비용 > 0"]
    params: List[Any] = [work_name]
    if vendor:
        clauses.append("업체명 = ?")
        params.append(vendor.strip())
    if product:
        clauses.append("제품명 = ?")
        params.append(product.strip())
    with get_connection() as con:
        row = con.execute(
            f"""SELECT 비용, 날짜 FROM repair_work_log
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(저장시간, 날짜) DESC, id DESC LIMIT 1""",
            params,
        ).fetchone()
    if not row:
        return None
    return int(row[0]), row[1]


def lookup_repair_price(
    vendor: Optional[str],
    work_type: Optional[str],
    product: Optional[str] = None,
) -> Dict[str, Any]:
    """제품+작업 최근 비용, 없으면 업체+작업, 없으면 기본비용."""
    ensure_catalog_tables()
    candidates = resolve_work_type_candidates(work_type)
    if len(candidates) > 1:
        return {
            "found": False,
            "candidates": candidates,
            "message": "여러 작업이 맞아요. " + ", ".join(c["작업명"] for c in candidates) + " 중에서 골라주세요.",
        }
    resolved = candidates[0] if candidates else None
    work_name = resolved["작업명"] if resolved else (work_type or "").strip()
    default_price = resolved["기본비용"] if resolved else None
    vendor_name = (vendor or "").strip() or None
    product_name = (product or "").strip() or None

    hit = None
    source = None
    if work_name and product_name and vendor_name:
        hit = _latest_log_price(work_name, vendor=vendor_name, product=product_name)
        if hit:
            source = "product_history"
    if hit is None and work_name and product_name:
        hit = _latest_log_price(work_name, product=product_name)
        if hit:
            source = "product_history"
    if hit is None and work_name and vendor_name:
        hit = _latest_log_price(work_name, vendor=vendor_name)
        if hit:
            source = "vendor_history"

    if hit:
        last_price, last_date = hit
        if source == "product_history":
            label = " / ".join(x for x in (vendor_name, product_name) if x)
            message = f"{label} {work_name} 최근 비용은 {last_price:,}원이었습니다. 그대로 저장할까요?"
        else:
            message = f"{vendor_name} {work_name} 최근 비용은 {last_price:,}원이었습니다. 그대로 저장할까요?"
        return {
            "found": True,
            "source": source,
            "작업명": work_name,
            "제품명": product_name,
            "비용": last_price,
            "기본비용": default_price,
            "날짜": last_date,
            "message": message,
        }
    if default_price is not None:
        return {
            "found": True,
            "source": "default",
            "작업명": work_name,
            "제품명": product_name,
            "비용": default_price,
            "기본비용": default_price,
            "날짜": None,
            "message": f"{work_name} 기본 비용은 {default_price:,}원입니다. 그대로 저장할까요?",
        }
    return {
        "found": False,
        "source": None,
        "작업명": work_name or work_type,
        "제품명": product_name,
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
