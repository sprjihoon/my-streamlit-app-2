"""Argument coercion and schema checks. Messages and strictness are unchanged."""
import json
from typing import Any, Dict, Optional

from .registry import _TOOL_BY_NAME

def _apply_schema_guard(spec: dict, *, strict: bool) -> dict:
    """가능한 범위에서 additionalProperties=false, strict를 붙인다. 실행 함수는 그대로 둔다."""
    out = json.loads(json.dumps(spec))
    fn = out["function"]
    params = fn.setdefault("parameters", {"type": "object", "properties": {}})
    params["type"] = "object"
    params["additionalProperties"] = False
    props = params.get("properties") or {}
    if strict and props:
        params["required"] = list(props.keys())
        fn["strict"] = True
    elif not props:
        params["additionalProperties"] = False
        if strict:
            fn["strict"] = True
            params["required"] = []
    return out

def allowed_arg_keys(tool_name: str) -> set:
    spec = _TOOL_BY_NAME.get(tool_name) or {}
    props = ((spec.get("function") or {}).get("parameters") or {}).get("properties") or {}
    return set(props.keys())


def _coerce_arg(value: Any, typ: Optional[str]) -> Any:
    if value is None:
        return None
    if typ == "integer":
        if isinstance(value, bool):
            raise ValueError("boolean is not integer")
        return int(value)
    if typ == "number":
        if isinstance(value, bool):
            raise ValueError("boolean is not number")
        return float(value)
    if typ == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        raise ValueError("invalid boolean")
    if typ == "string":
        return str(value)
    if typ == "array":
        if not isinstance(value, list):
            raise ValueError("expected array")
        return value
    if typ == "object":
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    return value


def validate_tool_args(tool_name: str, arguments: Optional[Dict[str, Any]]) -> tuple:
    """타입·필수값·허용 필드만 통과시킨다. 선택값은 비워도 된다."""
    spec = _TOOL_BY_NAME.get(tool_name) or {}
    params = (spec.get("function") or {}).get("parameters") or {}
    props = params.get("properties") or {}
    required = params.get("required") or []
    raw = dict(arguments or {})
    cleaned: Dict[str, Any] = {}
    for key, val in raw.items():
        if key not in props:
            continue
        prop = props[key] or {}
        typ = prop.get("type")
        try:
            if typ == "array" and key == "entries":
                items_spec = prop.get("items") or {}
                item_props = items_spec.get("properties") or {}
                item_req = items_spec.get("required") or []
                if not isinstance(val, list):
                    return None, "entries는 배열이어야 합니다."
                entries = []
                for item in val:
                    if not isinstance(item, dict):
                        return None, "entries 항목이 올바르지 않습니다."
                    one: Dict[str, Any] = {}
                    for ik, iv in item.items():
                        if ik not in item_props:
                            continue
                        one[ik] = _coerce_arg(iv, item_props[ik].get("type"))
                    for rk in item_req:
                        if one.get(rk) in (None, ""):
                            return None, f"entries.{rk}은(는) 필수입니다."
                    entries.append(one)
                cleaned[key] = entries
                continue
            cleaned[key] = _coerce_arg(val, typ)
        except (TypeError, ValueError):
            return None, f"{key} 값이 올바르지 않습니다."
    for rk in required:
        if cleaned.get(rk) in (None, "", []):
            return None, f"{rk}은(는) 필수입니다."
    return cleaned, None
