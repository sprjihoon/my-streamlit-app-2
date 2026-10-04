"""Work-log tool handlers."""
from datetime import datetime
from typing import Dict

from logic.db import get_connection
from backend.app.api.logs import add_log

from .common import _clamp_limit, _stats_group_order

def _save_work_log(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 저장"""
    vendor = args.get("vendor", "")
    work_type = args.get("work_type", "")
    unit_price = args.get("unit_price", 0)
    qty = args.get("qty", 1)
    date = args.get("date") or datetime.now().strftime("%Y-%m-%d")
    remark = args.get("remark", "")
    
    if not vendor or not work_type or not unit_price:
        return {"success": False, "error": "업체명, 작업종류, 단가는 필수입니다."}
    
    # 업체명 검증 - 등록된 업체인지 확인
    with get_connection() as con:
        # 공백 제거한 버전도 준비
        vendor_normalized = vendor.replace(" ", "").replace("　", "")
        
        # 1. 정확히 일치하는 업체 검색 (vendors 테이블 + aliases 테이블)
        # aliases 테이블: alias, file_type, vendor (vendor는 문자열)
        vendor_check = con.execute(
            """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
               UNION
               SELECT vendor FROM aliases WHERE LOWER(alias) = LOWER(?)""",
            (vendor, vendor)
        ).fetchone()
        
        # 2. 정확히 일치 없으면 → 공백 제거 후 검색
        if not vendor_check:
            vendor_check = con.execute(
                """SELECT vendor FROM vendors 
                   WHERE REPLACE(LOWER(vendor), ' ', '') = LOWER(?)
                   UNION
                   SELECT vendor FROM aliases 
                   WHERE REPLACE(LOWER(alias), ' ', '') = LOWER(?)""",
                (vendor_normalized, vendor_normalized)
            ).fetchone()
        
        # 3. 여전히 없으면 → 부분 일치 검색 (결과가 1개면 자동 선택)
        if not vendor_check:
            partial_matches = con.execute(
                """SELECT DISTINCT vendor FROM vendors 
                   WHERE vendor LIKE ? OR vendor LIKE ?
                   UNION
                   SELECT DISTINCT vendor FROM aliases 
                   WHERE alias LIKE ? OR alias LIKE ?""",
                (f"%{vendor}%", f"%{vendor_normalized}%", f"%{vendor}%", f"%{vendor_normalized}%")
            ).fetchall()
            
            if len(partial_matches) == 1:
                # 부분 일치가 1개면 자동 선택
                vendor_check = partial_matches[0]
        
        if not vendor_check:
            # 유사한 업체명 제안
            similar = con.execute(
                """SELECT vendor FROM vendors 
                   WHERE vendor LIKE ? OR vendor LIKE ? 
                   LIMIT 5""",
                (f"%{vendor}%", f"%{vendor[:2]}%")
            ).fetchall()
            
            similar_names = [r[0] for r in similar] if similar else []
            suggestion = f" 비슷한 업체: {', '.join(similar_names)}" if similar_names else ""
            
            return {
                "success": False, 
                "error": f"'{vendor}'은(는) 등록되지 않은 업체입니다.{suggestion}",
                "unknown_vendor": vendor,
                "similar_vendors": similar_names
            }
        
        # 정식 업체명으로 변환 (별칭으로 입력한 경우)
        vendor = vendor_check[0]
    
    total = unit_price * qty
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        cursor = con.execute(
            """INSERT INTO work_log 
               (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, vendor, work_type, unit_price, qty, total, remark, user_name, 저장시간, "bot", user_id)
        )
        con.commit()
        record_id = cursor.lastrowid
    
    # 이력 기록
    _log_work_history(record_id, "create", {
        "날짜": date, "업체명": vendor, "분류": work_type,
        "단가": unit_price, "수량": qty, "합계": total, "작성자": user_name
    }, user_name, "봇 입력", user_id)
    
    # 활동 로그
    add_log(
        action_type="작업일지_생성",
        target_type="work_log",
        target_id=str(record_id),
        target_name=f"{vendor} {work_type}",
        user_nickname=user_name or "봇",
        details=f"날짜: {date}, 합계: {total:,}원 (봇 입력)"
    )
    
    return {
        "success": True,
        "record_id": record_id,
        "data": {
            "vendor": vendor,
            "work_type": work_type,
            "qty": qty,
            "unit_price": unit_price,
            "total": total,
            "date": date,
            "remark": remark
        },
        "message": f"저장완료! {vendor} {work_type} {total:,}원"
    }

