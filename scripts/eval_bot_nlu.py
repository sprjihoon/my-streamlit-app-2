"""로컬/라이브 NLU 평가. CI에서는 --live를 실행하지 않는다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "bot_nlu_eval_cases.jsonl"


def load_cases() -> list[dict]:
    rows = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def match_expected(intent, expected: dict) -> bool:
    for key in ("action", "entity", "mode_action", "requested_mode", "target"):
        if key in expected and getattr(intent, key, None) != expected[key]:
            if key == "action":
                aliases = {
                    "help": {"help", "show_help"},
                    "lookup_price": {"lookup_price", "query_catalog"},
                    "start": {"start_mode", "unknown"},
                }
                if expected[key] in aliases and getattr(intent, key, None) in aliases[expected[key]]:
                    continue
                if expected[key] == "start" and getattr(intent, "mode_action", None) == "start":
                    continue
            return False
    filters = expected.get("filters") or {}
    for key, value in filters.items():
        if (getattr(intent, "filters", {}) or {}).get(key) != value:
            return False
    fields = expected.get("fields") or {}
    for key, value in fields.items():
        if (getattr(intent, "fields", {}) or {}).get(key) != value:
            return False
    return True


def eval_fallback() -> int:
    from backend.app.services.bot_nlu import fallback_from_local_parsers

    cases = load_cases()
    failed = []
    for case in cases:
        intent = fallback_from_local_parsers(case["text"], case.get("context") or {})
        if not match_expected(intent, case.get("expected") or {}):
            failed.append(case["text"])
    total = len(cases)
    ok = total - len(failed)
    print(f"fallback accuracy {ok}/{total} ({(ok / total * 100) if total else 0:.1f}%)")
    if failed:
        print("failed:")
        for text in failed[:20]:
            print(f"- {text}")
    return 0 if ok == total else 1


def eval_live() -> int:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY missing")
        return 2
    os.environ.pop("BOT_NLU_DISABLE", None)
    from backend.app.services.bot_nlu import interpret_user_text

    cases = load_cases()
    failed = []
    ok = 0
    import asyncio

    async def _run():
        nonlocal ok
        for case in cases:
            ctx = dict(case.get("context") or {})
            ctx.setdefault("user_message", case["text"])
            try:
                intent = await interpret_user_text(case["text"], ctx)
            except Exception:
                failed.append(case["id"])
                continue
            if match_expected(intent, case.get("expected") or {}):
                ok += 1
            else:
                failed.append(case["id"])

    asyncio.run(_run())
    total = len(cases)
    print(f"live intent accuracy {ok}/{total} ({(ok / total * 100) if total else 0:.1f}%)")
    if failed:
        print("failed ids:")
        for item in failed[:20]:
            print(f"- {item}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        return eval_live()
    return eval_fallback()


if __name__ == "__main__":
    raise SystemExit(main())
