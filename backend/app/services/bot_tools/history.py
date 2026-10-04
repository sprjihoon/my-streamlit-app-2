"""Undo history. Restores a work log through the original save handler."""
from typing import Dict

from logic.db import get_connection

from .work_log import _save_work_log

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
