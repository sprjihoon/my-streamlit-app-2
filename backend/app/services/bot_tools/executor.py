"""Dispatch a tool name to the same handler as the original module."""
from typing import Any, Dict

from .common import TRUSTED_EXCEL_UPLOAD
from .history import _get_undo_history, _undo_action
from .invoice import _get_invoice_stats
from .leave import (
    _apply_leave,
    _approve_leave,
    _cancel_leave,
    _check_leave,
    _get_pending_approvals,
    _reject_leave,
)
from .registry import JOURNAL_TOOL_NAMES, QUERY_TOOL_NAMES, WRITE_TOOL_NAMES
from .repair import (
    _get_repair_log_stats,
    _lookup_repair_barcode_tool,
    _lookup_repair_catalog,
    _lookup_repair_price,
    _save_repair_log,
    _search_repair_logs,
)
from .validation import validate_tool_args
from .vendors import (
    _lookup_rate_tables,
    _lookup_storage,
    _lookup_vendor_charges_tool,
    _lookup_vendors,
)
from .web import _get_dashboard_url, _get_help, _web_search
from .work_log import (
    _add_memo,
    _bulk_update_work_logs,
    _compare_periods,
    _copy_work_logs,
    _delete_work_log,
    _get_work_log_stats,
    _lookup_price_from_history,
    _lookup_work_price,
    _save_multiple_work_logs,
    _save_work_log,
    _search_work_logs,
    _update_work_log,
)

def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: str,
    user_name: str = None,
    mode: str = None,
    trusted_source: str = None,
) -> Dict[str, Any]:
    """
    도구를 실행하고 결과를 반환합니다.
    GPT/외부 호출은 mode가 없거나 잘못되면 쓰기를 거부한다.
    엑셀 업로드만 trusted_source='excel_upload'로 저장을 허용한다.
    """
    if trusted_source == TRUSTED_EXCEL_UPLOAD:
        if tool_name != "save_work_log":
            return {"success": False, "error": "엑셀 업로드는 작업일지 저장만 허용합니다."}
    else:
        if tool_name in WRITE_TOOL_NAMES and mode != "journal":
            if mode == "query":
                return {"success": False, "error": "조회모드에서는 저장·수정·삭제를 할 수 없습니다."}
            if mode == "idle":
                return {"success": False, "error": "기본상태에서는 업무 도구를 실행할 수 없습니다. 모드를 선택해주세요."}
            if mode == "repair":
                return {"success": False, "error": "수선모드에서는 GPT 업무 도구를 실행하지 않습니다."}
            return {"success": False, "error": "모드가 없거나 올바르지 않아 쓰기를 거부합니다."}
        if mode == "idle":
            return {"success": False, "error": "기본상태에서는 업무 도구를 실행할 수 없습니다. 모드를 선택해주세요."}
        if mode == "query" and (tool_name in WRITE_TOOL_NAMES or tool_name not in QUERY_TOOL_NAMES):
            return {"success": False, "error": "조회모드에서는 저장·수정·삭제를 할 수 없습니다."}
        if mode == "journal" and tool_name not in JOURNAL_TOOL_NAMES:
            return {"success": False, "error": "일지모드에서 사용할 수 없는 도구입니다."}
        if mode == "repair":
            return {"success": False, "error": "수선모드에서는 GPT 업무 도구를 실행하지 않습니다."}

    cleaned, err = validate_tool_args(tool_name, arguments)
    if err:
        return {"success": False, "error": err}
    args = cleaned

    tool_functions = {
        "save_work_log": _save_work_log,
        "save_multiple_work_logs": _save_multiple_work_logs,
        "delete_work_log": _delete_work_log,
        "search_work_logs": _search_work_logs,
        "get_work_log_stats": _get_work_log_stats,
        "search_repair_logs": _search_repair_logs,
        "get_repair_log_stats": _get_repair_log_stats,
        "lookup_work_price": _lookup_work_price,
        "compare_periods": _compare_periods,
        "update_work_log": _update_work_log,
        "bulk_update_work_logs": _bulk_update_work_logs,
        "copy_work_logs": _copy_work_logs,
        "add_memo": _add_memo,
        "get_undo_history": _get_undo_history,
        "undo_action": _undo_action,
        "get_dashboard_url": _get_dashboard_url,
        "get_invoice_stats": _get_invoice_stats,
        "web_search": _web_search,
        "get_help": _get_help,
        "lookup_price_from_history": _lookup_price_from_history,
        "save_repair_log": _save_repair_log,
        "lookup_repair_price": _lookup_repair_price,
        "lookup_repair_barcode": _lookup_repair_barcode_tool,
        "check_leave": _check_leave,
        "apply_leave": _apply_leave,
        "cancel_leave": _cancel_leave,
        "approve_leave": _approve_leave,
        "reject_leave": _reject_leave,
        "get_pending_approvals": _get_pending_approvals,
        "lookup_vendors": _lookup_vendors,
        "lookup_rate_tables": _lookup_rate_tables,
        "lookup_storage": _lookup_storage,
        "lookup_vendor_charges": _lookup_vendor_charges_tool,
        "lookup_repair_catalog": _lookup_repair_catalog,
    }
    
    if tool_name not in tool_functions:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    try:
        return tool_functions[tool_name](args, user_id, user_name)
    except Exception as e:
        return {"success": False, "error": str(e)}
