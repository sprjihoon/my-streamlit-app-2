"""Bot tools package. Public names stay importable from backend.app.services.bot_tools."""
from .common import (
    QUERY_ALL_TABLE_LIMIT,
    QUERY_DEFAULT_LIMIT,
    QUERY_MAX_LIMIT,
    TRUSTED_EXCEL_UPLOAD,
    _SECRET_KEY_RE,
    _clamp_limit,
    _clamp_offset,
    _fetch_allowed,
    _sql_ident,
    _stats_group_order,
    _strip_secrets,
    get_db_context_for_ai,
    logger,
)
from .executor import execute_tool
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
from .registry import (
    INACTIVE_TOOL_NAMES,
    JOURNAL_TOOL_NAMES,
    QUERY_TOOL_NAMES,
    TOOLS,
    WRITE_TOOL_NAMES,
    _TOOL_BY_NAME,
    get_tools_for_mode,
)
from .repair import (
    _DATE_RE,
    _REPAIR_GROUP_COLS,
    _get_repair_log_stats,
    _lookup_repair_barcode_tool,
    _lookup_repair_catalog,
    _lookup_repair_price,
    _safe_date,
    _save_repair_log,
    _search_repair_logs,
)
from .validation import (
    _apply_schema_guard,
    _coerce_arg,
    allowed_arg_keys,
    validate_tool_args,
)
from .vendors import (
    _RATE_TABLE_COLS,
    _RATE_TABLE_ORDER,
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
    _log_work_history,
    _lookup_price_from_history,
    _lookup_work_price,
    _save_multiple_work_logs,
    _save_work_log,
    _search_work_logs,
    _update_work_log,
)

# Submodule imports bind names on this package. Drop them so the public
# surface stays the original function and constant names.
for _submodule in (
    "common",
    "executor",
    "history",
    "invoice",
    "leave",
    "registry",
    "repair",
    "validation",
    "vendors",
    "web",
    "work_log",
):
    globals().pop(_submodule, None)
del _submodule
