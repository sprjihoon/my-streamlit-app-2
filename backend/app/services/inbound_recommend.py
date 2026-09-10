"""
backend/app/services/inbound_recommend.py
──────────────────────────────────────────
입고 품목 상품 추천 서비스 (인터페이스 기반)

설계 원칙:
  - 바코드 완전 일치 + 충돌 없는 경우에만 자동선택
  - 이미지 유사도·AI 판단만으로는 절대 자동 확정 안 함 (후보만 반환)
  - 이미지 특징값 기능이 없으면 NullFeatureProvider로 안전하게 fallback
  - 모델 교체가 가능하도록 provider 인터페이스로 분리
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from logic.db import get_connection

logger = logging.getLogger(__name__)


# ─────────────────────────────────────
# Provider 인터페이스
# ─────────────────────────────────────

class FeatureProvider(ABC):
    """이미지 특징값 추출 provider 인터페이스."""

    @abstractmethod
    def extract(self, image_data: bytes) -> Optional[List[float]]:
        """이미지에서 특징 벡터를 추출한다. 지원 불가이면 None을 반환."""
        ...

    @abstractmethod
    def similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """두 벡터의 유사도를 [0, 1] 범위로 반환."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


class NullFeatureProvider(FeatureProvider):
    """
    이미지 특징값 미구현 fallback.
    향후 실제 provider(clip, openai embedding 등)로 교체 가능.
    """

    def extract(self, image_data: bytes) -> Optional[List[float]]:
        return None

    def similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        return 0.0

    @property
    def provider_name(self) -> str:
        return "none"


