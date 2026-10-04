"""Invoice statistics tool."""
from typing import Dict

from logic.db import get_connection

from .common import QUERY_MAX_LIMIT, _clamp_limit

def _get_invoice_stats(args: Dict, user_id: str, user_name: str) -> Dict:
    """인보이스 통계 조회 (청구 기간 기준)"""
    conditions = []
    params = []
    
    # 날짜 조건 - period_from이 지정 기간 내인 인보이스 조회
    # 예: 1월 조회 → period_from이 2026-01-01 ~ 2026-01-31 사이인 인보이스
    if args.get("start_date") and args.get("end_date"):
        conditions.append("i.period_from BETWEEN ? AND ?")
        params.extend([args["start_date"], args["end_date"]])
    elif args.get("start_date"):
        conditions.append("i.period_from >= ?")
        params.append(args["start_date"])
    elif args.get("end_date"):
        conditions.append("i.period_from <= ?")
        params.append(args["end_date"])
    
    # 업체 조건
    if args.get("vendor"):
        conditions.append("v.vendor LIKE ?")
        params.append(f"%{args['vendor']}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    top_n = _clamp_limit(args.get("top_n"), default=10, maximum=QUERY_MAX_LIMIT)
    
    try:
        with get_connection() as con:
            # 전체 통계
            total_stats = con.execute(f"""
                SELECT COUNT(*), COALESCE(SUM(i.total_amount), 0)
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE {where_clause}
            """, params).fetchone()
            
            # 업체별 통계 (상위 N개)
            vendor_stats = con.execute(f"""
                SELECT v.vendor, COUNT(*) as cnt, SUM(i.total_amount) as total
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE {where_clause} AND v.vendor IS NOT NULL
                GROUP BY v.vendor
                ORDER BY total DESC
                LIMIT ?
            """, params + [top_n]).fetchall()
            
            # 최근 인보이스 5건
            recent = con.execute(f"""
                SELECT v.vendor, i.total_amount, i.period_from, i.period_to, i.created_at
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE {where_clause}
                ORDER BY i.created_at DESC
                LIMIT 5
            """, params).fetchall()
        
        # 결과 구성
        result = {
            "success": True,
            "query_params": {
                "start_date": args.get("start_date"),
                "end_date": args.get("end_date"),
                "vendor": args.get("vendor"),
                "where_clause": where_clause
            },
            "total_count": total_stats[0] or 0,
            "total_amount": total_stats[1] or 0,
            "by_vendor": [
                {"vendor": r[0], "count": r[1], "amount": r[2] or 0}
                for r in vendor_stats
            ],
            "recent": [
                {
                    "vendor": r[0],
                    "amount": r[1] or 0,
                    "period": f"{r[2]} ~ {r[3]}" if r[2] and r[3] else "",
                    "created": r[4]
                }
                for r in recent
            ]
        }
        
        # 상위 업체 정보
        if vendor_stats:
            top_vendor = vendor_stats[0]
            result["top_vendor"] = {
                "name": top_vendor[0],
                "count": top_vendor[1],
                "amount": top_vendor[2] or 0
            }
            result["message"] = f"청구금액 1위: {top_vendor[0]} ({top_vendor[2]:,.0f}원, {top_vendor[1]}건)"
        else:
            result["message"] = "조건에 맞는 인보이스가 없습니다."
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}
