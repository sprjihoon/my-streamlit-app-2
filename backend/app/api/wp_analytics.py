"""
backend/app/api/wp_analytics.py - WordPress 사이트 방문자 분석 API
────────────────────────────────────────────────────────
estimate_visitor_logs 테이블에서 spring3pl.co.kr 페이지 데이터를 필터링하여 분석.
WPCode 스니펫이 /estimate-analytics/visit 로 데이터를 전송하므로
page_url 기준으로 WordPress 페이지만 추출.
"""

from typing import List, Any, Optional
from fastapi import APIRouter, Query
from fastapi import HTTPException

from logic.db import get_connection

router = APIRouter(prefix="/wp-analytics", tags=["wp-analytics"])

WP_DOMAIN = "spring3pl.co.kr"


def _where_wp(extra: str = "") -> str:
    """WordPress 도메인 필터 + 날짜 필터 조합용 WHERE 절 베이스"""
    base = f"page_url LIKE '%{WP_DOMAIN}%'"
    if extra:
        base += f" AND {extra}"
    return base


@router.get("/stats")
async def get_wp_stats(
    date_from: Optional[str] = Query(None, description="시작일 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="종료일 YYYY-MM-DD"),
):
    """
    WordPress 전체 사이트 방문 통계.
    페이지별, 유입경로, 디바이스, OS, 브라우저, 시간대, 지역, UTM 등.
    """
    try:
        with get_connection() as con:
            where = f"page_url LIKE '%{WP_DOMAIN}%'"
            params: List[Any] = []

            if date_from:
                where += " AND date(created_at) >= ?"
                params.append(date_from)
            if date_to:
                where += " AND date(created_at) <= ?"
                params.append(date_to)

            # ── 요약 ──────────────────────────────────────────────
            total_visits = con.execute(
                f"SELECT COUNT(*) FROM estimate_visitor_logs WHERE {where}", params
            ).fetchone()[0]

            unique_visitors = con.execute(
                f"SELECT COUNT(DISTINCT ip_address) FROM estimate_visitor_logs WHERE {where}", params
            ).fetchone()[0]

            touch = con.execute(
                f"""
                SELECT
                    SUM(CASE WHEN is_mobile = 1 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN is_touch_device = 1 THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM estimate_visitor_logs WHERE {where}
                """,
                params,
            ).fetchone()

            dwell = con.execute(
                f"""
                SELECT
                    AVG(duration_seconds),
                    MAX(duration_seconds),
                    COUNT(CASE WHEN duration_seconds > 0 THEN 1 END)
                FROM estimate_visitor_logs
                WHERE {where} AND duration_seconds > 0
                """,
                params,
            ).fetchone()

            # ── 페이지별 방문 TOP 20 ─────────────────────────────
            page_stats = con.execute(
                f"""
                SELECT
                    page_url,
                    COUNT(*) as cnt,
                    COUNT(DISTINCT ip_address) as unique_cnt,
                    AVG(CASE WHEN duration_seconds > 0 THEN duration_seconds END) as avg_dur
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY page_url
                ORDER BY cnt DESC
                LIMIT 20
                """,
                params,
            ).fetchall()

            # ── 접속 경로 (UTM 우선, 없으면 referrer 파싱) ───────
            referrer_stats = con.execute(
                f"""
                SELECT
                    CASE
                        WHEN utm_source IS NOT NULL AND utm_source != '' THEN
                            CASE
                                WHEN LOWER(utm_source) = 'instagram' THEN 'Instagram'
                                WHEN LOWER(utm_source) = 'youtube' THEN 'YouTube'
                                WHEN LOWER(utm_source) = 'naver' THEN 'Naver'
                                WHEN LOWER(utm_source) = 'google' THEN 'Google'
                                WHEN LOWER(utm_source) = 'facebook' THEN 'Facebook'
                                WHEN LOWER(utm_source) IN ('kakao','kakaotalk') THEN 'KakaoTalk'
                                WHEN LOWER(utm_source) = 'tiktok' THEN 'TikTok'
                                WHEN LOWER(utm_source) IN ('twitter','x') THEN 'X(Twitter)'
                                ELSE utm_source
                            END
                        WHEN referrer IS NULL OR referrer = '' THEN '직접 접속'
                        WHEN referrer LIKE '%google%' THEN 'Google'
                        WHEN referrer LIKE '%naver%' THEN 'Naver'
                        WHEN referrer LIKE '%daum%' THEN 'Daum'
                        WHEN referrer LIKE '%youtube%' THEN 'YouTube'
                        WHEN referrer LIKE '%instagram%' THEN 'Instagram'
                        WHEN referrer LIKE '%facebook%' THEN 'Facebook'
                        WHEN referrer LIKE '%kakao%' THEN 'KakaoTalk'
                        WHEN referrer LIKE '%tiktok%' THEN 'TikTok'
                        WHEN referrer LIKE '%twitter%' OR referrer LIKE '%x.com%' THEN 'X(Twitter)'
                        WHEN referrer LIKE '%spring3pl%' THEN '사이트 내 이동'
                        ELSE '기타'
                    END as source,
                    COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY source ORDER BY cnt DESC LIMIT 15
                """,
                params,
            ).fetchall()

            # ── OS / 브라우저 / 디바이스 ─────────────────────────
            os_stats = con.execute(
                f"""
                SELECT os, COUNT(*) as cnt FROM estimate_visitor_logs
                WHERE {where} AND os IS NOT NULL AND os != ''
                GROUP BY os ORDER BY cnt DESC
                """,
                params,
            ).fetchall()

            browser_stats = con.execute(
                f"""
                SELECT browser, COUNT(*) as cnt FROM estimate_visitor_logs
                WHERE {where} AND browser IS NOT NULL AND browser != ''
                GROUP BY browser ORDER BY cnt DESC
                """,
                params,
            ).fetchall()

            device_stats = con.execute(
                f"""
                SELECT device_type, COUNT(*) as cnt FROM estimate_visitor_logs
                WHERE {where} AND device_type IS NOT NULL AND device_type != ''
                GROUP BY device_type ORDER BY cnt DESC
                """,
                params,
            ).fetchall()

            # ── 시간대별 ─────────────────────────────────────────
            hourly_stats = con.execute(
                f"""
                SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY hour ORDER BY hour
                """,
                params,
            ).fetchall()

            # ── 요일별 ───────────────────────────────────────────
            weekday_stats = con.execute(
                f"""
                SELECT
                    CASE strftime('%w', created_at)
                        WHEN '0' THEN '일'
                        WHEN '1' THEN '월'
                        WHEN '2' THEN '화'
                        WHEN '3' THEN '수'
                        WHEN '4' THEN '목'
                        WHEN '5' THEN '금'
                        WHEN '6' THEN '토'
                    END as weekday,
                    strftime('%w', created_at) as wday_num,
                    COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY wday_num ORDER BY wday_num
                """,
                params,
            ).fetchall()

            # ── 지역별 ───────────────────────────────────────────
            location_stats = con.execute(
                f"""
                SELECT
                    CASE
                        WHEN city IS NOT NULL AND city != '' THEN city
                        WHEN region IS NOT NULL AND region != '' THEN region
                        WHEN country IS NOT NULL AND country != '' THEN country
                        ELSE '알 수 없음'
                    END as location,
                    COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY location ORDER BY cnt DESC LIMIT 10
                """,
                params,
            ).fetchall()

            # ── 일별 추이 (최근 30일) ─────────────────────────────
            daily_visits = con.execute(
                f"""
                SELECT date(created_at) as day, COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY day ORDER BY day DESC LIMIT 30
                """,
                params,
            ).fetchall()

            # ── UTM 캠페인 ────────────────────────────────────────
            utm_stats = con.execute(
                f"""
                SELECT utm_source, utm_medium, utm_campaign, COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where} AND utm_source IS NOT NULL AND utm_source != ''
                GROUP BY utm_source, utm_medium, utm_campaign
                ORDER BY cnt DESC LIMIT 20
                """,
                params,
            ).fetchall()

            return {
                "summary": {
                    "total_visits": total_visits,
                    "unique_visitors": unique_visitors,
                    "mobile_count": int(touch[0] or 0) if touch else 0,
                    "touch_count": int(touch[1] or 0) if touch else 0,
                    "mobile_rate": round((touch[0] or 0) / touch[2] * 100, 1) if touch and touch[2] > 0 else 0,
                    "avg_duration_seconds": int(dwell[0]) if dwell and dwell[0] else 0,
                    "max_duration_seconds": int(dwell[1]) if dwell and dwell[1] else 0,
                    "tracked_visit_count": int(dwell[2]) if dwell and dwell[2] else 0,
                },
                "page_stats": [
                    {
                        "page_url": r[0],
                        "count": r[1],
                        "unique_count": r[2],
                        "avg_duration": int(r[3]) if r[3] else 0,
                    }
                    for r in page_stats
                ],
                "referrer_stats": [{"source": r[0], "count": r[1]} for r in referrer_stats],
                "os_stats": [{"os": r[0], "count": r[1]} for r in os_stats],
                "browser_stats": [{"browser": r[0], "count": r[1]} for r in browser_stats],
                "device_stats": [{"device": r[0], "count": r[1]} for r in device_stats],
                "hourly_stats": [{"hour": r[0], "count": r[1]} for r in hourly_stats],
                "weekday_stats": [{"weekday": r[0], "count": r[2]} for r in weekday_stats],
                "location_stats": [{"location": r[0], "count": r[1]} for r in location_stats],
                "daily_visits": [{"date": r[0], "count": r[1]} for r in daily_visits],
                "utm_stats": [
                    {
                        "source": r[0],
                        "medium": r[1] or "",
                        "campaign": r[2] or "",
                        "count": r[3],
                    }
                    for r in utm_stats
                ],
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visitors")
async def list_wp_visitors(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_filter: Optional[str] = Query(None, description="유입경로 필터"),
):
    """
    WordPress 방문자 로그 목록 (페이지네이션).
    """
    try:
        with get_connection() as con:
            where = f"page_url LIKE '%{WP_DOMAIN}%'"
            params: List[Any] = []

            if date_from:
                where += " AND date(created_at) >= ?"
                params.append(date_from)
            if date_to:
                where += " AND date(created_at) <= ?"
                params.append(date_to)

            total = con.execute(
                f"SELECT COUNT(*) FROM estimate_visitor_logs WHERE {where}", params
            ).fetchone()[0]

            offset = (page - 1) * page_size
            rows = con.execute(
                f"""
                SELECT id, ip_address, country, region, city, page_url, referrer,
                       os, browser, device_type, screen_width, screen_height,
                       language, timezone, session_id, created_at,
                       is_touch_device, is_mobile, inner_width, inner_height,
                       utm_source, utm_medium, utm_campaign, duration_seconds
                FROM estimate_visitor_logs
                WHERE {where}
                ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                params + [page_size, offset],
            ).fetchall()

            items = [
                {
                    "id": r[0],
                    "ip_address": r[1],
                    "country": r[2],
                    "region": r[3],
                    "city": r[4],
                    "page_url": r[5],
                    "referrer": r[6],
                    "os": r[7],
                    "browser": r[8],
                    "device_type": r[9],
                    "screen_width": r[10],
                    "screen_height": r[11],
                    "language": r[12],
                    "timezone": r[13],
                    "session_id": r[14],
                    "created_at": str(r[15]) if r[15] else "",
                    "is_touch_device": bool(r[16]) if r[16] is not None else None,
                    "is_mobile": bool(r[17]) if r[17] is not None else None,
                    "inner_width": r[18],
                    "inner_height": r[19],
                    "utm_source": r[20],
                    "utm_medium": r[21],
                    "utm_campaign": r[22],
                    "duration_seconds": r[23] or 0,
                }
                for r in rows
            ]

            return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