def _save_multiple_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """여러 작업일지 저장"""
    entries = args.get("entries", [])
    if not entries:
        return {"success": False, "error": "저장할 항목이 없습니다."}
    
    results = []
    total_saved = 0
    total_amount = 0
    
    for entry in entries:
        result = _save_work_log(entry, user_id, user_name)
        results.append(result)
        if result.get("success"):
            total_saved += 1
            total_amount += result["data"]["total"]
    
    return {
        "success": True,
        "saved_count": total_saved,
        "total_amount": total_amount,
        "results": results,
        "message": f"{total_saved}건 저장완료! 총 {total_amount:,}원"
    }

def _delete_work_log(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 삭제 - 상세 정보 포함"""
    log_id = args.get("log_id")
    delete_recent = args.get("delete_recent", False)
    
    with get_connection() as con:
        # 삭제할 레코드 찾기 (비고 포함)
        if delete_recent:
            row = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 비고1
                   FROM work_log WHERE works_user_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (user_id,)
            ).fetchone()
        elif log_id:
            row = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 비고1
                   FROM work_log WHERE id = ? AND works_user_id = ?""",
                (log_id, user_id)
            ).fetchone()
        else:
            # 조건으로 찾기
            conditions = []
            params = []
            if args.get("vendor"):
                conditions.append("업체명 LIKE ?")
                params.append(f"%{args['vendor']}%")
            if args.get("work_type"):
                conditions.append("분류 LIKE ?")
                params.append(f"%{args['work_type']}%")
            if args.get("date"):
                conditions.append("날짜 = ?")
                params.append(args["date"])
            if args.get("price"):
                conditions.append("합계 BETWEEN ? AND ?")
                params.extend([int(args["price"] * 0.9), int(args["price"] * 1.1)])
            
            if not conditions:
                return {"success": False, "error": "삭제 조건을 지정해주세요."}
            
            # 사용자 제한
            conditions.append("works_user_id = ?")
            params.append(user_id)
            
            row = con.execute(
                f"""SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 비고1
                   FROM work_log WHERE {' AND '.join(conditions)}
                   ORDER BY id DESC LIMIT 1""",
                params
            ).fetchone()
        
        if not row:
            return {"success": False, "error": "삭제할 작업일지를 찾지 못했습니다."}
        
        log_id = row[0]
        log_data = {
            "id": row[0], "날짜": row[1], "업체명": row[2], "분류": row[3],
            "단가": row[4], "수량": row[5], "합계": row[6], "작성자": row[7],
            "비고": row[8] if len(row) > 8 else None
        }
        
        # 이력 기록
        _log_work_history(log_id, "delete", log_data, user_name, "삭제", user_id)
        
        # 삭제
        con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
        con.commit()
    
    # 활동 로그
    add_log(
        action_type="작업일지_삭제",
        target_type="work_log",
        target_id=str(log_id),
        target_name=f"{log_data['업체명']} {log_data['분류']}",
        user_nickname=user_name or "봇",
        details=f"날짜: {log_data['날짜']}, 합계: {log_data['합계']:,}원"
    )
    
    # 상세 삭제 메시지 구성
    날짜 = log_data['날짜']
    업체명 = log_data['업체명']
    분류 = log_data['분류']
    단가 = log_data['단가'] or 0
    수량 = log_data['수량'] or 1
    합계 = log_data['합계'] or 0
    비고 = log_data.get('비고')
    
    # 상세 메시지
    detail_msg = f"🗑️ 삭제 완료!\n"
    detail_msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    detail_msg += f"📅 날짜: {날짜}\n"
    detail_msg += f"🏢 업체: {업체명}\n"
    detail_msg += f"📋 작업: {분류}\n"
    detail_msg += f"💵 단가: {단가:,}원\n"
    detail_msg += f"📦 수량: {수량}건\n"
    detail_msg += f"💰 합계: {합계:,}원\n"
    if 비고:
        detail_msg += f"📝 비고: {비고}\n"
    detail_msg += f"━━━━━━━━━━━━━━━━━━━━"
    
    return {
        "success": True,
        "deleted": log_data,
        "message": detail_msg
    }

