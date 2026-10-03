"""Janggi OCR normalization, OpenAI call, and OCR routes."""
from __future__ import annotations

import base64
import io
import json
import os
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import File, Header, HTTPException, UploadFile
from PIL import Image, ImageOps

from backend.app.api.logs import add_log
from logic.db import get_connection

from .barcode import _match_barcode, _update_barcode_master
from .router import router
from .utils import UPLOAD_DIR, _get_user, _recalc_batch_totals, logger

# ─────────────────────────────────────
# OCR (장끼 이미지 분석)
# ─────────────────────────────────────

OCR_MODEL: str = os.getenv("BOT_OCR_MODEL", "gpt-4o")

JANGGI_SCHEMA: dict = {
    "type": "object",
    "required": ["receipt", "items"],
    "additionalProperties": False,
    "properties": {
        "receipt": {
            "type": "object",
            "required": [
                "storeName", "receiptNo", "orderDate", "totalAmount",
                "isHandwritten", "confidence", "needsReview", "warnings",
            ],
            "additionalProperties": False,
            "properties": {
                "storeName":     {"type": ["string", "null"]},
                "receiptNo":     {"type": ["string", "null"]},
                "orderDate":     {"type": ["string", "null"]},
                "totalAmount":   {"type": ["number", "null"]},
                "isHandwritten": {"type": "boolean"},
                "confidence":    {"type": "number"},
                "needsReview":   {"type": "boolean"},
                "warnings":      {"type": "array", "items": {"type": "string"}},
            },
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "lineNo", "rawText", "itemName", "color", "size", "optionText",
                    "unitPrice", "quantity", "amount", "confidence", "needsReview", "warnings",
                ],
                "additionalProperties": False,
                "properties": {
                    "lineNo":     {"type": "integer"},
                    "rawText":    {"type": ["string", "null"]},
                    "itemName":   {"type": ["string", "null"]},
                    "color":      {"type": ["string", "null"]},
                    "size":       {"type": ["string", "null"]},
                    "optionText": {"type": ["string", "null"]},
                    "unitPrice":  {"type": ["number", "null"]},
                    "quantity":   {"type": ["number", "null"]},
                    "amount":     {"type": ["number", "null"]},
                    "confidence": {"type": "number"},
                    "needsReview":{"type": "boolean"},
                    "warnings":   {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

SYSTEM_PROMPT: str = (
    "너는 동대문 장끼(도매 영수증)를 판독하는 전문가다.\n"
    "규칙:\n"
    "1. 상호·도매처는 장끼를 발행한 판매처다. 상단에 별도로 손글씨로 쓰인 화주사명·구매자명은 도매처로 오인하지 않는다.\n"
    "2. 출력일시와 거래일이 함께 있으면 품목 가까이에 표시된 거래일을 orderDate로 사용한다.\n"
    "3. 품명·색상·사이즈·옵션을 가능한 범위에서 분리한다.\n"
    "4. 읽을 수 없는 글자를 추측해 확정하지 않는다. 불명확한 값은 rawText에 원문을 남기고 needsReview=true와 경고를 반환한다.\n"
    "5. unitPrice × quantity = amount 검산. 불일치 시 needsReview=true와 경고.\n"
    '6. 동대문 수기 장끼에서 "9", "18"처럼 천원 단위가 생략된 경우 수량·금액·총액 문맥이 일치하면 9000, 18000으로 정규화하되 '
    'needsReview=true와 "천원 단위 추정" 경고를 남긴다.\n'
    "7. 품목이 보이는데도 빈 배열을 반환하지 않는다. 한 개도 판독하지 못하면 정상 성공으로 처리하지 않는다.\n"
    "반드시 위 JSON Schema를 정확히 따른다."
)


class OcrError(Exception):
    """OCR 파이프라인 분류 오류.

    kind: "no_api_key" | "auth" | "model" | "quota" | "image"
          | "timeout" | "server" | "schema" | "no_items"
    """

    def __init__(self, kind: str, user_msg: str, log_detail: str = ""):
        self.kind = kind
        self.user_msg = user_msg
        self.log_detail = log_detail
        super().__init__(user_msg)


def _normalize_image(raw: bytes) -> tuple:
    """Pillow로 이미지를 디코딩·EXIF 회전·RGB JPEG 변환·2048px 리사이즈.

    반환: (정규화된 JPEG bytes, "image/jpeg")
    실패 시 ValueError 발생 (400으로 매핑됨).
    base64 내용·원본 bytes는 절대 로그에 남기지 않는다.
    """
    _ERR = "이미지를 읽지 못했어요. 사진 방향과 선명도를 확인해 다시 촬영해주세요."
    if not raw:
        raise ValueError(_ERR)
    try:
        buf = io.BytesIO(raw)
        img = Image.open(buf)
        img.verify()          # 포맷 유효성 검사
        buf.seek(0)
        img = Image.open(buf)  # verify() 후 재열기
    except Exception:
        raise ValueError(_ERR)
    try:
        img = ImageOps.exif_transpose(img)  # EXIF 회전 적용
        img = img.convert("RGB")
        w, h = img.size
        max_px = 2048
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf_out = io.BytesIO()
        img.save(buf_out, format="JPEG", quality=90)
        return buf_out.getvalue(), "image/jpeg"
    except Exception:
        raise ValueError(_ERR)


async def _run_ocr(image_bytes: bytes, mime: str) -> dict:
    """GPT Vision Structured Outputs로 장끼 분석.

    성공 시 OCR 결과 dict 반환.
    실패 시 OcrError 발생.
    API 키·Authorization·base64·장끼 전문·개인정보는 절대 로그에 남기지 않는다.
    """
    import httpx  # 지연 import (테스트 패치 용이)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OcrError("no_api_key", "AI 설정을 확인해야 합니다. 관리자에게 알려주세요.")

    b64 = base64.b64encode(image_bytes).decode()
    img_size = len(image_bytes)

    request_payload = {
        "model": OCR_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                }
            ]},
        ],
        "max_tokens": 2000,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "janggi_ocr",
                "strict": True,
                "schema": JANGGI_SCHEMA,
            },
        },
    }
    # Authorization 헤더는 로그에 남기지 않음
    req_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    max_attempts = 2
    t_start = time.monotonic()

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=req_headers,
                    json=request_payload,
                )
        except httpx.TimeoutException:
            elapsed = time.monotonic() - t_start
            if attempt < max_attempts - 1:
                continue  # 1회 재시도
            logger.info(
                "OCR err kind=timeout status=None req_id=None model=%s elapsed=%.1fs img_size=%d",
                OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("timeout", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

        elapsed = time.monotonic() - t_start
        status_code = resp.status_code
        req_id = resp.headers.get("x-request-id", "None")

        if status_code in (401, 403):
            logger.info(
                "OCR err kind=auth status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("auth", "AI 설정을 확인해야 합니다. 관리자에게 알려주세요.")

        if status_code == 404:
            logger.info(
                "OCR err kind=model status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("model", "AI 설정을 확인해야 합니다. 관리자에게 알려주세요.")

        if status_code == 429:
            logger.info(
                "OCR err kind=quota status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("quota", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

        if status_code >= 500:
            if attempt < max_attempts - 1:
                continue  # 1회 재시도
            logger.info(
                "OCR err kind=server status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("server", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

        # Structured Output 파싱
        try:
            resp_json = resp.json()
            content = resp_json["choices"][0]["message"]["content"]
            result = json.loads(content)
            if "receipt" not in result or "items" not in result:
                raise ValueError("required keys missing")
        except Exception:
            logger.info(
                "OCR err kind=schema status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("schema", "이미지를 읽지 못했어요. 사진 방향과 선명도를 확인해 다시 촬영해주세요.")

        items = result.get("items", [])
        if len(items) == 0:
            logger.info(
                "OCR err kind=no_items status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("no_items", "품목을 찾지 못했어요. 다시 촬영하거나 직접 입력해주세요.")

        # 정상 성공 로그 (img_size만, base64·원문 제외)
        try:
            norm_img = Image.open(io.BytesIO(image_bytes))
            nw, nh = norm_img.size
            norm_str = f"{nw}x{nh}"
        except Exception:
            norm_str = "?"
        logger.info(
            "OCR ok  model=%s elapsed=%.1fs items=%d norm=%s",
            OCR_MODEL, elapsed, len(items), norm_str,
        )
        return result

    # 도달 불가 (안전망)
    raise OcrError("server", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

# ── 장끼 OCR + 자동 매칭 ─────────────────

def _ocr_error_to_http(e: OcrError) -> HTTPException:
    """OcrError → HTTPException 매핑."""
    if e.kind in ("no_api_key", "auth", "model", "quota"):
        return HTTPException(status_code=503, detail=e.user_msg)
    if e.kind == "image":
        return HTTPException(status_code=400, detail=e.user_msg)
    if e.kind in ("timeout", "server"):
        return HTTPException(status_code=504, detail=e.user_msg)
    # schema, no_items
    return HTTPException(status_code=422, detail=e.user_msg)


@router.post("/batches/{batch_id}/ocr")
async def run_ocr(
    batch_id: str,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """장끼 이미지 업로드 → OCR → repair_barcode 자동 매칭 → inbound_items 생성.

    실패 시 기존 items, 배치 상태, 장끼 파일을 변경하지 않는다.
    """
    user = _get_user(authorization)

    # 1. 배치 조회
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT id, vendor, status, vendor_canonical FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
    if not batch_row:
        raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
    vendor = batch_row[3] or batch_row[1]  # vendor_canonical 우선

    # 2. 파일 읽기 (임시 — OCR 성공 후에만 저장)
    raw = await file.read()

    # 3. 이미지 정규화 (실패 → 400)
    try:
        norm_bytes, mime = _normalize_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4. OCR 실행 (실패 → 적절한 HTTP 오류, DB 변경 없음)
    try:
        ocr_result = await _run_ocr(norm_bytes, mime)
    except OcrError as e:
        raise _ocr_error_to_http(e)

    # 5. 성공 → 파일 저장 후 트랜잭션 내 기존 OCR 품목 교체
    janggi_filename = f"{uuid.uuid4().hex}.jpg"
    (UPLOAD_DIR / janggi_filename).write_bytes(norm_bytes)

    receipt_data = ocr_result.get("receipt", {})
    items_data = ocr_result.get("items", [])

    wholesale = receipt_data.get("storeName")
    janggi_date = receipt_data.get("orderDate")
    janggi_no = receipt_data.get("receiptNo")

    now = datetime.utcnow().isoformat()
    created_items = []

    with get_connection() as con:
        # 기존 OCR 생성 품목 삭제 (재시도 시 교체)
        con.execute(
            "DELETE FROM inbound_items WHERE batch_id=? AND (memo LIKE '%OCR%' OR memo IS NULL)",
            (batch_id,),
        )

        for i, item in enumerate(items_data):
            item_id = uuid.uuid4().hex
            item_name = item.get("itemName") or ""
            color = item.get("color") or ""
            size_str = item.get("size") or ""
            option_text = item.get("optionText") or ""
            # color / size / optionText 합산
            combined_option = " ".join(filter(None, [color, size_str, option_text])) or None
            unit_price = item.get("unitPrice")
            janggi_qty = int(item.get("quantity") or 0)

            match = _match_barcode(vendor, item_name, combined_option, wholesale)
            needs_review = bool(item.get("needsReview", False))
            needs_matching = match["needs_matching"] or needs_review

            con.execute("""
                INSERT INTO inbound_items
                    (id, batch_id, line_no, item_name, option_text, unit_price,
                     janggi_qty, actual_qty, missing_qty, status,
                     matched_barcode, matched_vendor, matched_product, matched_option,
                     match_confidence, needs_matching, supplier_location, supplier_contact,
                     memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id, batch_id, i + 1, item_name, combined_option, unit_price,
                janggi_qty,
                match["matched_barcode"], match["matched_vendor"],
                match["matched_product"], match["matched_option"],
                match["match_confidence"], int(needs_matching),
                match.get("supplier_location") or "",
                match.get("supplier_contact") or "",
                "OCR", now,
            ))
            # OCR 자동매칭 성공 시 바코드 마스터에 도매처 정보 갱신
            if match.get("matched_barcode") and wholesale:
                _update_barcode_master(
                    con,
                    barcode=match["matched_barcode"],
                    wholesale=wholesale or "",
                    supplier_location=match.get("supplier_location") or "",
                    supplier_contact=match.get("supplier_contact") or "",
                    matched_product=match.get("matched_product") or "",
                    matched_option=match.get("matched_option") or "",
                )
            created_items.append({
                "id": item_id,
                "line_no": i + 1,
                "item_name": item_name,
                "option_text": combined_option,
                "janggi_qty": janggi_qty,
                **match,
            })

        _recalc_batch_totals(con, batch_id)
        con.execute("""
            UPDATE inbound_batches
            SET janggi_filename=?, janggi_date=?, janggi_no=?,
                wholesale=?, status='confirming', updated_at=?
            WHERE id=?
        """, (janggi_filename, janggi_date, janggi_no, wholesale, now, batch_id))
        con.commit()

    matched_count = sum(1 for it in created_items if not it["needs_matching"])
    needs_count = len(created_items) - matched_count

    add_log(
        "inbound", "ocr",
        f"OCR: {vendor} {len(created_items)}개 ({matched_count}매칭/{needs_count}확인필요)",
        user["user_id"],
    )
    return {
        "ok": True,
        "item_count": len(created_items),
        "matched_count": matched_count,
        "needs_matching_count": needs_count,
        "wholesale": wholesale,
        "janggi_date": janggi_date,
        "items": created_items,
    }

# ── OCR 미리보기 (DB 저장 없이 GPT 결과만 반환) ─────────────────

@router.post("/ocr-preview")
async def ocr_preview(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """장끼 이미지를 GPT Vision으로 분석해 품목 목록을 반환. DB·업로드 폴더에 저장하지 않음."""
    _get_user(authorization)

    raw = await file.read()

    try:
        norm_bytes, mime = _normalize_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await _run_ocr(norm_bytes, mime)
    except OcrError as e:
        raise _ocr_error_to_http(e)

    return {
        "ok": True,
        "receipt": result.get("receipt", {}),
        "items": result.get("items", []),
        "raw": result,
    }
