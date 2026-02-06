"""
봇 Function Calling 도구 정의
───────────────────────────────────────
OpenAI Function Calling을 위한 도구(tools) 스키마와 실행 함수를 정의합니다.
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from logic.db import get_connection
from backend.app.api.logs import add_log


# ═══════════════════════════════════════════════════════════════════
# 도구(Tools) 스키마 정의 - OpenAI Function Calling 형식
# ═══════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_work_log",
            "description": "작업일지를 저장합니다. 업체명, 작업종류, 단가는 필수입니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명 (예: 틸리언, 나블리)"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업 종류 (예: 1톤하차, 양품화, 입고)"
                    },
                    "unit_price": {
                        "type": "integer",
                        "description": "단가 (원 단위, 예: 30000)"
                    },
                    "qty": {
                        "type": "integer",
                        "description": "수량 (기본값: 1)",
                        "default": 1
                    },
                    "date": {
                        "type": "string",
                        "description": "작업일 (YYYY-MM-DD 형식, 기본값: 오늘)"
                    },
                    "remark": {
                        "type": "string",
                        "description": "비고/메모"
                    }
                },
                "required": ["vendor", "work_type", "unit_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_multiple_work_logs",
            "description": "여러 작업일지를 한 번에 저장합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "description": "저장할 작업일지 목록",
                        "items": {
                            "type": "object",
                            "properties": {
                                "vendor": {"type": "string"},
                                "work_type": {"type": "string"},
                                "unit_price": {"type": "integer"},
                                "qty": {"type": "integer", "default": 1},
                                "date": {"type": "string"},
                                "remark": {"type": "string"}
                            },
                            "required": ["vendor", "work_type", "unit_price"]
                        }
                    }
                },
                "required": ["entries"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_work_log",
            "description": "작업일지를 삭제합니다. ID로 삭제하거나, 조건으로 최근 1건을 삭제합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {
                        "type": "integer",
                        "description": "삭제할 작업일지 ID (알고 있는 경우)"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "업체명 조건"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업종류 조건"
                    },
                    "date": {
                        "type": "string",
                        "description": "날짜 조건 (YYYY-MM-DD)"
                    },
                    "price": {
                        "type": "integer",
                        "description": "금액 조건 (합계)"
                    },
                    "delete_recent": {
                        "type": "boolean",
                        "description": "사용자의 가장 최근 작업일지 삭제 (true면 다른 조건 무시)",
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_work_logs",
            "description": "조건에 맞는 작업일지를 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명 (부분 일치)"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업종류 (부분 일치)"
                    },
                    "date": {
                        "type": "string",
                        "description": "특정 날짜 (YYYY-MM-DD)"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "시작 날짜 (YYYY-MM-DD)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료 날짜 (YYYY-MM-DD)"
                    },
                    "price": {
                        "type": "integer",
                        "description": "금액 (±10% 범위로 검색)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "최대 결과 수 (기본: 20)",
                        "default": 20
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_log_stats",
            "description": "작업일지 통계를 조회합니다 (총 건수, 총액, 업체별, 작업별 통계).",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "시작 날짜 (YYYY-MM-DD)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료 날짜 (YYYY-MM-DD)"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "특정 업체만 조회"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "두 기간의 작업일지 통계를 비교합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period1_start": {
                        "type": "string",
                        "description": "기간1 시작일 (YYYY-MM-DD)"
                    },
                    "period1_end": {
                        "type": "string",
                        "description": "기간1 종료일 (YYYY-MM-DD)"
                    },
                    "period1_name": {
                        "type": "string",
                        "description": "기간1 이름 (예: '지난주')"
                    },
                    "period2_start": {
                        "type": "string",
                        "description": "기간2 시작일 (YYYY-MM-DD)"
                    },
                    "period2_end": {
                        "type": "string",
                        "description": "기간2 종료일 (YYYY-MM-DD)"
                    },
                    "period2_name": {
                        "type": "string",
                        "description": "기간2 이름 (예: '이번주')"
                    }
                },
                "required": ["period1_start", "period1_end", "period2_start", "period2_end"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_log",
            "description": "작업일지를 수정합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {
                        "type": "integer",
                        "description": "수정할 작업일지 ID"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "업체명 조건 (ID 모를 때)"
                    },
                    "date": {
                        "type": "string",
                        "description": "날짜 조건 (ID 모를 때)"
                    },
                    "old_price": {
                        "type": "integer",
                        "description": "기존 금액 조건 (ID 모를 때)"
                    },
                    "new_vendor": {
                        "type": "string",
                        "description": "새 업체명"
                    },
                    "new_work_type": {
                        "type": "string",
                        "description": "새 작업종류"
                    },
                    "new_unit_price": {
                        "type": "integer",
                        "description": "새 단가"
                    },
                    "new_qty": {
                        "type": "integer",
                        "description": "새 수량"
                    },
                    "update_recent": {
                        "type": "boolean",
                        "description": "사용자의 가장 최근 작업일지 수정 (true면 조건 무시)",
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_update_work_logs",
            "description": "조건에 맞는 여러 작업일지를 일괄 수정합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명 조건"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업종류 조건"
                    },
                    "date": {
                        "type": "string",
                        "description": "날짜 조건"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "시작 날짜"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료 날짜"
                    },
                    "new_unit_price": {
                        "type": "integer",
                        "description": "새 단가"
                    }
                },
                "required": ["new_unit_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_work_logs",
            "description": "작업일지를 다른 날짜로 복사합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_date": {
                        "type": "string",
                        "description": "복사할 원본 날짜"
                    },
                    "source_start_date": {
                        "type": "string",
                        "description": "복사할 기간 시작일"
                    },
                    "source_end_date": {
                        "type": "string",
                        "description": "복사할 기간 종료일"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "특정 업체만 복사"
                    },
                    "target_date": {
                        "type": "string",
                        "description": "복사 대상 날짜 (기본: 오늘)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_memo",
            "description": "작업일지에 메모/비고를 추가합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {
                        "type": "integer",
                        "description": "작업일지 ID"
                    },
                    "memo": {
                        "type": "string",
                        "description": "추가할 메모 내용"
                    },
                    "add_to_recent": {
                        "type": "boolean",
                        "description": "가장 최근 작업일지에 추가",
                        "default": False
                    }
                },
                "required": ["memo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_undo_history",
            "description": "되돌리기 가능한 변경 이력을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "조회할 이력 수 (기본: 5)",
                        "default": 5
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "undo_action",
            "description": "특정 변경을 되돌립니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_id": {
                        "type": "integer",
                        "description": "되돌릴 이력 ID"
                    },
                    "history_index": {
                        "type": "integer",
                        "description": "되돌릴 이력 인덱스 (1부터 시작, 사용자가 '1번' 선택 시)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_url",
            "description": "대시보드/웹페이지 URL을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "웹에서 정보를 검색합니다 (외부 정보 조회용).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색어"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_help",
            "description": "사용법/도움말을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "도움말 주제 (입력, 조회, 수정, 분석, 고급, 전체)",
                        "enum": ["입력", "조회", "수정", "분석", "고급", "전체"]
                    }
                }
            }
        }
    }
]


# ═══════════════════════════════════════════════════════════════════
# 도구 실행 함수들
# ═══════════════════════════════════════════════════════════════════

def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: str,
    user_name: str = None
) -> Dict[str, Any]:
    """
    도구를 실행하고 결과를 반환합니다.
    
    Args:
        tool_name: 실행할 도구 이름
        arguments: 도구 인자
        user_id: 사용자 ID
        user_name: 사용자 이름
    
    Returns:
        실행 결과 딕셔너리
    """
    tool_functions = {
        "save_work_log": _save_work_log,
        "save_multiple_work_logs": _save_multiple_work_logs,
        "delete_work_log": _delete_work_log,
        "search_work_logs": _search_work_logs,
        "get_work_log_stats": _get_work_log_stats,
        "compare_periods": _compare_periods,
        "update_work_log": _update_work_log,
        "bulk_update_work_logs": _bulk_update_work_logs,
        "copy_work_logs": _copy_work_logs,
        "add_memo": _add_memo,
        "get_undo_history": _get_undo_history,
        "undo_action": _undo_action,
        "get_dashboard_url": _get_dashboard_url,
        "web_search": _web_search,
        "get_help": _get_help,
    }
    
    if tool_name not in tool_functions:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    try:
        return tool_functions[tool_name](arguments, user_id, user_name)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────
# 개별 도구 실행 함수
# ─────────────────────────────────────

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
    """작업일지 삭제"""
    log_id = args.get("log_id")
    delete_recent = args.get("delete_recent", False)
    
    with get_connection() as con:
        # 삭제할 레코드 찾기
        if delete_recent:
            row = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자
                   FROM work_log WHERE works_user_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (user_id,)
            ).fetchone()
        elif log_id:
            row = con.execute(
                "SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자 FROM work_log WHERE id = ?",
                (log_id,)
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
                f"""SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자
                   FROM work_log WHERE {' AND '.join(conditions)}
                   ORDER BY id DESC LIMIT 1""",
                params
            ).fetchone()
        
        if not row:
            return {"success": False, "error": "삭제할 작업일지를 찾지 못했습니다."}
        
        log_id = row[0]
        log_data = {
            "id": row[0], "날짜": row[1], "업체명": row[2], "분류": row[3],
            "단가": row[4], "수량": row[5], "합계": row[6], "작성자": row[7]
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
    
    return {
        "success": True,
        "deleted": log_data,
        "message": f"삭제완료! {log_data['업체명']} {log_data['분류']} {log_data['합계']:,}원"
    }


def _search_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 검색"""
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
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit = args.get("limit", 20)
    
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
    
    return {
        "success": True,
        "count": len(logs),
        "total_amount": total_amount,
        "logs": logs,
        "message": f"검색결과: {len(logs)}건, 총 {total_amount:,}원"
    }


