"""
backend/app/api/inbound.py - 입고모드 API
────────────────────────────────────────────
장끼 사진 OCR → 상품 자동 매칭 → 실수량 확인 → 양품화 → 마감

상태 흐름:
  ocr_pending   장끼 확인 중
  confirming    수량 확인 중 (OCR 완료, 직원 실수량 입력 전)
  inbound_done  입고접수 완료 (실수량 확정)
  grading       양품화 중
  repairing     수선 중
  done          최종완료
  cancelled     취소
"""

from .router import router
from .utils import (
    IMAGE_EXTS,
    ITEM_STATUS_LABELS,
    ITEM_STATUS_VALUES,
    STATUS_LABELS,
    STATUS_VALUES,
    UPLOAD_DIR,
    _KST,
    _PHOTO_DECISION_VALUES,
    _QTY_STATE_COL,
    _check_link_expiry,
    _get_item_photos,
    _get_user,
    _hash_password,
    _image_url,
    _image_url_defect,
    _image_url_repair,
    _item_pending_qty,
    _recalc_batch_totals,
    _save_upload,
    _serialize_batch,
    _serialize_item,
    _verify_password,
    logger,
    move_item_qty,
)
from .schemas import (
    CloseRequest,
    DefectLogLink,
    InboxPhotoLink,
    InboundBatchCreate,
    InboundBatchUpdate,
    InboundItemCreate,
    InboundItemUpdate,
    NormalQtyUpdate,
    RepairLogLink,
    ShareLinkCreate,
    VendorAliasUpdate,
)
from .db import ensure_inbound_tables
from .barcode import _match_barcode, _resolve_vendor_names, _update_barcode_master
from .ocr import (
    JANGGI_SCHEMA,
    OCR_MODEL,
    SYSTEM_PROMPT,
    OcrError,
    _normalize_image,
    _ocr_error_to_http,
    _run_ocr,
    ocr_preview,
    run_ocr,
)
from .vendors import (
    delete_vendor_alias,
    get_filter_options,
    get_vendor_aliases,
    get_vendor_overview_detail,
    list_inbound_vendors,
    list_vendor_overviews,
    upsert_vendor_alias,
)
from .batches import (
    close_batch,
    create_batch,
    delete_batch,
    get_batch,
    get_stats,
    grade_complete,
    list_batches,
    update_batch,
)
from .items import add_item, delete_item, update_item, update_normal_qty
from .photos import (
    _cleanup_unmatched_inbox_photos,
    delete_item_photo,
    link_inbox_photo_to_item,
    list_inbox_photos,
    serve_photo,
    unlink_inbox_photo_from_item,
    upload_item_photo,
)
from .exports import export_inbound_xls, generate_barcode_pdf
from .overview import _compute_batch_overview, _infer_phase, get_batch_overview
from .sharing import (
    create_share_link,
    get_share_data,
    get_share_overview,
    revoke_share_link,
    serve_share_photo,
)
from .links import _REPAIR_ACTION_TRANSITIONS, link_defect_log, link_repair_log