def _search_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 검색 (업체 별칭 지원)"""
    conditions = []
    params = []
    
    vendor_query = args.get("vendor")
    vendor_resolved = None
    if args.get("vendor"):
        vendor_search = args['vendor']
        # 별칭 테이블에서 실제 업체명 찾기
        with get_connection() as con:
            # aliases에서 검색
            alias_rows = con.execute(
                "SELECT DISTINCT vendor FROM aliases WHERE alias LIKE ? OR vendor LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
            # vendors에서도 검색
            vendor_rows = con.execute(
                "SELECT vendor FROM vendors WHERE vendor LIKE ? OR name LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
        # 조회 시 사용한 검색어 → 실제 정식 업체명 (봇 응답용)
        if alias_rows:
            vendor_resolved = alias_rows[0][0]
        elif vendor_rows:
            vendor_resolved = vendor_rows[0][0]
        # 찾은 모든 업체명으로 검색
        all_vendors = set([r[0] for r in alias_rows if r[0]] + [r[0] for r in vendor_rows if r[0]])
        all_vendors.add(vendor_search)  # 원본 검색어도 포함
        
        if len(all_vendors) == 1:
            conditions.append("업체명 LIKE ?")
            params.append(f"%{list(all_vendors)[0]}%")
        else:
            vendor_conditions = " OR ".join(["업체명 LIKE ?" for _ in all_vendors])
            conditions.append(f"({vendor_conditions})")
            params.extend([f"%{v}%" for v in all_vendors])
    if args.get("work_type"):
        conditions.append("분류 LIKE ?")
        params.append(f"%{args['work_type']}%")
    if args.get("date"):
        conditions.append("날짜 = ?")
        params.append(args["date"])
    elif args.get("start_date") and args.get("end_date"):
        conditions.append("날짜 >= ? AND 날짜 <= ?")
        params.extend([args["start_date"], args["end_date"]])
    elif args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    elif args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    if args.get("price"):
        conditions.append("합계 BETWEEN ? AND ?")
        params.extend([int(args["price"] * 0.9), int(args["price"] * 1.1)])
    if args.get("worker"):
        conditions.append("작성자 LIKE ?")
        params.append(f"%{args['worker']}%")
    if args.get("remark"):
        conditions.append("비고1 LIKE ?")
        params.append(f"%{args['remark']}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit = _clamp_limit(args.get("limit"))
    
    with get_connection() as con:
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log WHERE {where_clause}
               ORDER BY 날짜 DESC, id DESC LIMIT ?""",
            params + [limit]
        ).fetchall()
        
        logs = [
            {"id": r[0], "날짜": r[1], "업체명": r[2], "분류": r[3], "수량": r[4],
             "단가": r[5], "합계": r[6], "저장시간": str(r[7]) if r[7] else None, "작성자": r[8]}
            for r in rows
        ]
        
        total_amount = sum(l["합계"] or 0 for l in logs)
    
    result = {
        "success": True,
        "count": len(logs),
        "total_amount": total_amount,
        "logs": logs,
        "message": f"검색결과: {len(logs)}건, 총 {total_amount:,}원"
    }
    if vendor_query:
        result["vendor_query"] = vendor_query
    if vendor_resolved:
        result["vendor_resolved"] = vendor_resolved
    return result