def _get_work_log_stats(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 통계"""
    conditions = []
    params = []
    
    if args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    if args.get("vendor"):
        conditions.append("업체명 LIKE ?")
        params.append(f"%{args['vendor']}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_connection() as con:
        # 총합
        total_row = con.execute(
            f"SELECT COUNT(*), COALESCE(SUM(합계), 0) FROM work_log WHERE {where_clause}",
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
    
    return {
        "success": True,
        "total_count": total_row[0] or 0,
        "total_amount": total_row[1] or 0,
        "by_vendor": [{"vendor": v[0], "count": v[1], "amount": v[2]} for v in by_vendor],
        "by_work_type": [{"work_type": w[0], "count": w[1], "amount": w[2]} for w in by_work_type],
        "message": f"통계: {total_row[0]}건, 총 {total_row[1]:,}원"
    }


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
                "SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계 FROM work_log WHERE id = ?",
                (log_id,)
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
    
    return {
        "success": True,
        "log_id": log_id,
        "old_data": old_data,
        "new_data": new_data,
        "message": f"수정완료! {new_data['업체명']} {new_data['분류']} {new_data['합계']:,}원"
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


def _get_undo_history(args: Dict, user_id: str, user_name: str) -> Dict:
    """변경 이력 조회"""
    limit = args.get("limit", 5)
    
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, action, 업체명, 분류, 합계, 변경자, 변경시간, log_id
               FROM work_log_history
               WHERE works_user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
    
    history = []
    for i, r in enumerate(rows, 1):
        history.append({
            "index": i,
            "id": r[0],
            "action": r[1],
            "vendor": r[2],
            "work_type": r[3],
            "amount": r[4],
            "user": r[5],
            "time": r[6],
            "log_id": r[7]
        })
    
    return {
        "success": True,
        "history": history,
        "message": f"최근 변경 이력 {len(history)}건"
    }


def _undo_action(args: Dict, user_id: str, user_name: str) -> Dict:
    """되돌리기 실행"""
    history_id = args.get("history_id")
    history_index = args.get("history_index")
    
    # 이력 조회
    history_result = _get_undo_history({"limit": 10}, user_id, user_name)
    history = history_result.get("history", [])
    
    if not history:
        return {"success": False, "error": "되돌릴 이력이 없습니다."}
    
    # 대상 찾기
    target = None
    if history_index:
        for h in history:
            if h["index"] == history_index:
                target = h
                break
    elif history_id:
        for h in history:
            if h["id"] == history_id:
                target = h
                break
    
    if not target:
        return {"success": False, "error": "되돌릴 이력을 찾지 못했습니다."}
    
    action = target["action"]
    log_id = target["log_id"]
    
    if action == "create":
        # 생성된 것 삭제
        with get_connection() as con:
            con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
            con.commit()
        return {"success": True, "message": "되돌리기 완료! (추가된 데이터 삭제됨)"}
    
    elif action == "delete":
        # 삭제된 것 복구
        data = {
            "vendor": target["vendor"],
            "work_type": target["work_type"],
            "unit_price": target["amount"],  # 합계를 단가로 사용 (수량 1 가정)
            "qty": 1,
            "remark": "[복구됨]"
        }
        result = _save_work_log(data, user_id, user_name)
        return {"success": True, "message": "되돌리기 완료! (삭제된 데이터 복구됨)", "new_id": result.get("record_id")}
    
    return {"success": False, "error": "이 항목은 되돌릴 수 없습니다."}


def _get_dashboard_url(args: Dict, user_id: str, user_name: str) -> Dict:
    """대시보드 URL"""
    import os
    base_url = os.getenv("FRONTEND_URL", "https://my-streamlit-app-2.vercel.app")
    
    return {
        "success": True,
        "urls": {
            "main": base_url,
            "work_log": f"{base_url}/work-log"
        },
        "message": f"대시보드: {base_url}"
    }


def _web_search(args: Dict, user_id: str, user_name: str) -> Dict:
    """웹 검색"""
    query = args.get("query", "")
    if not query:
        return {"success": False, "error": "검색어를 입력해주세요."}
    
    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
        
        if not results:
            return {"success": False, "error": "검색 결과가 없습니다."}
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "message": f"'{query}' 검색결과 {len(results)}건"
        }
    except ImportError:
        return {"success": False, "error": "웹 검색 라이브러리가 설치되지 않았습니다."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_help(args: Dict, user_id: str, user_name: str) -> Dict:
    """도움말"""
    topic = args.get("topic", "전체")
    
    help_texts = {
        "입력": """📝 작업일지 입력
━━━━━━━━━━━━━━━━━━━━
✨ 자연스럽게 말하면 됩니다!

• "틸리언 1톤하차 3만원"
• "나블리 양품화 20개 800원"
• "어제 틸리언 하차 3만원"

💬 정보가 부족하면 물어봐요:
  "틸리언 하차" → "단가가 얼마예요?"
  "3만원" → 자동으로 완성!

💡 입력 후 '취소'로 바로 삭제 가능""",

        "조회": """🔍 조회/검색
━━━━━━━━━━━━━━━━━━━━
자연어로 물어보세요!

📅 기간 조회
• "오늘 작업 보여줘"
• "이번주 뭐했어?"
• "지난달 작업"

🏢 업체별 조회
• "틸리언 작업 보여줘"
• "이번주 나블리"

💰 금액 검색
• "3만원짜리 뭐있어?"
• "5만원 이상"

🔀 조합도 가능!
• "이번주 틸리언 뭐했어?"
• "어제 3만원짜리"

📥 결과에서 엑셀 다운로드 가능""",

        "수정": """✏️ 수정/삭제
━━━━━━━━━━━━━━━━━━━━
🗑️ 삭제
• "취소" / "삭제해줘"
• "방금꺼 지워줘"
• "틸리언 3만원 삭제해줘"

✏️ 수정
• "수정해줘"
• "5만원으로 바꿔줘"
• "업체명 틸리언으로 수정"

📦 일괄 수정
• "오늘 전부 5만원으로"
• "틸리언 단가 3만원으로"

🔄 되돌리기
• "되돌려줘" - 최근 변경 이력
• 번호 선택해서 복구""",

        "분석": """📊 통계/분석
━━━━━━━━━━━━━━━━━━━━
💰 합계
• "이번달 총 얼마?"
• "오늘 합계"

🏢 업체별
• "업체별 합계"
• "틸리언 이번달 얼마?"

📈 비교
• "지난주랑 이번주 비교"
• "저번달이랑 비교해줘"

🏆 순위
• "가장 많이 일한 업체"
• "이번달 Top 5"

🌐 대시보드
• "대시보드" → 웹 링크 제공""",

        "고급": """🔧 고급 기능
━━━━━━━━━━━━━━━━━━━━
📋 메모 추가
• "방금꺼에 메모 추가해줘"
• "급건이라고 메모"

📑 복사
• "어제꺼 오늘로 복사"
• "월요일 작업 복사해줘"

📊 엑셀 일괄 등록
• 엑셀 파일 보내면 자동 등록
• 필수 컬럼: 날짜, 업체명, 분류, 단가

🔍 웹 검색
• "OO업체 정보 찾아줘"

💬 일반 대화
• 아무 질문이나 OK!
• AI가 이해하고 답변해요""",

        "전체": """📚 작업일지봇 사용법
━━━━━━━━━━━━━━━━━━━━

💬 자연어로 편하게 말하세요!
정보가 부족하면 물어보고,
대화하듯 완성해갑니다.

━━━━━━━━━━━━━━━━━━━━
📝 입력 예시
  "틸리언 하차 3만원"
  "나블리 양품화 20개 800원"

🔍 조회 예시
  "오늘 작업 보여줘"
  "이번주 틸리언"

✏️ 수정 예시
  "취소" / "수정해줘"
  "5만원으로 바꿔"

📊 통계 예시
  "이번달 총 얼마?"
  "지난주랑 비교"

━━━━━━━━━━━━━━━━━━━━
📖 상세 도움말
  "도움말 입력"
  "도움말 조회"
  "도움말 수정"
  "도움말 분석"
  "도움말 고급"
━━━━━━━━━━━━━━━━━━━━"""
    }
    
    return {
        "success": True,
        "topic": topic,
        "help_text": help_texts.get(topic, help_texts["전체"]),
        "message": f"도움말: {topic}"
    }


# ─────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────

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


def get_db_context_for_ai() -> str:
    """AI에게 제공할 DB 컨텍스트 요약"""
    try:
        today = datetime.now()
        month_start = today.replace(day=1).strftime("%Y-%m-%d")
        month_end = today.strftime("%Y-%m-%d")
        
        with get_connection() as con:
            # 등록 업체
            vendors = [r[0] for r in con.execute(
                "SELECT vendor FROM vendors WHERE active != 'NO' OR active IS NULL ORDER BY vendor LIMIT 15"
            ).fetchall() if r[0]]
            
            # 자주 쓰는 작업종류
            work_types = [r[0] for r in con.execute(
                """SELECT 분류 FROM work_log WHERE 분류 IS NOT NULL
                   GROUP BY 분류 ORDER BY COUNT(*) DESC LIMIT 10"""
            ).fetchall() if r[0]]
            
            # 이번달 통계
            stats = con.execute(
                f"SELECT COUNT(*), COALESCE(SUM(합계), 0) FROM work_log WHERE 날짜 BETWEEN ? AND ?",
                (month_start, month_end)
            ).fetchone()
        
        context = f"""## 현재 DB 정보
- 등록 업체: {', '.join(vendors[:10])}{'...' if len(vendors) > 10 else ''}
- 자주 쓰는 작업: {', '.join(work_types)}
- 이번달: {stats[0]}건, {stats[1]:,}원 ({month_start} ~ {month_end})
- 오늘: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})"""
        
        return context
    except Exception as e:
        return f"## DB 정보 로드 오류: {e}"
