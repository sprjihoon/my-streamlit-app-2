"""
backend/app/services/inbound_photo_dict.py
────────────────────────────────────────────
상품사진 사전 서비스

원칙:
  - 직원이 직접 확정한 연결만 등록
  - AI 추천 결과 자체는 학습자료로 등록하지 않음
  - 상품별 대표사진은 압축본 최대 3장까지 유지
  - 기존 사진을 임의 삭제하지 않고 교체 이력 남김
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from logic.db import get_connection

logger = logging.getLogger(__name__)

_MAX_REPRESENTATIVE = 3


def confirm_photo_link(
    *,
    photo_filename: str,
    item_id: Optional[str] = None,
    barcode: Optional[str] = None,
    vendor: Optional[str] = None,
    wholesale: Optional[str] = None,
    wholesale_product: Optional[str] = None,
    sales_product: Optional[str] = None,
    option_text: Optional[str] = None,
    confirmed_by: str = "system",
    quality_score: float = 0.0,
    is_representative: bool = False,
) -> Dict[str, Any]:
    """
    직원이 확정한 사진-품목 연결을 상품사진 사전에 등록한다.
    같은 (photo_filename, barcode) 조합은 idempotent하게 처리한다.
    """
    from backend.app.api.inbound import ensure_inbound_tables
    ensure_inbound_tables()

    now = datetime.utcnow().isoformat()
    with get_connection() as con:
        # 중복 확인
        existing = con.execute(
            "SELECT id FROM product_photo_dict WHERE photo_filename=? AND (barcode=? OR (barcode IS NULL AND ? IS NULL))",
            (photo_filename, barcode, barcode)
        ).fetchone()
        if existing:
            return {"status": "already_exists", "id": existing[0]}

        # 대표사진 수 확인 (3장 초과 시 교체 이력 기록 후 비대표로 강등)
        if is_representative and barcode:
            rep_rows = con.execute(
                "SELECT id FROM product_photo_dict WHERE barcode=? AND is_representative=1 ORDER BY confirmed_at",
                (barcode,)
            ).fetchall()
            if len(rep_rows) >= _MAX_REPRESENTATIVE:
                # 가장 오래된 대표사진 비대표로 강등 + 이력 기록
                oldest_id = rep_rows[0][0]
                con.execute(
                    "UPDATE product_photo_dict SET is_representative=0, replaced_at=?, replace_reason=? WHERE id=?",
                    (now, "대표사진 3장 초과로 비대표 강등", oldest_id)
                )

        entry_id = uuid.uuid4().hex
        con.execute("""
            INSERT INTO product_photo_dict
                (id, photo_filename, item_id, barcode, vendor, wholesale,
                 wholesale_product, sales_product, option_text,
                 confirmed_by, confirmed_at, is_representative, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id, photo_filename, item_id, barcode, vendor, wholesale,
            wholesale_product, sales_product, option_text,
            confirmed_by, now,
            1 if is_representative else 0,
            quality_score,
        ))
        con.commit()

    return {"status": "created", "id": entry_id}


def get_representative_photos(barcode: str) -> List[Dict]:
    """바코드에 연결된 대표사진 목록 (최대 3장)."""
    try:
        with get_connection() as con:
            rows = con.execute(
                """SELECT id, photo_filename, quality_score, confirmed_at
                   FROM product_photo_dict
                   WHERE barcode=? AND is_representative=1
                   ORDER BY quality_score DESC, confirmed_at DESC
                   LIMIT ?""",
                (barcode, _MAX_REPRESENTATIVE)
            ).fetchall()
        return [{"id": r[0], "filename": r[1], "quality_score": r[2], "confirmed_at": r[3]} for r in rows]
    except Exception:
        return []


# ─────────────────────────────────────
# 보관정책 정리 작업
# ─────────────────────────────────────

def cleanup_product_photos(
    *,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    상품사진 사전의 교체 이력이 있는 비대표 사진 정리.
    dry_run=True(기본): 대상만 반환, 실제 삭제 없음.
    """
    try:
        with get_connection() as con:
            targets = con.execute(
                """SELECT id, photo_filename, replaced_at
                   FROM product_photo_dict
                   WHERE is_representative=0 AND replaced_at IS NOT NULL"""
            ).fetchall()
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    if dry_run:
        return {
            "status": "dry_run",
            "pending_count": len(targets),
            "samples": [{"id": r[0], "filename": r[1]} for r in targets[:5]],
        }

    # 실제 삭제는 파일 삭제 없이 is_deleted 마킹만 (파일은 별도 스케줄러가 처리)
    with get_connection() as con:
        for r in targets:
            con.execute(
                "UPDATE product_photo_dict SET is_representative=-1 WHERE id=?",
                (r[0],)
            )
        con.commit()

    return {"status": "done", "marked": len(targets)}


def inbound_photo_cleanup_plan(
    *,
    dry_run: bool = True,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """
    입고 제품사진 보관정책 계산:
      - 입고 마감 후 30일: 제품 원본 사진 삭제 대상
      - 미연결 사진: 7일 후 삭제 대상
      - 장끼 사진: 장기 보관 (삭제 안 함)
      - 불량·수선 사진: 장기 보관 (삭제 안 함)

    dry_run=True(기본): 대상 목록만 반환, 실제 삭제 없음.
    """
    if today is None:
        today = datetime.utcnow().strftime("%Y-%m-%d")

    plan: Dict[str, Any] = {"dry_run": dry_run, "date_basis": today, "categories": {}}

    try:
        with get_connection() as con:
            # 1. 입고 마감 후 30일이 지난 배치의 원본 제품사진
            expired_batches = con.execute(
                """SELECT id, vendor, closed_at
                   FROM inbound_batches
                   WHERE status IN ('done', 'inbound_done')
                     AND closed_at IS NOT NULL
                     AND DATE(closed_at, '+30 days') < ?""",
                (today,)
            ).fetchall()
            plan["categories"]["product_photos_30d"] = {
                "description": "입고 마감 후 30일 경과 — 원본 제품사진",
                "batch_count": len(expired_batches),
                "batch_ids": [r[0] for r in expired_batches],
            }

            # 2. 미연결 inbox 사진 7일 경과
            #    ◆ item_id IS NULL: 직접 연결 없음
            #    ◆ inbound_item_photos 에도 없음: from-inbox 공유 연결도 없음
            #    → 두 조건 모두 충족해야 삭제 후보
            unlinked = con.execute(
                """SELECT inp.id, inp.stored_filename, inp.created_at
                   FROM inbound_product_photo_inbox inp
                   WHERE inp.item_id IS NULL
                     AND inp.is_deleted = 0
                     AND DATE(inp.created_at, '+7 days') < ?
                     AND NOT EXISTS (
                         SELECT 1 FROM inbound_item_photos iip
                         WHERE iip.filename = inp.stored_filename
                     )""",
                (today,)
            ).fetchall()
            plan["categories"]["unlinked_inbox_7d"] = {
                "description": "미연결 inbox 사진 7일 경과 (품목연결 없음)",
                "count": len(unlinked),
                "sample_filenames": [r[1] for r in unlinked[:5]],
            }

    except Exception as e:
        plan["error"] = str(e)

    if dry_run:
        plan["action"] = "dry_run — 실제 파일/DB는 변경되지 않음"
    else:
        plan["action"] = "실행 모드 — 실제 적용은 배포 환경의 스케줄러에서만 수행"
        plan["warning"] = "이 함수는 실제 삭제를 실행하지 않습니다. 별도 스케줄러 구현 후 연결하세요."

    return plan