def _get_work_log_stats(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 통계 (업체 별칭 지원)"""
    conditions = []
    params = []
    
    if args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    vendor_query = args.get("vendor")
    vendor_resolved = None
    if args.get("vendor"):
        vendor_search = args['vendor']
        # 별칭 테이블에서 실제 업체명 찾기
        with get_connection() as con:
            alias_rows = con.execute(
                "SELECT DISTINCT vendor FROM aliases WHERE alias LIKE ? OR vendor LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
            vendor_rows = con.execute(
                "SELECT vendor FROM vendors WHERE vendor LIKE ? OR name LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
        if alias_rows:
            vendor_resolved = alias_rows[0][0]
        elif vendor_rows:
            vendor_resolved = vendor_rows[0][0]
        all_vendors = set([r[0] for r in alias_rows if r[0]] + [r[0] for r in vendor_rows if r[0]])
        all_vendors.add(vendor_search)
        
        if len(all_vendors) == 1:
            conditions.append("업체명 LIKE ?")
            params.append(f"%{list(all_vendors)[0]}%")
        else:
            vendor_conditions = " OR ".join(["업체명 LIKE ?" for _ in all_vendors])
            conditions.append(f"({vendor_conditions})")
            params.extend([f"%{v}%" for v in all_vendors])
    if args.get("work_type"):
        conditions.append("분류 LIKE ?")
        params.append(f"%{args['work_type']}%")
    if args.get("worker"):
        conditions.append("작성자 LIKE ?")
        params.append(f"%{args['worker']}%")
    if args.get("remark"):
        conditions.append("비고1 LIKE ?")
        params.append(f"%{args['remark']}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_connection() as con:
        # 총합
        total_row = con.execute(
            f"SELECT COUNT(*), COALESCE(SUM(수량), 0), COALESCE(SUM(합계), 0) FROM work_log WHERE {where_clause}",
            params
        ).fetchone()
        
        # 업체별
        by_vendor = con.execute(
            f"""SELECT 업체명, COUNT(*), SUM(합계)
               FROM work_log WHERE {where_clause} AND 업체명 IS NOT NULL
               GROUP BY 업체명 ORDER BY SUM(합계) DESC LIMIT 10""",
            params
        ).fetchall()
        
        # 작업종류별
        by_work_type = con.execute(
            f"""SELECT 분류, COUNT(*), SUM(합계)
               FROM work_log WHERE {where_clause} AND 분류 IS NOT NULL
               GROUP BY 분류 ORDER BY COUNT(*) DESC LIMIT 10""",
            params
        ).fetchall()
    
    qty_sum = int(total_row[1] or 0)
    amount_sum = int(total_row[2] or 0)
    group_col = {"vendor": "업체명", "work_type": "분류", "worker": "작성자"}.get(str(args.get("group_by") or ""), "")
    groups = []
    if group_col:
        order_expr, sort_dir, group_limit = _stats_group_order(args, "수량", "합계")
        with get_connection() as con:
            grouped = con.execute(
                f"""SELECT {group_col}, COUNT(*), COALESCE(SUM(수량),0), COALESCE(SUM(합계),0)
                   FROM work_log WHERE {where_clause} AND {group_col} IS NOT NULL
                   GROUP BY {group_col} ORDER BY {order_expr} {sort_dir} LIMIT ?""",
                (*params, group_limit),
            ).fetchall()
        groups = [{"name": g[0], "count": g[1], "qty": g[2], "amount": g[3]} for g in grouped]
    result = {
        "success": True,
        "total_count": total_row[0] or 0,
        "count": total_row[0] or 0,
        "qty": qty_sum,
        "total": amount_sum,
        "total_amount": amount_sum,
        "groups": groups,
        "by_vendor": [{"vendor": v[0], "count": v[1], "amount": v[2]} for v in by_vendor],
        "by_work_type": [{"work_type": w[0], "count": w[1], "amount": w[2]} for w in by_work_type],
        "message": f"통계: {total_row[0]}건, 총 {amount_sum:,}원"
    }
    if vendor_query:
        result["vendor_query"] = vendor_query
    if vendor_resolved:
        result["vendor_resolved"] = vendor_resolved
    return result

def _lookup_work_price(args: Dict, user_id: str, user_name: str) -> Dict:
    try:
        return _lookup_price_from_history(args, user_id, user_name)
    except Exception:
        return {"success": False, "error": "조회 중 문제가 생겼어요."}

def _compare_periods(args: Dict, user_id: str, user_name: str) -> Dict:
    """기간 비교"""
    stats1 = _get_work_log_stats({
        "start_date": args.get("period1_start"),
        "end_date": args.get("period1_end")
    }, user_id, user_name)
    
    stats2 = _get_work_log_stats({
        "start_date": args.get("period2_start"),
        "end_date": args.get("period2_end")
    }, user_id, user_name)
    
    count_diff = stats2["total_count"] - stats1["total_count"]
    amount_diff = stats2["total_amount"] - stats1["total_amount"]
    count_rate = (count_diff / stats1["total_count"] * 100) if stats1["total_count"] > 0 else 0
    amount_rate = (amount_diff / stats1["total_amount"] * 100) if stats1["total_amount"] > 0 else 0
    
    return {
        "success": True,
        "period1": {
            "name": args.get("period1_name", "기간1"),
            "start": args.get("period1_start"),
            "end": args.get("period1_end"),
            "count": stats1["total_count"],
            "amount": stats1["total_amount"]
        },
        "period2": {
            "name": args.get("period2_name", "기간2"),
            "start": args.get("period2_start"),
            "end": args.get("period2_end"),
            "count": stats2["total_count"],
            "amount": stats2["total_amount"]
        },
        "diff": {
            "count": count_diff,
            "count_rate": count_rate,
            "amount": amount_diff,
            "amount_rate": amount_rate
        },
        "message": f"비교: 건수 {count_diff:+}건({count_rate:+.1f}%), 금액 {amount_diff:+,}원({amount_rate:+.1f}%)"
    }

def _update_work_log(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 수정"""
    log_id = args.get("log_id")
    update_recent = args.get("update_recent", False)
    
    with get_connection() as con:
        # 수정할 레코드 찾기
        if update_recent:
            row = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계
                   FROM work_log WHERE works_user_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (user_id,)
            ).fetchone()
        elif log_id:
            row = con.execute(
                "SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계 FROM work_log WHERE id = ? AND works_user_id = ?",
                (log_id, user_id)
            ).fetchone()
        else:
            # 조건으로 찾기
            conditions = ["works_user_id = ?"]
            params = [user_id]
            if args.get("vendor"):
                conditions.append("업체명 LIKE ?")
                params.append(f"%{args['vendor']}%")
            if args.get("date"):
                conditions.append("날짜 = ?")
                params.append(args["date"])
            if args.get("old_price"):
                conditions.append("합계 BETWEEN ? AND ?")
                params.extend([int(args["old_price"] * 0.9), int(args["old_price"] * 1.1)])
            
            row = con.execute(
                f"""SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계
                   FROM work_log WHERE {' AND '.join(conditions)}
                   ORDER BY id DESC LIMIT 1""",
                params
            ).fetchone()
        
        if not row:
            return {"success": False, "error": "수정할 작업일지를 찾지 못했습니다."}
        
        log_id = row[0]
        old_data = {
            "날짜": row[1], "업체명": row[2], "분류": row[3],
            "단가": row[4], "수량": row[5], "합계": row[6]
        }
        
        # 기존 비고 조회
        remark_row = con.execute("SELECT 비고1 FROM work_log WHERE id = ?", (log_id,)).fetchone()
        old_remark = remark_row[0] if remark_row and remark_row[0] else ""
        
        # 업데이트 필드 구성
        updates = []
        update_params = []
        
        if args.get("new_vendor"):
            updates.append("업체명 = ?")
            update_params.append(args["new_vendor"])
        if args.get("new_work_type"):
            updates.append("분류 = ?")
            update_params.append(args["new_work_type"])
        if args.get("new_unit_price"):
            updates.append("단가 = ?")
            update_params.append(args["new_unit_price"])
        if args.get("new_qty"):
            updates.append("수량 = ?")
            update_params.append(args["new_qty"])
        
        # 비고 수정 처리
        if args.get("new_remark"):
            new_remark = args["new_remark"]
            append_remark = args.get("append_remark", True)  # 기본값: 기존에 추가
            
            if append_remark and old_remark:
                # 기존 비고에 추가
                final_remark = f"{old_remark}, {new_remark}"
            else:
                # 교체
                final_remark = new_remark
            
            updates.append("비고1 = ?")
            update_params.append(final_remark)
        
        if not updates:
            return {"success": False, "error": "수정할 내용이 없습니다."}
        
        # 합계 재계산
        new_단가 = args.get("new_unit_price") or old_data["단가"]
        new_수량 = args.get("new_qty") or old_data["수량"]
        updates.append("합계 = ?")
        update_params.append(new_단가 * new_수량)
        
        update_params.append(log_id)
        con.execute(f"UPDATE work_log SET {', '.join(updates)} WHERE id = ?", update_params)
        con.commit()
        
        # 수정된 데이터 조회
        new_row = con.execute(
            "SELECT 날짜, 업체명, 분류, 단가, 수량, 합계 FROM work_log WHERE id = ?",
            (log_id,)
        ).fetchone()
        
        new_data = {
            "날짜": new_row[0], "업체명": new_row[1], "분류": new_row[2],
            "단가": new_row[3], "수량": new_row[4], "합계": new_row[5]
        }
    
    # 이력 기록
    _log_work_history(log_id, "update", new_data, user_name, "수정", user_id)
    
    # 응답 메시지 구성
    message = f"수정완료! {new_data['업체명']} {new_data['분류']} {new_data['합계']:,}원"
    if args.get("new_remark"):
        message += f" (비고: {args['new_remark']})"
    
    return {
        "success": True,
        "log_id": log_id,
        "old_data": old_data,
        "new_data": new_data,
        "remark_updated": args.get("new_remark"),
        "message": message
    }

