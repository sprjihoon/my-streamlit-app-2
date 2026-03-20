from __future__ import annotations

import pathlib


def _prompts_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "prompts"


def _read_template(name: str) -> str:
    return (_prompts_dir() / name).read_text(encoding="utf-8")


def _num(v, default=0):
    if v is None:
        return default
    try:
        return float(v) if isinstance(v, str) and "." in str(v).strip() else int(float(v))
    except (TypeError, ValueError):
        return default


def build_review_prompt(recommendation: dict, historical_data: dict) -> str:
    h = historical_data or {}
    r = recommendation or {}
    supplier = str(r.get("supplier_name") or "")
    target = str(r.get("target_name") or "")
    pred = _num(r.get("predicted_qty"), 0)
    conf = float(r.get("confidence_score") or 0)
    r7 = float(h.get("recent_7d_avg", r.get("recent_7d_avg")) or 0)
    r30 = float(h.get("recent_30d_avg", r.get("recent_30d_avg")) or 0)
    wday = float(
        h.get("weekday_avg", r.get("recent_same_weekday_avg") or r.get("weekday_avg")) or 0
    )
    var = h.get("variability", r.get("risk_score"))
    if var is None:
        var = 0
    var_s = str(var)
    hist_acc = h.get("historical_accuracy", h.get("historical_accuracy_rate"))
    if hist_acc is None:
        hist_acc = "데이터 없음"
    else:
        hist_acc = str(hist_acc)
    tpl = _read_template("review_recommendation.txt")
    return tpl.format(
        supplier_name=supplier,
        target_name=target,
        predicted_qty=pred,
        confidence_score=conf,
        recent_7d_avg=r7,
        recent_30d_avg=r30,
        weekday_avg=wday,
        variability=var_s,
        historical_accuracy=hist_acc,
    )


def build_failure_analysis_prompt(validation: dict) -> str:
    v = validation or {}
    target = str(v.get("target_name") or "")
    pred = _num(v.get("predicted_qty"), 0)
    actual = _num(v.get("actual_qty"), 0)
    err = v.get("error_qty")
    if err is None:
        err = abs(int(pred) - int(actual))
    ou = str(v.get("over_under_type") or v.get("validation_result") or "")
    tpl = _read_template("failure_analysis.txt")
    return tpl.format(
        target_name=target,
        predicted_qty=pred,
        actual_qty=actual,
        error_qty=err,
        over_under_type=ou or "미상",
    )


def build_post_validation_prompt(validation: dict, recommendation: dict) -> str:
    v = validation or {}
    rec = recommendation or {}
    base = build_failure_analysis_prompt(v)
    if not rec:
        return base
    extra = (
        "\n\n## 추천 당시 맥락(참고)\n"
        f"- 공급사: {rec.get('supplier_name', '')}\n"
        f"- 추천일/대상일: {rec.get('recommendation_date', '')} / {rec.get('target_date', '')}\n"
        f"- 당시 예측 수량: {rec.get('predicted_qty', '')}\n"
        f"- 당시 신뢰도: {rec.get('confidence_score', '')}\n"
        f"- 추천 사유 요약: {rec.get('recommendation_reason', '')}\n"
    )
    return base + extra
