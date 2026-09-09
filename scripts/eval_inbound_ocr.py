"""
scripts/eval_inbound_ocr.py – 입고 OCR 품질 평가 스크립트

사용법:
    python scripts/eval_inbound_ocr.py --image <로컬사진경로>

조건:
- 프로세스 환경의 OPENAI_API_KEY만 사용
- DB 저장 없음
- 업로드 폴더에 파일을 남기지 않음
- API 키·base64 출력 금지
- 판독 JSON, 모델, 지연시간, 검산 결과만 출력
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


async def _eval(image_path: Path) -> None:
    """이미지를 정규화 → OCR → 결과 출력."""
    # 지연 import (sys.path 설정 후)
    from backend.app.api.inbound import (
        OCR_MODEL,
        OcrError,
        _normalize_image,
        _run_ocr,
    )

    raw = image_path.read_bytes()
    print(f"[원본] 파일: {image_path.name}  크기: {len(raw):,} bytes")

    try:
        norm_bytes, mime = _normalize_image(raw)
    except ValueError as e:
        print(f"[오류] 이미지 정규화 실패: {e}")
        sys.exit(1)

    from PIL import Image
    import io
    norm_img = Image.open(io.BytesIO(norm_bytes))
    print(f"[정규화] {norm_img.size[0]}x{norm_img.size[1]}  {mime}  {len(norm_bytes):,} bytes")
    print(f"[모델] {OCR_MODEL}")
    print("OCR 요청 중...")

    t0 = time.monotonic()
    try:
        result = await _run_ocr(norm_bytes, mime)
    except OcrError as e:
        elapsed = time.monotonic() - t0
        print(f"[오류] kind={e.kind}  elapsed={elapsed:.1f}s")
        print(f"       사용자 메시지: {e.user_msg}")
        sys.exit(1)

    elapsed = time.monotonic() - t0
    print(f"[완료] 지연시간: {elapsed:.1f}s")
    print()

    receipt = result.get("receipt", {})
    items = result.get("items", [])

    print("── 영수증 헤더 ──────────────────────")
    print(f"  도매처    : {receipt.get('storeName')}")
    print(f"  영수증번호: {receipt.get('receiptNo')}")
    print(f"  거래일    : {receipt.get('orderDate')}")
    print(f"  총금액    : {receipt.get('totalAmount')}")
    print(f"  수기여부  : {receipt.get('isHandwritten')}")
    print(f"  신뢰도    : {receipt.get('confidence')}")
    print(f"  검토필요  : {receipt.get('needsReview')}")
    if receipt.get("warnings"):
        print(f"  경고      : {receipt['warnings']}")
    print()

    print(f"── 품목 ({len(items)}개) ─────────────────────")
    for item in items:
        check = "✓" if _calc_ok(item) else "⚠"
        print(
            f"  {check} {item.get('lineNo'):>2}. "
            f"{item.get('itemName')} "
            f"[{item.get('color') or '-'}/{item.get('size') or '-'}] "
            f"  단가={item.get('unitPrice')}  수량={item.get('quantity')}  금액={item.get('amount')}"
        )
        if item.get("needsReview"):
            print(f"       ⚠ needsReview  warnings={item.get('warnings')}")
    print()

    # 검산
    total_from_items = sum(
        (it.get("amount") or 0) for it in items
    )
    receipt_total = receipt.get("totalAmount")
    if receipt_total is not None:
        match = "✓ 일치" if abs(total_from_items - receipt_total) < 1 else f"⚠ 차이 {total_from_items - receipt_total:+.0f}"
        print(f"[검산] 품목합계={total_from_items}  영수증총액={receipt_total}  → {match}")
    else:
        print(f"[검산] 품목합계={total_from_items}  영수증총액=없음")

    print()
    print("── 원시 JSON ────────────────────────")
    # API 키·base64 미포함 보장 (result에는 원래 없음)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _calc_ok(item: dict) -> bool:
    """unitPrice × quantity ≈ amount 검산."""
    up = item.get("unitPrice")
    qty = item.get("quantity")
    amt = item.get("amount")
    if up is None or qty is None or amt is None:
        return True  # 검산 불가 → 통과
    return abs(up * qty - amt) < 1


def main() -> None:
    parser = argparse.ArgumentParser(description="입고 OCR 평가 스크립트")
    parser.add_argument("--image", required=True, help="분석할 장끼 이미지 경로")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"파일을 찾을 수 없습니다: {image_path}")
        sys.exit(1)

    asyncio.run(_eval(image_path))


if __name__ == "__main__":
    main()
