from __future__ import annotations

import math


def calculate_confidence(frequency: int, variability: float, data_days: int) -> float:
    freq = max(0, int(frequency))
    var = max(0.0, float(variability))
    days = max(0, int(data_days))
    freq_part = min(1.0, freq / 24.0)
    var_part = max(0.0, 1.0 - min(1.0, var))
    days_part = min(1.0, days / 60.0)
    raw = 0.45 * freq_part + 0.4 * var_part + 0.15 * days_part
    if math.isnan(raw) or math.isinf(raw):
        return 0.0
    return max(0.0, min(1.0, raw))


def calculate_risk(confidence: float, is_new_sku: bool, has_exceptions: bool) -> float:
    c = max(0.0, min(1.0, float(confidence)))
    r = 1.0 - c
    if is_new_sku:
        r += 0.22
    if has_exceptions:
        r += 0.12
    return max(0.0, min(1.0, r))
