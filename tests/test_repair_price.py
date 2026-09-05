"""수선 비용 제안: 제품+작업을 업체+작업보다 우선한다."""
from backend.app.api.repair_log import insert_repair_log_record
from backend.app.services.repair_catalog import lookup_repair_price


def _log(product: str, work: str, cost: int, vendor="로지킴"):
    return insert_repair_log_record(
        날짜="2026-09-05",
        작업=work,
        비용=cost,
        업체명=vendor,
        제품명=product,
        작성자="테스터",
        출처="bot",
    )


def test_prefers_same_product_over_other_product_at_vendor():
    _log("릴리프T", "단순바느질", 1500)
    _log("후드집업", "단순바느질", 2500)
    hit = lookup_repair_price("로지킴", "바느질", "릴리프T")
    assert hit["found"] is True
    assert hit["source"] == "product_history"
    assert hit["비용"] == 1500


def test_falls_back_to_vendor_work_when_product_has_no_history():
    _log("후드집업", "스팀작업", 900)
    hit = lookup_repair_price("로지킴", "스팀", "릴리프T")
    assert hit["found"] is True
    assert hit["source"] == "vendor_history"
    assert hit["비용"] == 900


def test_falls_back_to_default_when_no_history():
    hit = lookup_repair_price("없는업체", "단순바느질", "없는제품")
    assert hit["found"] is True
    assert hit["source"] == "default"
    assert hit["비용"] == 1500