def _bulk_update_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """일괄 수정"""
    new_unit_price = args.get("new_unit_price")
    if not new_unit_price:
        return {"success": False, "error": "새 단가를 지정해주세요."}
    
    conditions = ["works_user_id = ?"]
    params = [user_id]
    
    if args.get("vendor"):
        conditions.append("업체명 LIKE ?")
        params.append(f"%{args['vendor']}%")
    if args.get("work_type"):
        conditions.append("분류 LIKE ?")
        params.append(f"%{args['work_type']}%")
    if args.get("date"):
        conditions.append("날짜 = ?")
        params.append(args["date"])
    if args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    
    with get_connection() as con:
        cursor = con.execute(
            f"""UPDATE work_log 
               SET 단가 = ?, 합계 = 수량 * ?
               WHERE {' AND '.join(conditions)}""",
            [new_unit_price, new_unit_price] + params
        )
        con.commit()
        updated_count = cursor.rowcount
    
    return {
        "success": True,
        "updated_count": updated_count,
        "new_unit_price": new_unit_price,
        "message": f"{updated_count}건 일괄 수정완료! 단가: {new_unit_price:,}원"
    }

def _copy_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 복사"""
    target_date = args.get("target_date") or datetime.now().strftime("%Y-%m-%d")
    
    conditions = []
    params = []
    
    if args.get("source_date"):
        conditions.append("날짜 = ?")
        params.append(args["source_date"])
    if args.get("source_start_date") and args.get("source_end_date"):
        conditions.append("날짜 >= ? AND 날짜 <= ?")
        params.extend([args["source_start_date"], args["source_end_date"]])
    if args.get("vendor"):
        conditions.append("업체명 LIKE ?")
        params.append(f"%{args['vendor']}%")
    
    if not conditions:
        return {"success": False, "error": "복사할 원본 조건을 지정해주세요."}
    
    new_ids = []
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        rows = con.execute(
            f"""SELECT 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 출처, works_user_id
               FROM work_log WHERE {' AND '.join(conditions)}""",
            params
        ).fetchall()
        
        for row in rows:
            cursor = con.execute(
                """INSERT INTO work_log (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (target_date, row[0], row[1], row[2], row[3], row[4],
                 f"{row[5] or ''} [복사됨]", row[6], 저장시간, "bot_copy", row[8])
            )
            new_ids.append(cursor.lastrowid)
        
        con.commit()
    
    return {
        "success": True,
        "copied_count": len(new_ids),
        "target_date": target_date,
        "new_ids": new_ids,
        "message": f"{len(new_ids)}건 복사완료! 대상 날짜: {target_date}"
    }

