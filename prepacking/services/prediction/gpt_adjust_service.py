"""
GPT 보정 서비스
──────────────
ML/통계 예측 결과를 GPT에게 보내서 최종 수량을 보정받는다.
API 키가 없거나 호출 실패 시 ML 결과를 그대로 사용(폴백).
"""
from __future__ import annotations

import json
import logging
import pathlib
import time

from prepacking.config import OPENAI_API_KEY, PP_AI_MODEL

logger = logging.getLogger(__name__)

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
PROMPT_VERSION = "forecast_adjust.txt@1"


def _read_template() -> str:
    p = pathlib.Path(__file__).resolve().parent.parent.parent / "prompts" / "forecast_adjust.txt"
    return p.read_text(encoding="utf-8")


def adjust_with_gpt(
    supplier_name: str,
    target_name: str,
    target_type: str,
    target_date: str,
    weekday_idx: int,
    ml_qty: int,
    ml_accuracy: float,
    ml_samples: int,
    stat_qty: int,
    avg_7d: float,
    avg_14d: float,
    avg_30d: float,
    avg_same_wd: float,
    same_wd_history: list[float],
    cv: float,
    trend: float,
    frequency: int,
) -> dict:
    """
    GPT 보정 호출. 반환:
      {"adjusted_qty": int, "confidence": str, "reason": str, "used_gpt": bool}
    """
    if not OPENAI_API_KEY:
        return _fallback(ml_qty, stat_qty, "no_api_key")

    weekday_name = WEEKDAY_KR[weekday_idx] if 0 <= weekday_idx <= 6 else "?"

    try:
        tpl = _read_template()
    except Exception:
        return _fallback(ml_qty, stat_qty, "template_not_found")

    history_str = ", ".join(f"{v:.0f}" for v in same_wd_history) if same_wd_history else "없음"

    prompt = tpl.format(
        target_date=target_date,
        weekday_name=weekday_name,
        supplier_name=supplier_name or "전체",
        target_name=target_name,
        target_type="조합" if target_type == "combination" else "단일 SKU",
        ml_qty=ml_qty,
        ml_accuracy=f"{ml_accuracy:.1%}" if ml_accuracy > 0 else "N/A",
        ml_samples=ml_samples,
        stat_qty=stat_qty,
        avg_7d=f"{avg_7d:.1f}",
        avg_14d=f"{avg_14d:.1f}",
        avg_30d=f"{avg_30d:.1f}",
        avg_same_wd=f"{avg_same_wd:.1f}",
        same_wd_history=history_str,
        cv=f"{cv:.2f}",
        trend=f"{trend:+.2f}",
        frequency=frequency,
    )

    try:
        from openai import OpenAI
        from prepacking.ai import ai_log_service

        t0 = time.perf_counter()
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=PP_AI_MODEL,
            temperature=0.2,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0

        pricing = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.5, 10.0)}
        inp_m, out_m = pricing.get(PP_AI_MODEL, (0.15, 0.60))
        cost = (in_tok * inp_m + out_tok * out_m) / 1_000_000.0

        ai_log_service.log_ai_call(
            PP_AI_MODEL, PROMPT_VERSION, in_tok, out_tok, cost, latency_ms,
            success=True, error_message="",
        )

        parsed = _parse_response(text)
        if parsed is None:
            return _fallback(ml_qty, stat_qty, "parse_failed")

        adj_qty = max(0, int(parsed.get("adjusted_qty", ml_qty)))

        return {
            "adjusted_qty": adj_qty,
            "confidence": parsed.get("confidence", "medium"),
            "reason": parsed.get("reason", ""),
            "used_gpt": True,
            "gpt_model": PP_AI_MODEL,
            "latency_ms": latency_ms,
            "tokens_used": in_tok + out_tok,
        }

    except Exception as exc:
        logger.warning("GPT adjust failed: %s", exc)
        return _fallback(ml_qty, stat_qty, f"error: {exc}")


def _parse_response(text: str) -> dict | None:
    """GPT 응답에서 JSON 추출."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _fallback(ml_qty: int, stat_qty: int, reason: str) -> dict:
    """GPT 실패 시 ML/통계 결과 중 더 나은 것 사용."""
    qty = ml_qty if ml_qty > 0 else stat_qty
    return {
        "adjusted_qty": qty,
        "confidence": "medium",
        "reason": f"GPT 폴백({reason})",
        "used_gpt": False,
        "gpt_model": "",
        "latency_ms": 0,
        "tokens_used": 0,
    }
