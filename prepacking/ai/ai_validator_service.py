from __future__ import annotations

import json
import logging
import time

from openai import OpenAI

from prepacking.ai import ai_log_service
from prepacking.ai.prompt_builder import (
    build_failure_analysis_prompt,
    build_post_validation_prompt,
    build_review_prompt,
)
from prepacking.ai.response_parser import parse_failure_response, parse_review_response
from prepacking.common.constants import CONFIDENCE_HIGH, CONFIDENCE_MEDIUM
from prepacking.config import (
    OPENAI_API_KEY,
    PP_AI_MAX_TOKENS,
    PP_AI_MODEL,
    PP_AI_TEMPERATURE,
)
from prepacking.database import ensure_pp_tables, get_pp_connection

logger = logging.getLogger(__name__)

PROMPT_VERSION_REVIEW = "review_recommendation.txt@1"
PROMPT_VERSION_FAILURE = "failure_analysis.txt@1"


def _row_dict(cur) -> dict | None:
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    m = (model or "").lower()
    pricing = (
        ("gpt-4o-mini", (0.15, 0.60)),
        ("gpt-4o", (2.5, 10.0)),
        ("gpt-4-turbo", (10.0, 30.0)),
        ("gpt-3.5-turbo", (0.5, 1.5)),
    )
    inp_m, out_m = 0.15, 0.60
    for key, pair in pricing:
        if key in m:
            inp_m, out_m = pair
            break
    return (max(0, input_tokens) * inp_m + max(0, output_tokens) * out_m) / 1_000_000.0


def _call_openai(prompt: str) -> tuple[str, int, int, int]:
    t0 = time.perf_counter()
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=PP_AI_MODEL,
        temperature=float(PP_AI_TEMPERATURE),
        max_tokens=int(PP_AI_MAX_TOKENS),
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    text = (resp.choices[0].message.content or "").strip()
    usage = getattr(resp, "usage", None)
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    return text, in_tok, out_tok, latency_ms


def _call_openai_safe(prompt: str, prompt_version: str) -> tuple[str | None, str]:
    t0 = time.perf_counter()
    if not OPENAI_API_KEY:
        err = "OPENAI_API_KEY is not set"
        latency_ms = int((time.perf_counter() - t0) * 1000)
        ai_log_service.log_ai_call(
            PP_AI_MODEL,
            prompt_version,
            0,
            0,
            0.0,
            latency_ms,
            success=False,
            error_message=err,
        )
        return None, err
    try:
        text, in_tok, out_tok, latency_ms = _call_openai(prompt)
        cost = _estimate_cost_usd(PP_AI_MODEL, in_tok, out_tok)
        ai_log_service.log_ai_call(
            PP_AI_MODEL,
            prompt_version,
            in_tok,
            out_tok,
            cost,
            latency_ms,
            success=True,
            error_message="",
        )
        return text, ""
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        err = str(e)
        logger.exception("OpenAI call failed: %s", err)
        ai_log_service.log_ai_call(
            PP_AI_MODEL,
            prompt_version,
            0,
            0,
            0.0,
            latency_ms,
            success=False,
            error_message=err[:2000],
        )
        return None, err


def _rule_based_action(confidence: float) -> str:
    c = float(confidence or 0)
    if c >= CONFIDENCE_HIGH:
        return "approve"
    if c >= CONFIDENCE_MEDIUM:
        return "modify"
    if c >= 0.3:
        return "hold"
    return "reject"


