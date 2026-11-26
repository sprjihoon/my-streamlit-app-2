"""근로자 도장과 싸인 이미지를 만들고 다듬는다."""
from __future__ import annotations

import fitz

_RED = (0.73, 0.05, 0.08)
_STYLES = {"grid", "ring"}


def seal_label(name: str) -> str:
    chars = [ch for ch in (name or "").strip() if not ch.isspace()]
    if not chars:
        raise ValueError("도장에 넣을 이름이 없습니다.")
    return "".join(chars[:4])


def make_seal(name: str, style: str) -> bytes:
    """이름 도장. grid는 원 안에 네 글자 목도장, ring은 타원 안에 이름을 세로로 넣는다."""
    if style not in _STYLES:
        raise ValueError("도장 모양을 고르세요.")
    doc = fitz.open()
    if style == "ring":
        page = doc.new_page(width=240, height=340)
        _draw_oval(page, _oval_chars(name))
    else:
        page = doc.new_page(width=280, height=280)
        _draw_wood(page, _wood_chars(name))
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=True)
    doc.close()
    return _finish(pix)


def _wood_chars(name: str) -> str:
    """세 글자 이름은 뒤에 인을 붙여 네 글자 목도장으로 만든다."""
    label = seal_label(name)
    if len(label) == 3:
        return label + "인"
    return label


def _oval_chars(name: str) -> str:
    """타원에는 본인 이름만 넣는다."""
    return seal_label(name)


def _put_char(page: fitz.Page, char: str, cx: float, cy: float, size: float) -> None:
    page.insert_text((cx - size / 2, cy + size * 0.34), char, fontsize=size, fontname="korea", color=_RED)


def _draw_wood(page: fitz.Page, label: str) -> None:
    shape = page.new_shape()
    shape.draw_circle(fitz.Point(140, 140), 118)
    shape.finish(color=_RED, width=14)
    shape.commit()
    if len(label) >= 4:
        # 오른쪽 줄부터 위에서 아래로 읽는다. 장지훈인 → 지 장 / 인 훈
        chars = label[:4]
        size = 64
        slots = (
            (176, 104),
            (176, 176),
            (104, 104),
            (104, 176),
        )
        for char, (cx, cy) in zip(chars, slots):
            _put_char(page, char, cx, cy, size)
        return
    if len(label) == 2:
        _put_char(page, label[0], 140, 100, 72)
        _put_char(page, label[1], 140, 180, 72)
        return
    _put_char(page, label[0], 140, 140, 92)


def _draw_oval(page: fitz.Page, label: str) -> None:
    shape = page.new_shape()
    shape.draw_oval(fitz.Rect(22, 14, 218, 326))
    shape.finish(color=_RED, width=13)
    shape.commit()
    count = len(label)
    size = {1: 100, 2: 84, 3: 72, 4: 56}[count]
    gap = {1: 0, 2: 90, 3: 74, 4: 62}[count]
    top = 170 - gap * (count - 1) / 2
    for index, char in enumerate(label):
        _put_char(page, char, 120, top + gap * index, size)


def prepare_mark(raw: bytes) -> bytes:
    """올린 도장·싸인을 투명 배경 PNG로 맞춘다."""
    if not raw or len(raw) > 1_500_000:
        raise ValueError("도장 파일을 확인하세요.")
    try:
        pix = fitz.Pixmap(raw)
    except Exception as exc:
        raise ValueError("도장 이미지를 읽을 수 없습니다.") from exc
    if pix.colorspace is None or pix.n not in (1, 3, 4):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    elif pix.colorspace.n == 1:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    longest = max(pix.width, pix.height)
    if longest > 640:
        scale = 640 / longest
        pix = fitz.Pixmap(pix, pix.width * scale, pix.height * scale)
    if not pix.alpha:
        pix = fitz.Pixmap(pix, 1)
    return _finish(pix)


def mark_is_signature(png: bytes) -> bool:
    pix = fitz.Pixmap(png)
    return pix.width >= pix.height * 1.65


def _finish(pix: fitz.Pixmap) -> bytes:
    cleared = _clear_paper(pix)
    cropped = _crop_visible(cleared)
    if cropped is None:
        raise ValueError("도장이나 싸인이 비어 있습니다.")
    return cropped.tobytes("png")


def _clear_paper(pix: fitz.Pixmap) -> fitz.Pixmap:
    if not pix.alpha:
        pix = fitz.Pixmap(pix, 1)
    n = pix.n
    data = bytearray(pix.samples)
    for index in range(0, len(data), n):
        red, green, blue = data[index], data[index + 1], data[index + 2]
        if red > 236 and green > 236 and blue > 236:
            data[index + 3] = 0
    return fitz.Pixmap(fitz.csRGB, pix.width, pix.height, bytes(data), 1)


def _crop_visible(pix: fitz.Pixmap, pad: int = 6) -> fitz.Pixmap | None:
    n = pix.n
    width, height = pix.width, pix.height
    samples = pix.samples
    min_x, min_y, max_x, max_y = width, height, 0, 0
    found = False
    for y in range(height):
        row = y * width * n
        for x in range(width):
            if samples[row + x * n + 3] < 24:
                continue
            found = True
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if not found:
        return None
    x0 = max(0, min_x - pad)
    y0 = max(0, min_y - pad)
    x1 = min(width, max_x + pad + 1)
    y1 = min(height, max_y + pad + 1)
    crop_w = x1 - x0
    crop_h = y1 - y0
    cropped = bytearray(crop_w * crop_h * n)
    for y in range(crop_h):
        src = ((y0 + y) * width + x0) * n
        dst = y * crop_w * n
        cropped[dst:dst + crop_w * n] = samples[src:src + crop_w * n]
    return fitz.Pixmap(fitz.csRGB, crop_w, crop_h, bytes(cropped), 1)
