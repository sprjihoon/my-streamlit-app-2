"""HS 6자리 품목 검색. 자주 쓰는 창고 카탈로그 + WCO HS 명칭을 로컬에 저장해 검색한다."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.services.ems.item_categories import ITEM_CATEGORIES, suggest_item_categories

HS6_PATH = Path(__file__).with_name("hs6.json")

CHAPTER_KO: dict[str, str] = {
    "01": "산동물",
    "02": "육류",
    "03": "어류 생선 해산물",
    "04": "유제품 계란 꿀",
    "07": "채소",
    "08": "과일",
    "09": "커피 차 향신료",
    "10": "곡물 쌀",
    "16": "조제 육류 어류",
    "17": "당류 사탕 초콜릿",
    "18": "코코아 초콜릿",
    "19": "곡물조제품 라면 과자",
    "20": "채소과일조제품 김치",
    "21": "소스 조미료 건강식품",
    "22": "음료 주류",
    "30": "의약품",
    "33": "화장품 향수",
    "34": "비누 세제",
    "39": "플라스틱 주방용품",
    "42": "가죽 가방 지갑",
    "48": "종이 문구",
    "49": "서적 책",
    "61": "니트 의류 티셔츠",
    "62": "직물 의류 코트",
    "63": "침구 타월",
    "64": "신발",
    "65": "모자",
    "71": "보석 장신구",
    "84": "기계 노트북",
    "85": "전자기기 이어폰 충전기",
    "90": "광학 카메라",
    "91": "시계",
    "94": "가구 침구",
    "95": "장난감 스포츠",
}


@lru_cache(maxsize=1)
def load_hs6() -> list[dict[str, str]]:
    if not HS6_PATH.exists():
        return []
    raw = json.loads(HS6_PATH.read_text(encoding="utf-8"))
    items: list[dict[str, str]] = []
    for row in raw:
        code = re.sub(r"\D", "", str(row.get("hs_code") or ""))
        if len(code) != 6:
            continue
        name_en = str(row.get("name_en") or "").strip()
        if not name_en:
            continue
        items.append({"hs_code": code, "name_en": name_en[:140]})
    return items


@lru_cache(maxsize=1)
def _ko_aliases() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for cat in ITEM_CATEGORIES:
        hs = re.sub(r"\D", "", cat.get("hs_code") or "")
        name = (cat.get("name_ko") or "").strip()
        if len(hs) == 6 and name:
            mapping.setdefault(hs, [])
            if name not in mapping[hs]:
                mapping[hs].append(name)
    return mapping


def _nomenclature_category(row: dict[str, str]) -> dict[str, Any]:
    code = row["hs_code"]
    aliases = _ko_aliases().get(code) or []
    name_en = row["name_en"]
    short_en = name_en.split(";")[0].strip()[:80] or name_en[:80]
    return {
        "id": f"hs-{code}",
        "name_ko": aliases[0] if aliases else short_en,
        "name_en": short_en,
        "hs_code": code,
        "group": "HS목록",
        "description": name_en,
    }


def _chapter_matches(query: str) -> set[str]:
    q = (query or "").strip().lower().replace(" ", "")
    if not q:
        return set()
    hits: set[str] = set()
    for chapter, names in CHAPTER_KO.items():
        hay = names.lower().replace(" ", "")
        if q in hay or hay in q:
            hits.add(chapter)
    return hits


def search_hs_catalog(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 50))
    q = (query or "").strip()
    if not q:
        return suggest_item_categories("", limit)

    frequent = suggest_item_categories(q, limit=limit)
    qn = q.lower().replace(" ", "")
    digits = re.sub(r"\D", "", q)
    chapters = _chapter_matches(q)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in load_hs6():
        code = row["hs_code"]
        hay = f"{row['name_en']}{code}".lower().replace(" ", "")
        aliases = " ".join(_ko_aliases().get(code) or []).lower().replace(" ", "")
        score = 0
        if digits and code.startswith(digits):
            score = 120 if code == digits else 90
        elif qn and qn in hay:
            score = 60
        elif qn and aliases and qn in aliases:
            score = 80
        elif code[:2] in chapters:
            score = 40
        if score:
            ranked.append((score, _nomenclature_category(row)))
    ranked.sort(key=lambda item: (-item[0], item[1]["hs_code"]))

    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []
    for cat in frequent + [item for _, item in ranked]:
        key = (cat.get("hs_code") or "", (cat.get("name_en") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(cat)
        if len(merged) >= limit:
            break
    return merged
