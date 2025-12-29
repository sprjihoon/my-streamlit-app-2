"""
logic/ - 순수 비즈니스 로직 모듈
────────────────────────────────────
Streamlit 의존성을 제거한 순수 Python 함수들.
모든 계산/비즈니스 로직은 이 패키지에서 관리됩니다.

모듈 구조:
- db.py: DB 연결 및 스키마 관리
- clean.py: 송장번호 정규화 유틸
- invoice_calc.py: 인보이스 계산 로직
- fee_combined.py: 합포장 요금 계산
- fee_courier.py: 택배요금 구간별 계산
- fee_inbound.py: 입고검수 요금 계산
- fee_remote.py: 도서산간 요금 계산
- shipping_stats.py: 배송통계 필터
- upload.py: 파일 업로드 로직
- invoice_pdf.py: PDF 템플릿
"""

# DB 연결
from .db import (
    get_connection,
    ensure_column,
    ensure_tables,
    now_str,
    get_shipping_fee,
    df_from_sql,
    refresh_alias_vendor_cache,
)

# 정규화 유틸
from .clean import (
    TRACK_COLS,
    clean_invoice_id,
    normalize_tracking,
)

# 인보이스 계산
from .invoice_calc import (
    add_basic_shipping,
    add_courier_fee_by_zone,
    get_invoice_id,
    finalize_invoice,
    create_and_finalize_invoice,
    get_extra_unit,
    get_material_unit,
    add_flag_fee,
    add_barcode_fee,
    add_void_fee,
    add_ppbag_fee,
    add_video_out_fee,
    add_return_pickup_fee,
    add_return_courier_fee,
    add_video_ret_fee,
    add_box_fee_by_zone,
    add_worklog_items,
)

# 요금 계산
from .fee_combined import (
    add_combined_pack_fee,
    calculate_combined_pack_fee,
)
from .fee_courier import (
    calculate_courier_fee_by_zone,
    get_courier_fee_items,
)
from .fee_inbound import (
    add_inbound_inspection_fee,
    calculate_inbound_inspection_fee,
)
from .fee_remote import (
    add_remote_area_fee,
    calculate_remote_area_fee,
)

# 배송통계
from .shipping_stats import (
    shipping_stats,
    get_shipping_count,
)

# 업로드
from .upload import (
    ingest,
    list_uploads,
    delete_upload,
)

# PDF 생성
from .invoice_pdf import (
    InvoicePDF,
    create_invoice_pdf,
)

__all__ = [
    # db
    "get_connection",
    "ensure_column",
    "ensure_tables",
    "now_str",
    "get_shipping_fee",
    "df_from_sql",
    "refresh_alias_vendor_cache",
    # clean
    "TRACK_COLS",
    "clean_invoice_id",
    "normalize_tracking",
    # invoice_calc
    "add_basic_shipping",
    "add_courier_fee_by_zone",
    "get_invoice_id",
    "finalize_invoice",
    "create_and_finalize_invoice",
    "get_extra_unit",
    "get_material_unit",
    "add_flag_fee",
    "add_barcode_fee",
    "add_void_fee",
    "add_ppbag_fee",
    "add_video_out_fee",
    "add_return_pickup_fee",
    "add_return_courier_fee",
    "add_video_ret_fee",
    "add_box_fee_by_zone",
    "add_worklog_items",
    # fees
    "add_combined_pack_fee",
    "calculate_combined_pack_fee",
    "calculate_courier_fee_by_zone",
    "get_courier_fee_items",
    "add_inbound_inspection_fee",
    "calculate_inbound_inspection_fee",
    "add_remote_area_fee",
    "calculate_remote_area_fee",
    # shipping_stats
    "shipping_stats",
    "get_shipping_count",
    # upload
    "ingest",
    "list_uploads",
    "delete_upload",
    # pdf
    "InvoicePDF",
    "create_invoice_pdf",
]

