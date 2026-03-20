from __future__ import annotations

import json
import re


def _strip_code_fence(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _extract_json_object(s: str) -> str | None:
    t = _strip_code_fence(s)
    try:
        start = t.index("{")
        depth = 0
        for i, ch in enumerate(t[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return t[start : i + 1]
    except ValueError:
        pass
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", t, re.DOTALL)
    return m.group(0) if m else None


def _first_group(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def parse_review_response(raw_response: str) -> dict:
    out = {
        "recommended_action": "",
        "reason_summary": "",
        "risk_summary": "",
        "confidence_comment": "",
    }
    if not raw_response or not str(raw_response).strip():
        return out
    text = str(raw_response)
    blob = _extract_json_object(text)
    if blob:
        try:
            data = json.loads(blob)
            if isinstance(data, dict):
                out["recommended_action"] = str(
                    data.get("recommended_action", data.get("action", "")) or ""
                ).strip()
                out["reason_summary"] = str(data.get("reason_summary", "") or "").strip()
                out["risk_summary"] = str(data.get("risk_summary", "") or "").strip()
                out["confidence_comment"] = str(
                    data.get("confidence_comment", data.get("confidence", "")) or ""
                ).strip()
                if out["recommended_action"]:
                    return out
        except json.JSONDecodeError:
            pass
    out["recommended_action"] = _first_group(
        [
            r"recommended_action[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']",
            r"recommended_action\s*[:：]\s*([^\n]+)",
        ],
        text,
    )
    out["reason_summary"] = _first_group(
        [r"reason_summary[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", r"reason_summary\s*[:：]\s*([^\n]+)"],
        text,
    )
    out["risk_summary"] = _first_group(
        [r"risk_summary[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", r"risk_summary\s*[:：]\s*([^\n]+)"],
        text,
    )
    out["confidence_comment"] = _first_group(
        [
            r"confidence_comment[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']",
            r"confidence_comment\s*[:：]\s*([^\n]+)",
        ],
        text,
    )
    return out


def parse_failure_response(raw_response: str) -> dict:
    out = {"failure_reason": "", "improvement_suggestion": ""}
    if not raw_response or not str(raw_response).strip():
        return out
    text = str(raw_response)
    blob = _extract_json_object(text)
    if blob:
        try:
            data = json.loads(blob)
            if isinstance(data, dict):
                out["failure_reason"] = str(data.get("failure_reason", "") or "").strip()
                out["improvement_suggestion"] = str(
                    data.get("improvement_suggestion", data.get("suggestion", "")) or ""
                ).strip()
                if out["failure_reason"] or out["improvement_suggestion"]:
                    return out
        except json.JSONDecodeError:
            pass
    out["failure_reason"] = _first_group(
        [r"failure_reason[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", r"failure_reason\s*[:：]\s*([^\n]+)"],
        text,
    )
    out["improvement_suggestion"] = _first_group(
        [
            r"improvement_suggestion[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']",
            r"improvement_suggestion\s*[:：]\s*([^\n]+)",
        ],
        text,
    )
    return out