def _add_memo(args: Dict, user_id: str, user_name: str) -> Dict:
    """메모 추가"""
    memo = args.get("memo", "")
    if not memo:
        return {"success": False, "error": "메모 내용을 입력해주세요."}
    
    log_id = args.get("log_id")
    add_to_recent = args.get("add_to_recent", False)
    
    with get_connection() as con:
        if add_to_recent or not log_id:
            row = con.execute(
                "SELECT id FROM work_log WHERE works_user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            if row:
                log_id = row[0]
        else:
            row = con.execute(
                "SELECT id FROM work_log WHERE id = ? AND works_user_id = ?",
                (log_id, user_id),
            ).fetchone()
            if not row:
                return {"success": False, "error": "메모를 추가할 작업일지를 찾지 못했습니다."}
            log_id = row[0]
        
        if not log_id:
            return {"success": False, "error": "메모를 추가할 작업일지를 찾지 못했습니다."}
        
        existing = con.execute("SELECT 비고1 FROM work_log WHERE id = ?", (log_id,)).fetchone()
        if existing:
            old_memo = existing[0] or ""
            new_memo = f"{old_memo} [{memo}]" if old_memo else memo
            con.execute("UPDATE work_log SET 비고1 = ? WHERE id = ?", (new_memo, log_id))
            con.commit()
    
    return {
        "success": True,
        "log_id": log_id,
        "memo": memo,
        "message": f"메모 추가완료! [{memo}]"
    }

def _lookup_price_from_history(args: Dict, user_id: str, user_name: str) -> Dict:
    """기존 작업일지에서 업체명+작업종류 조합의 가격 조회
    
    조회 우선순위:
    1. 해당 업체 + 해당 작업종류 (정확히 일치)
    2. 해당 작업종류만 (모든 업체에서 검색)
    """
    vendor = args.get("vendor", "")
    work_type = args.get("work_type", "")
    
    if not work_type:
        return {"success": False, "error": "작업종류가 필요합니다."}
    
    with get_connection() as con:
        resolved_vendor = vendor
        
        if vendor:
            # 공백 제거한 버전도 준비
            vendor_normalized = vendor.replace(" ", "").replace("　", "")
            
            # 1. 별칭 테이블에서 실제 업체명 찾기
            vendor_check = con.execute(
                """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
                   UNION
                   SELECT vendor FROM aliases WHERE LOWER(alias) = LOWER(?)""",
                (vendor, vendor)
            ).fetchone()
            
            if not vendor_check:
                vendor_check = con.execute(
                    """SELECT vendor FROM vendors 
                       WHERE REPLACE(LOWER(vendor), ' ', '') = LOWER(?)
                       UNION
                       SELECT vendor FROM aliases 
                       WHERE REPLACE(LOWER(alias), ' ', '') = LOWER(?)""",
                    (vendor_normalized, vendor_normalized)
                ).fetchone()
            
            if vendor_check:
                resolved_vendor = vendor_check[0]
            
            # 2. 해당 업체+작업종류 조합의 최근 가격 조회
            price_rows = con.execute(
                """SELECT 단가, 합계, 수량, 날짜, COUNT(*) as usage_count, 업체명
                   FROM work_log 
                   WHERE 업체명 = ? AND 분류 LIKE ?
                   GROUP BY 단가
                   ORDER BY MAX(날짜) DESC, usage_count DESC
                   LIMIT 5""",
                (resolved_vendor, f"%{work_type}%")
            ).fetchall()
            
            if price_rows:
                # 정확히 일치하는 경우
                prices = [
                    {
                        "unit_price": r[0],
                        "total": r[1],
                        "qty": r[2],
                        "last_date": r[3],
                        "usage_count": r[4],
                        "vendor": r[5]
                    }
                    for r in price_rows if r[0]
                ]
                
                if prices:
                    most_recent = prices[0]
                    return {
                        "success": True,
                        "found": True,
                        "exact_match": True,
                        "vendor": resolved_vendor,
                        "work_type": work_type,
                        "prices": prices,
                        "most_recent_price": most_recent["unit_price"],
                        "most_recent_date": most_recent["last_date"],
                        "usage_count": most_recent["usage_count"],
                        "message": f"'{resolved_vendor} {work_type}'의 최근 단가: {most_recent['unit_price']:,}원 ({most_recent['usage_count']}회 사용)"
                    }
        
        # 3. 작업종류만으로 검색 (모든 업체에서)
        # 가장 많이 사용된 단가를 찾음
        price_rows = con.execute(
            """SELECT 단가, 합계, 수량, MAX(날짜) as last_date, COUNT(*) as usage_count, 업체명
               FROM work_log 
               WHERE 분류 LIKE ? AND 단가 IS NOT NULL AND 단가 > 0
               GROUP BY 단가
               ORDER BY usage_count DESC, last_date DESC
               LIMIT 5""",
            (f"%{work_type}%",)
        ).fetchall()
        
        if not price_rows:
            return {
                "success": False,
                "found": False,
                "vendor": resolved_vendor,
                "work_type": work_type,
                "message": f"'{work_type}' 작업에 대한 이전 가격 기록이 없습니다."
            }
        
        # 작업종류만 일치하는 경우 - 가장 많이 사용된 단가 제안
        prices = [
            {
                "unit_price": r[0],
                "total": r[1],
                "qty": r[2],
                "last_date": r[3],
                "usage_count": r[4],
                "sample_vendor": r[5]
            }
            for r in price_rows if r[0]
        ]
        
        if not prices:
            return {
                "success": False,
                "found": False,
                "vendor": resolved_vendor,
                "work_type": work_type,
                "message": f"'{work_type}' 작업에 대한 이전 가격 기록이 없습니다."
            }
        
        most_used = prices[0]
        sample_vendor = most_used.get("sample_vendor", "")
        
        return {
            "success": True,
            "found": True,
            "exact_match": False,
            "vendor": resolved_vendor,
            "work_type": work_type,
            "prices": prices,
            "most_recent_price": most_used["unit_price"],
            "most_recent_date": most_used["last_date"],
            "usage_count": most_used["usage_count"],
            "sample_vendor": sample_vendor,
            "message": f"'{work_type}' 작업의 최근 단가: {most_used['unit_price']:,}원 ({most_used['usage_count']}회 사용, 예: {sample_vendor})"
        }

def _log_work_history(
    log_id: int,
    action: str,
    log_data: Dict,
    변경자: str = None,
    변경사유: str = None,
    works_user_id: str = None
):
    """작업일지 변경 이력 기록"""
    try:
        with get_connection() as con:
            con.execute(
                """INSERT INTO work_log_history 
                   (log_id, action, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 변경자, 변경시간, 변경사유, works_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    log_id, action,
                    log_data.get("날짜") or log_data.get("date"),
                    log_data.get("업체명") or log_data.get("vendor"),
                    log_data.get("분류") or log_data.get("work_type"),
                    log_data.get("단가") or log_data.get("unit_price"),
                    log_data.get("수량") or log_data.get("qty"),
                    log_data.get("합계") or (log_data.get("수량", 1) * log_data.get("단가", 0)),
                    log_data.get("작성자"),
                    변경자,
                    datetime.now().isoformat(),
                    변경사유,
                    works_user_id
                )
            )
            con.commit()
    except Exception as e:
        print(f"Warning: Could not log work history: {e}")
