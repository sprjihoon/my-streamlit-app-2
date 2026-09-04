"""
수선 바코드 디코딩
Code128 문자+숫자 (예: ON56S152917). pyzbar 가능하면 먼저, 아니면 Vision.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import List, Optional, Tuple

BARCODE_RE = re.compile(r"[A-Za-z0-9]{8,24}")


def looks_like_barcode(text: Optional[str]) -> bool:
    if not text:
        return False
    s = re.sub(r"[\s\-]", "", text)
    if not BARCODE_RE.fullmatch(s):
        return False
    return any(c.isalpha() for c in s) and any(c.isdigit() for c in s)


def decode_local(data: bytes) -> Optional[Tuple[str, float]]:
    try:
        from io import BytesIO
        from PIL import Image
        from pyzbar.pyzbar import decode as zbar_decode
    except Exception:
        return None
    try:
        img = Image.open(BytesIO(data))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        for r in zbar_decode(img):
            raw = r.data.decode("utf-8", errors="ignore").strip()
            code = re.sub(r"[\s\-]", "", raw)
            if looks_like_barcode(code) or (code.isdigit() and 8 <= len(code) <= 14):
                return code, 0.95
    except Exception:
        return None
    return None


async def decode_set_vision(photos: List[bytes]) -> List[Optional[Tuple[str, float]]]:
    """3장을 한 번에 보고 각 장의 바코드 후보를 반환."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not photos:
        return [None] * len(photos)

    from openai import AsyncOpenAI

    content: list = [{
        "type": "text",
        "text": (
            "These photos may include a 1D Code128 barcode. "
            "The value is alphanumeric like ON56S152917, not only EAN digits. "
            "For each image in order, return the barcode text if readable. "
            "Reply JSON only: {\"results\":[{\"index\":0,\"barcode\":\"ON56S152917\",\"confidence\":0.9}]}. "
            "Use barcode null if none. index is 0-based."
        ),
    }]
    for data in photos:
        b64 = base64.b64encode(data).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
        })

    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": content}],
        temperature=0,
        max_tokens=400,
    )
    raw = (resp.choices[0].message.content or "").replace("```json", "").replace("```", "").strip()
    out: List[Optional[Tuple[str, float]]] = [None] * len(photos)
    try:
        parsed = json.loads(raw)
        for item in parsed.get("results") or []:
            idx = int(item.get("index", -1))
            code = re.sub(r"[\s\-]", "", str(item.get("barcode") or ""))
            conf = float(item.get("confidence") or 0.6)
            if 0 <= idx < len(photos) and looks_like_barcode(code):
                out[idx] = (code, conf)
    except Exception:
        found = BARCODE_RE.findall(raw.replace(" ", ""))
        for i, code in enumerate(found):
            if i < len(out) and looks_like_barcode(code):
                out[i] = (code, 0.5)
    return out


async def classify_photos(photos: List[bytes]) -> dict:
    """
    바코드가 읽히는 1장 + 나머지 보낸 순서대로 전/후.
    반환: barcode, barcode_index, before_index, after_index, decoded[], ambiguous
    """
    decoded: List[Optional[Tuple[str, float]]] = []
    need_vision = []
    for i, data in enumerate(photos):
        local = decode_local(data)
        decoded.append(local)
        if local is None:
            need_vision.append(i)

    if need_vision:
        vision_inputs = [photos[i] for i in need_vision]
        vision = await decode_set_vision(vision_inputs)
        for i, result in zip(need_vision, vision):
            if result and decoded[i] is None:
                decoded[i] = result

    hits = [(i, c, conf) for i, pair in enumerate(decoded) if pair for c, conf in [pair]]
    ambiguous = False
    barcode = None
    barcode_index = None
    if len(hits) == 1:
        barcode_index, barcode, _ = hits[0]
    elif len(hits) >= 2:
        hits.sort(key=lambda x: x[2], reverse=True)
        if hits[0][2] - hits[1][2] >= 0.15 or hits[0][1] == hits[1][1]:
            barcode_index, barcode, _ = hits[0]
        else:
            ambiguous = True
            barcode_index, barcode, _ = hits[0]

    rest = [i for i in range(len(photos)) if i != barcode_index]
    before_index = rest[0] if rest else None
    after_index = rest[1] if len(rest) > 1 else None
    return {
        "barcode": barcode,
        "barcode_index": barcode_index,
        "before_index": before_index,
        "after_index": after_index,
        "decoded": decoded,
        "ambiguous": ambiguous,
        "hit_count": len(hits),
    }