class MultimodalComparator(ABC):
    """멀티모달 모델 최종 비교 인터페이스."""

    @abstractmethod
    async def compare(
        self,
        query_image: bytes,
        candidates: List[Dict],
    ) -> List[Dict]:
        """후보 목록을 멀티모달 모델로 비교해 순위를 조정한다. 자동 확정 금지."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...


class NullMultimodalComparator(MultimodalComparator):
    """멀티모달 비교 미구현 fallback — 순위 변경 없이 그대로 반환."""

    async def compare(
        self,
        query_image: bytes,
        candidates: List[Dict],
    ) -> List[Dict]:
        return candidates

    @property
    def model_name(self) -> str:
        return "none"


# ─────────────────────────────────────
# 기본 provider 설정 (환경에 따라 교체 가능)
# ─────────────────────────────────────

_feature_provider: FeatureProvider = NullFeatureProvider()
_multimodal_comparator: MultimodalComparator = NullMultimodalComparator()


def set_feature_provider(provider: FeatureProvider) -> None:
    global _feature_provider
    _feature_provider = provider


def set_multimodal_comparator(comparator: MultimodalComparator) -> None:
    global _multimodal_comparator
    _multimodal_comparator = comparator


def get_feature_provider() -> FeatureProvider:
    return _feature_provider


def get_multimodal_comparator() -> MultimodalComparator:
    return _multimodal_comparator


# ─────────────────────────────────────
# 추천 로직
# ─────────────────────────────────────

class RecommendResult:
    """추천 결과."""

    def __init__(
        self,
        candidates: List[Dict],
        auto_selected: Optional[Dict] = None,
        auto_select_reason: str = "",
    ):
        self.candidates = candidates          # 후보 목록 (최대 3개)
        self.auto_selected = auto_selected    # 자동 선택된 경우만 채워짐
        self.auto_select_reason = auto_select_reason

    def to_dict(self) -> Dict:
        return {
            "candidates": self.candidates,
            "auto_selected": self.auto_selected,
            "auto_select_reason": self.auto_select_reason,
        }


def recommend_product(
    vendor: str,
    wholesale: Optional[str],
    item_name: Optional[str],
    option_text: Optional[str],
    barcode: Optional[str],
    *,
    limit: int = 3,
) -> RecommendResult:
    """
    바코드·화주사·상품명·옵션 기반 상품 추천.

    자동 선택 조건:
      - 바코드 완전 일치
      - AND 화주사 불일치가 없음 (barcode가 다른 화주사에 등록돼 있지 않음)

    나머지는 후보만 반환.
    """
    candidates: List[Dict] = []
    auto_selected: Optional[Dict] = None
    auto_reason = ""

    with get_connection() as con:
        # 1. 바코드 완전 일치
        if barcode:
            row = con.execute(
                """SELECT 바코드, 업체명, 제품명, 옵션, 도매처
                   FROM repair_barcode WHERE 바코드=? LIMIT 1""",
                (barcode,)
            ).fetchone()
            if row:
                bc, vendor_db, product, option, ws = row
                candidate = {
                    "barcode": bc,
                    "vendor": vendor_db,
                    "product": product,
                    "option": option,
                    "wholesale": ws,
                    "match_type": "barcode_exact",
                    "confidence": 1.0,
                }
                candidates.append(candidate)
                # 자동 선택: 바코드 일치 + 화주사 충돌 없음
                if not vendor or not vendor_db or vendor_db == vendor:
                    auto_selected = candidate
                    auto_reason = "바코드 완전 일치"

        if auto_selected:
            return RecommendResult(candidates[:limit], auto_selected, auto_reason)

        # 2. 화주사 + 도매처 일치
        if vendor and wholesale:
            rows = con.execute(
                """SELECT 바코드, 업체명, 제품명, 옵션, 도매처
                   FROM repair_barcode
                   WHERE 업체명=? AND 도매처=?
                   LIMIT ?""",
                (vendor, wholesale, limit * 2)
            ).fetchall()
            for r in rows:
                c = {
                    "barcode": r[0], "vendor": r[1],
                    "product": r[2], "option": r[3], "wholesale": r[4],
                    "match_type": "vendor_wholesale",
                    "confidence": 0.7,
                }
                if c not in candidates:
                    candidates.append(c)

        # 3. 상품명 유사도 (단순 부분 일치)
        if item_name and len(candidates) < limit:
            search = f"%{item_name}%"
            rows = con.execute(
                """SELECT 바코드, 업체명, 제품명, 옵션, 도매처
                   FROM repair_barcode
                   WHERE 제품명 LIKE ? AND 업체명=?
                   LIMIT ?""",
                (search, vendor, limit)
            ).fetchall()
            for r in rows:
                c = {
                    "barcode": r[0], "vendor": r[1],
                    "product": r[2], "option": r[3], "wholesale": r[4],
                    "match_type": "name_partial",
                    "confidence": 0.5,
                }
                if not any(x["barcode"] == c["barcode"] for x in candidates):
                    candidates.append(c)

        # 4. 상품사진 사전 추가 후보 (확정 연결 기반)
        if len(candidates) < limit and barcode is None and item_name:
            try:
                dict_rows = con.execute(
                    """SELECT DISTINCT d.barcode, d.vendor, d.wholesale_product, d.option_text, d.wholesale
                       FROM product_photo_dict d
                       WHERE d.vendor=? AND d.wholesale_product LIKE ?
                       LIMIT ?""",
                    (vendor, f"%{item_name}%", limit)
                ).fetchall()
                for r in dict_rows:
                    c = {
                        "barcode": r[0], "vendor": r[1],
                        "product": r[2], "option": r[3], "wholesale": r[4],
                        "match_type": "photo_dict",
                        "confidence": 0.6,
                    }
                    if not any(x["barcode"] == c["barcode"] for x in candidates):
                        candidates.append(c)
            except Exception:
                pass  # product_photo_dict 없을 때 무시

    return RecommendResult(candidates[:limit])


async def recommend_with_image(
    vendor: str,
    wholesale: Optional[str],
    item_name: Optional[str],
    option_text: Optional[str],
    barcode: Optional[str],
    query_image: Optional[bytes] = None,
    *,
    limit: int = 3,
) -> RecommendResult:
    """
    이미지 특징값 유사도 + 멀티모달 비교를 포함한 추천.
    특징값 provider가 None이면 텍스트 기반 추천만 수행.
    이미지 유사도·AI 판단만으로는 자동 확정 금지.
    """
    base = recommend_product(vendor, wholesale, item_name, option_text, barcode, limit=limit)
    if base.auto_selected:
        return base

    candidates = base.candidates

    # 이미지 특징값 유사도 (현재 NullProvider → 건너뜀)
    provider = get_feature_provider()
    if query_image and provider.provider_name != "none":
        query_vec = provider.extract(query_image)
        if query_vec:
            for c in candidates:
                feat_row = _load_feature(c["barcode"])
                if feat_row:
                    sim = provider.similarity(query_vec, feat_row)
                    c["image_similarity"] = round(sim, 4)
            candidates.sort(key=lambda x: x.get("image_similarity", 0), reverse=True)

    # 멀티모달 최종 비교 (현재 NullComparator → 순위 변경 없음)
    if query_image and candidates:
        comparator = get_multimodal_comparator()
        if comparator.model_name != "none":
            candidates = await comparator.compare(query_image, candidates)

    return RecommendResult(candidates[:limit])


def _load_feature(barcode: Optional[str]) -> Optional[List[float]]:
    if not barcode:
        return None
    try:
        with get_connection() as con:
            row = con.execute(
                "SELECT feature_vector FROM product_image_features WHERE barcode=? LIMIT 1",
                (barcode,)
            ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
    except Exception:
        pass
    return None


# ─────────────────────────────────────
# 특징값 저장
# ─────────────────────────────────────

def save_feature(barcode: str, photo_filename: str, vector: List[float]) -> None:
    """이미지 특징값을 DB에 저장한다."""
    from backend.app.api.inbound import ensure_inbound_tables
    ensure_inbound_tables()

    provider = get_feature_provider()
    now = __import__("datetime").datetime.utcnow().isoformat()
    with get_connection() as con:
        con.execute("""
            INSERT INTO product_image_features
                (barcode, photo_filename, feature_vector, provider, computed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(barcode, photo_filename) DO UPDATE SET
                feature_vector=excluded.feature_vector,
                provider=excluded.provider,
                computed_at=excluded.computed_at
        """, (barcode, photo_filename, json.dumps(vector), provider.provider_name, now))
        con.commit()


# ─────────────────────────────────────
# Backfill 명령 (dry-run 지원)
# ─────────────────────────────────────

def backfill_features(
    *,
    dry_run: bool = True,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    기존 상품사진 사전의 사진들로 특징값을 일괄 생성한다.
    - dry_run=True(기본): 실제 실행 없이 대상 목록만 반환
    - dry_run=False: 실제 실행 (provider가 none이면 0건 처리)
    """
    provider = get_feature_provider()
    if provider.provider_name == "none":
        return {
            "status": "skipped",
            "reason": "현재 이미지 특징값 provider가 설정되지 않았습니다. "
                      "FeatureProvider 구현체를 set_feature_provider()로 등록한 뒤 실행해주세요.",
            "dry_run": dry_run,
            "processed": 0,
        }

    try:
        from backend.app.api.inbound import UPLOAD_DIR
        with get_connection() as con:
            rows = con.execute(
                """SELECT d.barcode, d.photo_filename
                   FROM product_photo_dict d
                   LEFT JOIN product_image_features f
                     ON d.barcode = f.barcode AND d.photo_filename = f.photo_filename
                   WHERE f.barcode IS NULL AND d.barcode IS NOT NULL
                   LIMIT ?""",
                (limit,)
            ).fetchall()
    except Exception as e:
        return {"status": "error", "reason": str(e), "processed": 0}

    targets = [{"barcode": r[0], "photo": r[1]} for r in rows]
    if dry_run:
        return {
            "status": "dry_run",
            "pending": len(targets),
            "targets": targets[:10],  # 미리보기 최대 10건
            "dry_run": True,
        }

    processed, failed = 0, 0
    for t in targets:
        try:
            photo_path = UPLOAD_DIR / t["photo"]
            if not photo_path.exists():
                failed += 1
                continue
            vec = provider.extract(photo_path.read_bytes())
            if vec:
                save_feature(t["barcode"], t["photo"], vec)
                processed += 1
        except Exception as err:
            logger.warning("backfill_features 오류: %s — %s", t["photo"], err)
            failed += 1

    return {
        "status": "done",
        "processed": processed,
        "failed": failed,
        "dry_run": False,
    }
