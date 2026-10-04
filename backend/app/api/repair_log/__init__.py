"""Repair log API. Existing imports keep working."""
from __future__ import annotations

import sys
import types

from .router import router
from .common import (
    IMAGE_EXTS,
    UPLOAD_DIR,
    _clean,
    _clean_vendor,
    _lookup_barcode,
    _resolve_vendor,
    _strip_option,
    ensure_repair_tables,
)
from .catalog import (
    BarcodeCreate,
    BarcodeUpdate,
    DefectBody,
    WorkTypeBody,
    barcode_template,
    create_barcode,
    delete_all_barcodes,
    delete_barcode,
    get_catalog,
    get_catalog_price,
    list_barcodes,
    lookup_barcode,
    remove_defect,
    remove_work_type,
    save_defect,
    save_work_type,
    update_barcode,
    upload_barcodes,
    upsert_repair_barcode_record,
)
from .photos import (
    _clear_photo_refs,
    _collect_stale_photo_names,
    _delete_image,
    _image_path,
    _log_photos,
    _save_upload,
    dump_extra_images,
    get_repair_image,
    old_photo_stats,
    parse_extra_images,
    purge_old_photos,
    save_image_bytes,
    upload_photos,
)
from .crud import (
    RepairLogCreate,
    RepairLogUpdate,
    _editor_name,
    _log_where,
    create_log,
    delete_log,
    export_logs,
    get_stats,
    insert_repair_log_record,
    list_logs,
    update_log,
)


class _RepairLogModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name != "UPLOAD_DIR":
            return
        for suffix in ("common", "photos"):
            mod = sys.modules.get(f"backend.app.api.repair_log.{suffix}")
            if mod is not None:
                mod.__dict__["UPLOAD_DIR"] = value


sys.modules[__name__].__class__ = _RepairLogModule
