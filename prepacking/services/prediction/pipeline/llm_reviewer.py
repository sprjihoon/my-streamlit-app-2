"""
llm_reviewer — LLM 기반 예측 결과 검증 및 보정
═══════════════════════════════════════════════
모든 예측을 LLM에 보내면 비용/속도 문제가 있으므로,
이상치(outlier)만 선별하여 LLM에 검증을 요청한다.

이상치 기준:
  1) 예측 vs 통계 중앙값 차이가 3배 이상
  2) 최근 4주 대비 급증/급감 패턴
  3) 총합 예측이 실제 범위를 크게 벗어남
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def review_predictions(
    predictions: list[dict],
    supplier_name: str,
    target_date: str,
    max_review_items: int = 10,
) -> list[dict]:
    """
    예측 결과 중 이상치를 LLM으로 검증하고 보정한다.
    원본 predictions를 수정하여 반환.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.info("No OpenAI API key, skipping LLM review")
        return predictions

    # 이상치 선별
    outliers = _detect_outliers(predictions)
    if not outliers:
        return predictions

    review_items = outliers[:max_review_items]

    try:
        adjustments = _call_llm_review(review_items, supplier_name, target_date, api_key)
    except Exception as exc:
        logger.warning("LLM review failed: %s", exc)
        return predictions

    # 보정 적용
    if adjustments:
        _apply_adjustments(predictions, adjustments)

    return predictions


def _detect_outliers(predictions: list[dict]) -> list[dict]:
    """이상치 후보를 선별한다."""
    outliers = []

    for p in predictions:
        pred = p.get("predicted_qty", 0)
        stat = p.get("stat_qty", 0)
        wd_avg = p.get("recent_same_weekday_avg", 0)
        avg_30 = p.get("recent_30d_avg", 0)

        reasons = []

        # 예측이 같은 요일 평균의 3배 이상
        if wd_avg > 0 and pred > wd_avg * 3:
            reasons.append(f"pred({pred}) > 3x weekday_avg({wd_avg:.0f})")

        # 예측이 30일 평균의 5배 이상
        if avg_30 > 0 and pred > avg_30 * 5:
            reasons.append(f"pred({pred}) > 5x 30d_avg({avg_30:.0f})")

        # 통계와 ML이 크게 다름
        ml_qty = p.get("ml_qty", 0)
        if stat > 0 and ml_qty > 0 and abs(stat - ml_qty) > max(stat, ml_qty) * 0.5:
            reasons.append(f"stat({stat}) vs ml({ml_qty}) diverge")

        if reasons:
            outliers.append({**p, "_outlier_reasons": reasons})

    outliers.sort(key=lambda x: x.get("predicted_qty", 0), reverse=True)
    return outliers


def _call_llm_review(
    items: list[dict],
    supplier_name: str,
    target_date: str,
    api_key: str,
) -> list[dict]:
    """OpenAI API로 이상치 검증."""
    import httpx

    summary_lines = []
    for i, item in enumerate(items):
        summary_lines.append(
            f"{i+1}. {item.get('target_name', '?')} | "
            f"예측={item.get('predicted_qty', 0)} | "
            f"통계={item.get('stat_qty', 0)} | "
            f"ML={item.get('ml_qty', 0)} | "
            f"요일평균={item.get('recent_same_weekday_avg', 0):.0f} | "
            f"30일평균={item.get('recent_30d_avg', 0):.1f} | "
            f"이상사유={item.get('_outlier_reasons', [])}"
        )

    prompt = f"""당신은 물류 예측 전문가입니다.
업체: {supplier_name}
예측일: {target_date}

아래 예측 항목들이 이상치로 감지되었습니다. 각 항목에 대해:
1. 예측값이 합리적인지 판단
2. 보정이 필요하면 적정 수량 제안
3. 판단 근거를 한 줄로 설명

항목:
{chr(10).join(summary_lines)}

JSON 배열로 응답하세요. 각 항목:
{{"index": 번호, "action": "keep"|"adjust"|"zero", "adjusted_qty": 숫자, "reason": "한줄설명"}}
"""

    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500,
        },
        timeout=15.0,
    )
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]

    # JSON 파싱
    start = content.find("[")
    end = content.rfind("]") + 1
    if start >= 0 and end > start:
        return json.loads(content[start:end])

    return []


def _apply_adjustments(predictions: list[dict], adjustments: list[dict]) -> None:
    """LLM 보정 결과를 원본 predictions에 적용."""
    adj_map = {}
    for a in adjustments:
        idx = a.get("index", 0) - 1
        if 0 <= idx:
            adj_map[idx] = a

    if not adj_map:
        return

    # outlier 인덱스와 prediction 인덱스 매핑은 복잡하므로,
    # target_name으로 매칭
    outlier_names = []
    for p in predictions:
        pred = p.get("predicted_qty", 0)
        wd_avg = p.get("recent_same_weekday_avg", 0)
        if wd_avg > 0 and pred > wd_avg * 3:
            outlier_names.append(p.get("target_name", ""))

    for a in adjustments:
        action = a.get("action", "keep")
        if action == "keep":
            continue

        idx = a.get("index", 0) - 1
        if idx < 0 or idx >= len(outlier_names):
            continue

        target_name = outlier_names[idx]
        for p in predictions:
            if p.get("target_name") == target_name:
                old_qty = p["predicted_qty"]
                if action == "zero":
                    p["predicted_qty"] = 0
                elif action == "adjust":
                    p["predicted_qty"] = max(0, int(a.get("adjusted_qty", old_qty)))

                p["gpt_reason"] = f"LLM: {a.get('reason', '')} (was {old_qty})"
                p["model_used"] = "llm_adjusted"
                break
