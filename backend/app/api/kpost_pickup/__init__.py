"""K-Post pickup API. Existing imports keep working."""
from __future__ import annotations

import sys
import types

from .router import router
from .common import KST, _get_user, _row_to_dict, ensure_pickup_tables
from .pickup import (
    PickupSubmitRequest,
    create_pickup,
    extract_if_needed,
    list_pickups,
    pickup_filter_options,
    pickup_meta,
    preview_pickup,
)
from .saved_recipients import (
    SavedRecipientRequest,
    delete_saved_recipient,
    list_saved_recipients,
    save_recipient,
    update_saved_recipient,
)
from .tracking import (
    bulk_delete_pickups,
    cancel_pickup,
    delete_pickup,
    get_pickup,
    get_res_info_with_dates,
    patch_treat_status,
    refresh_pickup_statuses,
    track_regi_no,
)
from .maintenance import debug_track, maintenance_inspect, maintenance_reset_status

_PATCH_NAMES = ("get_res_info_with_dates", "track_regi_no")
_PATCH_MODULES = ("tracking", "maintenance")


class _KpostPickupModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name not in _PATCH_NAMES:
            return
        for suffix in _PATCH_MODULES:
            mod = sys.modules.get(f"backend.app.api.kpost_pickup.{suffix}")
            if mod is not None:
                mod.__dict__[name] = value


sys.modules[__name__].__class__ = _KpostPickupModule
