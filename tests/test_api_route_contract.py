"""Lock the current method and path contract for the core APIs.

This does not call external carriers and does not write the production database.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "api_route_contract.json"
PREFIXES = (
    "/inbound",
    "/repair-log",
    "/kpost-pickup",
    "/domestic-shipping",
    "/overseas-shipping",
    "/invoices",
    "/leave",
)


def _live_routes() -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {prefix: set() for prefix in PREFIXES}
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for prefix in PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                for method in methods:
                    if method in {"HEAD", "OPTIONS"}:
                        continue
                    grouped[prefix].add(f"{method} {path}")
    return {prefix: sorted(grouped[prefix]) for prefix in PREFIXES}


def test_core_api_routes_match_snapshot():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    live = _live_routes()
    for prefix in PREFIXES:
        assert live[prefix] == expected[prefix]


def test_core_request_schema_names():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["schemas"]
    spec = app.openapi()
    ref_key = "$ref"
    for key, name in expected.items():
        method, path = key.split(" ", 1)
        operation = spec["paths"][path][method.lower()]
        schema = (
            (operation.get("requestBody") or {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        assert schema.get(ref_key, "").endswith("/" + name)


def test_export_routes_remain_in_contract():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    joined = "\n".join(
        line
        for prefix in ("/invoices", "/repair-log", "/inbound")
        for line in expected[prefix]
    )
    for required in (
        "GET /invoices/export/xlsx",
        "GET /invoices/{invoice_id}/export/pdf",
        "GET /invoices/{invoice_id}/export/xlsx",
        "GET /repair-log/export",
        "GET /inbound/batches/{batch_id}/export-xls",
    ):
        assert required in joined