def _fetch_historical_accuracy(supplier_name: str, target_name: str) -> float | None:
    with get_pp_connection() as con:
        row = con.execute(
            """
            SELECT AVG(accuracy_rate) AS a
            FROM pp_validations
            WHERE supplier_name = ? AND target_name = ?
              AND accuracy_rate IS NOT NULL AND accuracy_rate > 0
            """,
            (supplier_name or "", target_name or ""),
        ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def review_recommendation(recommendation_id: int) -> dict:
    ensure_pp_tables()
    rid = int(recommendation_id)
    with get_pp_connection() as con:
        cur = con.execute(
            "SELECT * FROM pp_recommendations WHERE recommendation_id = ?",
            (rid,),
        )
        rec = _row_dict(cur)
    if not rec:
        return {"ok": False, "error": "recommendation_not_found", "recommendation_id": rid}
    hist_acc = _fetch_historical_accuracy(
        str(rec.get("supplier_name") or ""),
        str(rec.get("target_name") or ""),
    )
    historical_data = {
        "historical_accuracy": hist_acc if hist_acc is not None else None,
        "variability": rec.get("risk_score"),
        "recent_7d_avg": rec.get("recent_7d_avg"),
        "recent_30d_avg": rec.get("recent_30d_avg"),
        "weekday_avg": rec.get("recent_same_weekday_avg"),
    }
    prompt = build_review_prompt(rec, historical_data)
    raw, err = _call_openai_safe(prompt, PROMPT_VERSION_REVIEW)
    if raw is None:
        action = _rule_based_action(float(rec.get("confidence_score") or 0))
        return {
            "ok": True,
            "fallback": True,
            "recommendation_id": rid,
            "recommended_action": action,
            "reason_summary": "",
            "risk_summary": "",
            "confidence_comment": "",
            "error": err,
        }
    parsed = parse_review_response(raw)
    action = (parsed.get("recommended_action") or "").lower() or _rule_based_action(
        float(rec.get("confidence_score") or 0)
    )
    snapshot = json.dumps({"recommendation": rec, "historical_data": historical_data}, ensure_ascii=False)
    variability = float(rec.get("risk_score") or 0)
    hist_rate = float(hist_acc) if hist_acc is not None else 0.0
    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_ai_reviews(
                recommendation_id, supplier_name, target_type, target_code, target_name,
                rule_based_predicted_qty, recent_7d_avg, recent_30d_avg, recent_same_weekday_avg,
                variability_score, repeat_score, combination_repeat_score, pack_stability_score,
                exclusion_flag, historical_accuracy_rate, historical_unwrap_rate,
                ai_model_name, ai_prompt_version, ai_input_snapshot, ai_review_result,
                ai_recommended_action, ai_reason_summary, ai_risk_summary, ai_confidence_comment,
                reviewed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """,
            (
                rid,
                rec.get("supplier_name") or "",
                rec.get("target_type") or "",
                rec.get("target_code") or "",
                rec.get("target_name") or "",
                int(rec.get("predicted_qty") or 0),
                float(rec.get("recent_7d_avg") or 0),
                float(rec.get("recent_30d_avg") or 0),
                float(rec.get("recent_same_weekday_avg") or 0),
                variability,
                0.0,
                0.0,
                0.0,
                0,
                hist_rate,
                0.0,
                PP_AI_MODEL,
                PROMPT_VERSION_REVIEW,
                snapshot[:65000] if len(snapshot) > 65000 else snapshot,
                raw[:65000] if len(raw) > 65000 else raw,
                action,
                parsed.get("reason_summary") or "",
                parsed.get("risk_summary") or "",
                parsed.get("confidence_comment") or "",
            ),
        )
        con.commit()
    return {
        "ok": True,
        "fallback": False,
        "recommendation_id": rid,
        "recommended_action": action,
        "reason_summary": parsed.get("reason_summary") or "",
        "risk_summary": parsed.get("risk_summary") or "",
        "confidence_comment": parsed.get("confidence_comment") or "",
        "raw_response": raw,
    }


def analyze_failure(validation_id: int) -> dict:
    ensure_pp_tables()
    vid = int(validation_id)
    with get_pp_connection() as con:
        cur = con.execute("SELECT * FROM pp_validations WHERE validation_id = ?", (vid,))
        val = _row_dict(cur)
        rec = None
        if val and val.get("recommendation_id"):
            cur2 = con.execute(
                "SELECT * FROM pp_recommendations WHERE recommendation_id = ?",
                (int(val["recommendation_id"]),),
            )
            rec = _row_dict(cur2)
    if not val:
        return {"ok": False, "error": "validation_not_found", "validation_id": vid}
    vcopy = dict(val)
    pred = int(vcopy.get("predicted_qty") or 0)
    actual = int(vcopy.get("actual_qty") or 0)
    vcopy["error_qty"] = abs(pred - actual)
    if not vcopy.get("over_under_type"):
        vcopy["over_under_type"] = str(vcopy.get("validation_result") or "")
    prompt = (
        build_post_validation_prompt(vcopy, rec or {})
        if rec
        else build_failure_analysis_prompt(vcopy)
    )
    raw, err = _call_openai_safe(prompt, PROMPT_VERSION_FAILURE)
    rid = int(val.get("recommendation_id") or 0) or None
    if raw is None:
        return {
            "ok": True,
            "fallback": True,
            "validation_id": vid,
            "failure_reason": "",
            "improvement_suggestion": "",
            "error": err,
        }
    parsed = parse_failure_response(raw)
    with get_pp_connection() as con:
        con.execute(
            """
            INSERT INTO pp_ai_post_validations(
                validation_id, recommendation_id, predicted_qty, actual_qty, error_qty,
                over_under_type, ai_failure_reason, ai_improvement_suggestion,
                ai_reanalysis_model, ai_reanalysis_prompt_version, reanalyzed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """,
            (
                vid,
                rid,
                pred,
                actual,
                int(vcopy.get("error_qty") or 0),
                str(vcopy.get("over_under_type") or ""),
                parsed.get("failure_reason") or "",
                parsed.get("improvement_suggestion") or "",
                PP_AI_MODEL,
                PROMPT_VERSION_FAILURE,
            ),
        )
        con.commit()
    return {
        "ok": True,
        "fallback": False,
        "validation_id": vid,
        "failure_reason": parsed.get("failure_reason") or "",
        "improvement_suggestion": parsed.get("improvement_suggestion") or "",
        "raw_response": raw,
    }
