"""Leave tool handlers. Calls into the leave API the same way as before."""
from typing import Dict

def _check_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 현황 조회"""
    try:
        from backend.app.api.leave import bot_get_leave_summary
        year = args.get("year")
        result = bot_get_leave_summary(user_id)
        if "error" in result:
            return result
        if result.get("exempt"):
            return {"success": True, "message": f"{result['nickname']}님은 연차 관리 대상이 아닙니다."}

        summary = result
        lines = [
            f"📊 {summary['nickname']}님 연차 현황 ({summary['year']}년)",
            f"━━━━━━━━━━━━━━━━",
            f"📋 총 부여: {summary['total_hours']}시간 ({summary['total_days']}일)",
            f"✅ 사용:    {summary['used_hours']}시간 ({summary['used_days']}일)",
        ]
        if summary['pending_hours'] > 0:
            lines.append(f"⏳ 결재중:  {summary['pending_hours']}시간 ({summary['pending_days']}일)")
        color = "🔴" if summary['remaining_days'] < 0 else ("🟡" if summary['remaining_days'] < 3 else "🟢")
        lines.append(f"{color} 잔여:    {summary['remaining_hours']}시간 ({summary['remaining_days']}일)")
        lines.append(f"(입사일: {summary['join_date']})")
        return {"success": True, "message": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _apply_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 신청"""
    try:
        from backend.app.api.leave import bot_apply_leave
        leave_type = args.get("leave_type", "연차")
        start_date = args.get("start_date", "")
        end_date = args.get("end_date", start_date)
        reason = args.get("reason")

        if not start_date:
            return {"success": False, "error": "시작일을 알려주세요. (예: 7월 1일)"}

        result = bot_apply_leave(user_id, leave_type, start_date, end_date, reason)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}

def _cancel_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 취소"""
    try:
        from backend.app.api.leave import bot_cancel_leave
        request_id = args.get("request_id")
        if not request_id:
            return {"success": False, "error": "취소할 신청 번호(#ID)를 알려주세요."}
        return bot_cancel_leave(user_id, request_id)
    except Exception as e:
        return {"success": False, "error": str(e)}

def _approve_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 승인"""
    try:
        from backend.app.api.leave import bot_approve_leave
        request_id = args.get("request_id")
        if not request_id:
            return {"success": False, "error": "승인할 신청 번호(#ID)를 알려주세요."}
        comment = args.get("comment")
        return bot_approve_leave(user_id, request_id, comment)
    except Exception as e:
        return {"success": False, "error": str(e)}

def _reject_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 반려"""
    try:
        from backend.app.api.leave import bot_reject_leave
        request_id = args.get("request_id")
        if not request_id:
            return {"success": False, "error": "반려할 신청 번호(#ID)를 알려주세요."}
        comment = args.get("comment")
        return bot_reject_leave(user_id, request_id, comment)
    except Exception as e:
        return {"success": False, "error": str(e)}

def _get_pending_approvals(args: Dict, user_id: str, user_name: str) -> Dict:
    """결재 대기 목록"""
    try:
        from backend.app.api.leave import bot_get_pending_approvals
        result = bot_get_pending_approvals(user_id)
        if "error" in result:
            return result

        if result["count"] == 0:
            return {"success": True, "message": "✅ 결재 대기 중인 연차가 없습니다."}

        lines = [f"📋 결재 대기 {result['count']}건", "━━━━━━━━━━━━━━━━"]
        for item in result["items"]:
            lines.append(
                f"#{item['request_id']} {item['requester']}({item['department']}) "
                f"{item['start_date']}~{item['end_date']} {item['leave_type']} {item['days']}일\n"
                f"   사유: {item['reason']}"
            )
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append("승인: '승인 #번호' | 반려: '반려 #번호 사유'")
        return {"success": True, "message": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}
