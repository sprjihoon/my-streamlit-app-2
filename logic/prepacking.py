"""
logic/prepacking.py - 하위호환 re-export
────────────────────────────────────────
기존 import 경로를 유지하기 위한 파일.
실제 로직은 아래 모듈에 분리되어 있습니다:

- prepacking_parse.py      : SKU 파싱, 컬럼 감지, 배송건 그룹핑
- prepacking_analysis.py   : 조합 분석, 예측
- prepacking_production.py : 제작 CRUD, 일일 지시, 정확도, 효율
- prepacking_settings.py   : 설정, 공급처 목록, 로케이션
"""

# ── 파싱 ──
from .prepacking_parse import (  # noqa: F401
    parse_admin_product_qty,
    build_combo_key,
    build_combo_detail,
    detect_columns as _detect_columns,
    find_invoice_col as _find_invoice_col,
    extract_items_from_row as _extract_items_from_row,
    group_shipments as _group_shipments,
    load_vendor_df as _load_vendor_df,
    _safe_str,
)

# ── 분석 & 예측 ──
from .prepacking_analysis import (  # noqa: F401
    analyze_combinations,
    predict_for_date,
)

# ── 제작 관리 ──
from .prepacking_production import (  # noqa: F401
    save_predictions,
    get_predictions,
    create_production,
    use_production,
    update_production_status,
    update_production_location,
    get_active_productions,
    get_productions_by_date,
    generate_daily_instructions,
    update_actual_qty,
    get_accuracy_history,
    get_efficiency_stats,
)

# ── 설정 ──
from .prepacking_settings import (  # noqa: F401
    get_settings,
    save_settings,
    get_all_settings,
    suggest_locations,
    get_vendors_with_data,
)
