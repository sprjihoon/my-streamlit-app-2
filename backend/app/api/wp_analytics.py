"""
backend/app/api/wp_analytics.py - WordPress 사이트 방문자 분석 API
────────────────────────────────────────────────────────
estimate_visitor_logs 테이블에서 spring3pl.co.kr 페이지 데이터를 필터링하여 분석.
WPCode 스니펫이 /estimate-analytics/visit 로 데이터를 전송하므로
page_url 기준으로 WordPress 페이지만 추출.
"""

from typing import List, Any, Optional
from fastapi import APIRouter, Query, HTTPException

from logic.db import get_connection

router = APIRouter(prefix="/wp-analytics", tags=["wp-analytics"])

WP_DOMAIN = "spring3pl.co.kr"


def _ensure_columns(con):
    """estimate_visitor_logs에 필요한 컬럼이 없으면 추가"""
    for col, definition in [
        ("duration_seconds", "INTEGER DEFAULT 0"),
        ("is_touch_device", "INTEGER"),
        ("is_mobile", "INTEGER"),
        ("inner_width", "INTEGER"),
        ("inner_height", "INTEGER"),
        ("utm_source", "TEXT"),
        ("utm_medium", "TEXT"),
        ("utm_campaign", "TEXT"),
        ("utm_content", "TEXT"),
        ("utm_term", "TEXT"),
    ]:
        try:
            con.execute(f"ALTER TABLE estimate_visitor_logs ADD COLUMN {col} {definition}")
            con.commit()
        except Exception:
            pass


def _build_where(date_from: Optional[str], date_to: Optional[str]) -> tuple:
    """WordPress 도메인 + 날짜 필터 WHERE절과 params 반환"""
    where = f"page_url LIKE '%{WP_DOMAIN}%'"
    params: List[Any] = []
    if date_from:
        where += " AND date(created_at) >= ?"
        params.append(date_from)
    if date_to:
        where += " AND date(created_at) <= ?"
        params.append(date_to)
    return where, params


def _classify_source(utm_source: Optional[str], utm_medium: Optional[str], referrer: Optional[str]) -> str:
    """유입 경로 상세 분류 (유료/자연 구분)"""
    if utm_source:
        s = utm_source.lower()
        m = (utm_medium or "").lower()
        is_paid = any(x in m for x in ("cpc", "paid", "ppc", "ad", "ads", "display", "remarketing"))
        if s in ("instagram", "ig"):
            return "Instagram 광고" if is_paid else "Instagram"
        if s == "youtube":
            return "YouTube 광고" if is_paid else "YouTube"
        if s == "naver":
            return "네이버 광고" if is_paid else "Naver"
        if s == "google":
            return "Google 광고" if is_paid else "Google"
        if s in ("facebook", "fb"):
            return "Facebook 광고" if is_paid else "Facebook"
        if s in ("kakao", "kakaotalk"):
            return "카카오 광고" if is_paid else "KakaoTalk"
        if s == "tiktok":
            return "TikTok 광고" if is_paid else "TikTok"
        if s in ("twitter", "x"):
            return "X(Twitter)"
        if m == "email":
            return "이메일"
        return utm_source
    if referrer:
        r = referrer.lower()
        if "instagram" in r:
            return "Instagram"
        if "youtube" in r:
            return "YouTube"
        if "naver" in r:
            return "Naver"
        if "google" in r:
            return "Google"
        if "facebook" in r:
            return "Facebook"
        if "kakao" in r:
            return "KakaoTalk"
        if "tiktok" in r:
            return "TikTok"
        if "twitter" in r or "x.com" in r:
            return "X(Twitter)"
        if "daum" in r:
            return "Daum"
        if WP_DOMAIN in r:
            return "사이트 내 이동"
        return "기타"
    return "직접 접속"


def _shorten_page(url: str) -> str:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path.rstrip("/") or "/"
        return path if path != "/" else "홈 (/)"
    except Exception:
        return url


@router.get("/stats")
async def get_wp_stats(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """WordPress 전체 방문 통계 (요약 + 각종 분류)"""
    try:
        with get_connection() as con:
            _ensure_columns(con)
            where, params = _build_where(date_from, date_to)

            total_visits = con.execute(
                f"SELECT COUNT(*) FROM estimate_visitor_logs WHERE {where}", params
            ).fetchone()[0]

            unique_visitors = con.execute(
                f"SELECT COUNT(DISTINCT ip_address) FROM estimate_visitor_logs WHERE {where}", params
            ).fetchone()[0]

            touch = con.execute(
                f"""
                SELECT SUM(CASE WHEN is_mobile=1 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN is_touch_device=1 THEN 1 ELSE 0 END),
                       COUNT(*)
                FROM estimate_visitor_logs WHERE {where}
                """, params,
            ).fetchone()

            dwell = con.execute(
                f"""
                SELECT AVG(duration_seconds), MAX(duration_seconds),
                       COUNT(CASE WHEN duration_seconds > 0 THEN 1 END)
                FROM estimate_visitor_logs
                WHERE {where} AND duration_seconds > 0
                """, params,
            ).fetchone()

            # 페이지별 방문
            page_stats = con.execute(
                f"""
                SELECT page_url, COUNT(*) as cnt,
                       COUNT(DISTINCT ip_address) as unique_cnt,
                       AVG(CASE WHEN duration_seconds > 0 THEN duration_seconds END) as avg_dur
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY page_url ORDER BY cnt DESC LIMIT 20
                """, params,
            ).fetchall()

            # 유입 경로 (UTM 우선)
            referrer_raw = con.execute(
                f"""
                SELECT utm_source, utm_medium, referrer, COUNT(*) as cnt
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY utm_source, utm_medium, referrer
                """, params,
            ).fetchall()

            source_map: dict = {}
            for row in referrer_raw:
                src = _classify_source(row[0], row[1], row[2])
                source_map[src] = source_map.get(src, 0) + row[3]
            referrer_stats = sorted(
                [{"source": k, "count": v} for k, v in source_map.items()],
                key=lambda x: -x["count"]
            )[:15]

            # OS / 브라우저 / 디바이스
            os_stats = con.execute(
                f"""
                SELECT os, COUNT(*) FROM estimate_visitor_logs
                WHERE {where} AND os IS NOT NULL AND os != ''
                GROUP BY os ORDER BY COUNT(*) DESC
                """, params,
            ).fetchall()

            browser_stats = con.execute(
                f"""
                SELECT browser, COUNT(*) FROM estimate_visitor_logs
                WHERE {where} AND browser IS NOT NULL AND browser != ''
                GROUP BY browser ORDER BY COUNT(*) DESC
                """, params,
            ).fetchall()

            device_stats = con.execute(
                f"""
                SELECT device_type, COUNT(*) FROM estimate_visitor_logs
                WHERE {where} AND device_type IS NOT NULL AND device_type != ''
                GROUP BY device_type ORDER BY COUNT(*) DESC
                """, params,
            ).fetchall()

            # 시간대 / 요일
            hourly_stats = con.execute(
                f"""
                SELECT strftime('%H', created_at) as h, COUNT(*)
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY h ORDER BY h
                """, params,
            ).fetchall()

            weekday_stats = con.execute(
                f"""
                SELECT
                    CASE strftime('%w', created_at)
                        WHEN '0' THEN '일' WHEN '1' THEN '월' WHEN '2' THEN '화'
                        WHEN '3' THEN '수' WHEN '4' THEN '목' WHEN '5' THEN '금'
                        WHEN '6' THEN '토' END as wd,
                    strftime('%w', created_at) as wn,
                    COUNT(*)
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY wn ORDER BY wn
                """, params,
            ).fetchall()

            # 지역
            location_stats = con.execute(
                f"""
                SELECT
                    CASE
                        WHEN city IS NOT NULL AND city != '' THEN city
                        WHEN region IS NOT NULL AND region != '' THEN region
                        WHEN country IS NOT NULL AND country != '' THEN country
                        ELSE '알 수 없음'
                    END as loc,
                    COUNT(*)
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY loc ORDER BY COUNT(*) DESC LIMIT 10
                """, params,
            ).fetchall()

            # 일별 추이
            daily_visits = con.execute(
                f"""
                SELECT date(created_at) as d, COUNT(*)
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY d ORDER BY d DESC LIMIT 30
                """, params,
            ).fetchall()

            # UTM 캠페인
            utm_stats = con.execute(
                f"""
                SELECT utm_source, utm_medium, utm_campaign, COUNT(*) as cnt
                FROM estimate_visitor_logs
                WHERE {where} AND utm_source IS NOT NULL AND utm_source != ''
                GROUP BY utm_source, utm_medium, utm_campaign
                ORDER BY cnt DESC LIMIT 20
                """, params,
            ).fetchall()

            # 체류시간 분포
            dwell_dist = con.execute(
                f"""
                SELECT
                    SUM(CASE WHEN duration_seconds BETWEEN 1 AND 9 THEN 1 ELSE 0 END) as s1,
                    SUM(CASE WHEN duration_seconds BETWEEN 10 AND 29 THEN 1 ELSE 0 END) as s2,
                    SUM(CASE WHEN duration_seconds BETWEEN 30 AND 59 THEN 1 ELSE 0 END) as s3,
                    SUM(CASE WHEN duration_seconds BETWEEN 60 AND 179 THEN 1 ELSE 0 END) as s4,
                    SUM(CASE WHEN duration_seconds BETWEEN 180 AND 599 THEN 1 ELSE 0 END) as s5,
                    SUM(CASE WHEN duration_seconds >= 600 THEN 1 ELSE 0 END) as s6,
                    SUM(CASE WHEN duration_seconds = 0 OR duration_seconds IS NULL THEN 1 ELSE 0 END) as s0
                FROM estimate_visitor_logs WHERE {where}
                """, params,
            ).fetchone()

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
                    {"page_url": r[0], "count": r[1], "unique_count": r[2], "avg_duration": int(r[3]) if r[3] else 0}
                    for r in page_stats
                ],
                "referrer_stats": referrer_stats,
                "os_stats": [{"os": r[0], "count": r[1]} for r in os_stats],
                "browser_stats": [{"browser": r[0], "count": r[1]} for r in browser_stats],
                "device_stats": [{"device": r[0], "count": r[1]} for r in device_stats],
                "hourly_stats": [{"hour": r[0], "count": r[1]} for r in hourly_stats],
                "weekday_stats": [{"weekday": r[0], "count": r[2]} for r in weekday_stats],
                "location_stats": [{"location": r[0], "count": r[1]} for r in location_stats],
                "daily_visits": [{"date": r[0], "count": r[1]} for r in daily_visits],
                "utm_stats": [
                    {"source": r[0], "medium": r[1] or "", "campaign": r[2] or "", "count": r[3]}
                    for r in utm_stats
                ],
                "dwell_distribution": {
                    "미측정": int(dwell_dist[6] or 0) if dwell_dist else 0,
                    "1-9초": int(dwell_dist[0] or 0) if dwell_dist else 0,
                    "10-29초": int(dwell_dist[1] or 0) if dwell_dist else 0,
                    "30-59초": int(dwell_dist[2] or 0) if dwell_dist else 0,
                    "1-3분": int(dwell_dist[3] or 0) if dwell_dist else 0,
                    "3-10분": int(dwell_dist[4] or 0) if dwell_dist else 0,
                    "10분+": int(dwell_dist[5] or 0) if dwell_dist else 0,
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flow")
async def get_page_flow(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    페이지 흐름 분석.
    - 입장 페이지 (Landing pages)
    - 이탈 페이지 (Exit pages)
    - 바운스율 (단일 페이지 세션)
    - 세션 깊이 분포
    - 페이지 전환 흐름 (A → B)
    """
    try:
        with get_connection() as con:
            _ensure_columns(con)
            where, params = _build_where(date_from, date_to)

            # ── 세션별 페이지 수 / 첫페이지 / 마지막페이지 ────────────
            session_data = con.execute(
                f"""
                SELECT session_id,
                       COUNT(*) as page_count,
                       MIN(id) as first_id,
                       MAX(id) as last_id,
                       MAX(duration_seconds) as duration
                FROM estimate_visitor_logs
                WHERE {where} AND session_id IS NOT NULL AND session_id != ''
                GROUP BY session_id
                """, params,
            ).fetchall()

            total_sessions = len(session_data)
            bounce_sessions = sum(1 for r in session_data if r[1] == 1)
            bounce_rate = round(bounce_sessions / total_sessions * 100, 1) if total_sessions > 0 else 0

            # 세션 깊이 분포
            depth_map = {"1 페이지": 0, "2 페이지": 0, "3 페이지": 0, "4-5 페이지": 0, "6+ 페이지": 0}
            for r in session_data:
                pc = r[1]
                if pc == 1:
                    depth_map["1 페이지"] += 1
                elif pc == 2:
                    depth_map["2 페이지"] += 1
                elif pc == 3:
                    depth_map["3 페이지"] += 1
                elif pc <= 5:
                    depth_map["4-5 페이지"] += 1
                else:
                    depth_map["6+ 페이지"] += 1

            first_ids = [r[2] for r in session_data]
            last_ids = [r[3] for r in session_data]

            # ── 입장 페이지 ───────────────────────────────────────
            entry_pages: dict = {}
            if first_ids:
                placeholders = ",".join("?" * len(first_ids))
                entry_rows = con.execute(
                    f"""
                    SELECT page_url, COUNT(*) as cnt
                    FROM estimate_visitor_logs
                    WHERE id IN ({placeholders})
                    GROUP BY page_url ORDER BY cnt DESC LIMIT 10
                    """, first_ids,
                ).fetchall()
                entry_pages = {r[0]: r[1] for r in entry_rows}

            # ── 이탈 페이지 ───────────────────────────────────────
            exit_pages: dict = {}
            if last_ids:
                placeholders = ",".join("?" * len(last_ids))
                exit_rows = con.execute(
                    f"""
                    SELECT page_url, COUNT(*) as cnt
                    FROM estimate_visitor_logs
                    WHERE id IN ({placeholders})
                    GROUP BY page_url ORDER BY cnt DESC LIMIT 10
                    """, last_ids,
                ).fetchall()
                exit_pages = {r[0]: r[1] for r in exit_rows}

            # ── 페이지 전환 흐름 (A → B) ─────────────────────────
            # session_id 기준으로 연속 페이지 쌍 추출
            flow_rows = con.execute(
                f"""
                SELECT a.page_url as from_page, b.page_url as to_page, COUNT(*) as cnt
                FROM estimate_visitor_logs a
                JOIN estimate_visitor_logs b
                  ON a.session_id = b.session_id
                  AND b.id = (
                      SELECT MIN(id) FROM estimate_visitor_logs
                      WHERE session_id = a.session_id AND id > a.id
                        AND page_url LIKE '%{WP_DOMAIN}%'
                  )
                WHERE a.page_url LIKE '%{WP_DOMAIN}%'
                  AND b.page_url LIKE '%{WP_DOMAIN}%'
                  AND a.session_id IS NOT NULL AND a.session_id != ''
                  {'AND date(a.created_at) >= ?' if date_from else ''}
                  {'AND date(a.created_at) <= ?' if date_to else ''}
                GROUP BY from_page, to_page
                ORDER BY cnt DESC LIMIT 20
                """,
                ([date_from] if date_from else []) + ([date_to] if date_to else []),
            ).fetchall()

            # ── 페이지별 이탈률 ───────────────────────────────────
            # 페이지별 (총 방문 중 마지막 페이지인 비율)
            page_exit_rate: dict = {}
            page_total: dict = {}
            page_last: dict = {}
            for r in session_data:
                pass  # computed below via SQL

            page_counts_rows = con.execute(
                f"""
                SELECT page_url, COUNT(*) as total
                FROM estimate_visitor_logs WHERE {where}
                GROUP BY page_url
                """, params,
            ).fetchall()
            for r in page_counts_rows:
                page_total[r[0]] = r[1]

            if last_ids:
                placeholders = ",".join("?" * len(last_ids))
                last_page_rows = con.execute(
                    f"""
                    SELECT page_url, COUNT(*) as cnt
                    FROM estimate_visitor_logs
                    WHERE id IN ({placeholders})
                    GROUP BY page_url
                    """, last_ids,
                ).fetchall()
                for r in last_page_rows:
                    page_last[r[0]] = r[1]

            exit_rate_list = []
            for url, total in page_total.items():
                exits = page_last.get(url, 0)
                exit_rate_list.append({
                    "page_url": url,
                    "total_views": total,
                    "exit_count": exits,
                    "exit_rate": round(exits / total * 100, 1) if total > 0 else 0,
                })
            exit_rate_list.sort(key=lambda x: -x["exit_count"])
            exit_rate_list = exit_rate_list[:15]

            return {
                "summary": {
                    "total_sessions": total_sessions,
                    "bounce_sessions": bounce_sessions,
                    "bounce_rate": bounce_rate,
                },
                "session_depth": [
                    {"label": k, "count": v} for k, v in depth_map.items()
                ],
                "entry_pages": [
                    {"page_url": k, "count": v} for k, v in sorted(entry_pages.items(), key=lambda x: -x[1])
                ],
                "exit_pages": [
                    {"page_url": k, "count": v} for k, v in sorted(exit_pages.items(), key=lambda x: -x[1])
                ],
                "page_flow": [
                    {"from_page": r[0], "to_page": r[1], "count": r[2]} for r in flow_rows
                ],
                "exit_rate_by_page": exit_rate_list,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def get_ip_sessions(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    """
    IP별 방문자 세션 요약.
    방문 횟수, 페이지뷰, 체류시간, 위치, 유입경로, 기기 등.
    """
    try:
        with get_connection() as con:
            _ensure_columns(con)
            where, params = _build_where(date_from, date_to)

            total = con.execute(
                f"SELECT COUNT(DISTINCT ip_address) FROM estimate_visitor_logs WHERE {where}", params
            ).fetchone()[0]

            offset = (page - 1) * page_size
            rows = con.execute(
                f"""
                SELECT
                    ip_address,
                    country, region, city,
                    COUNT(*) as page_views,
                    COUNT(DISTINCT session_id) as sessions,
                    MAX(duration_seconds) as max_duration,
                    MIN(created_at) as first_visit,
                    MAX(created_at) as last_visit,
                    MAX(os) as os,
                    MAX(browser) as browser,
                    MAX(device_type) as device_type,
                    MAX(is_mobile) as is_mobile,
                    GROUP_CONCAT(DISTINCT utm_source) as utm_sources,
                    GROUP_CONCAT(DISTINCT utm_campaign) as utm_campaigns,
                    GROUP_CONCAT(DISTINCT referrer) as referrers,
                    GROUP_CONCAT(DISTINCT language) as languages
                FROM estimate_visitor_logs
                WHERE {where}
                GROUP BY ip_address
                ORDER BY page_views DESC
                LIMIT ? OFFSET ?
                """,
                params + [page_size, offset],
            ).fetchall()

            # 각 IP의 방문 페이지 목록 (최대 5개)
            items = []
            for r in rows:
                ip = r[0]
                pages_visited = con.execute(
                    f"""
                    SELECT DISTINCT page_url FROM estimate_visitor_logs
                    WHERE ip_address = ? AND page_url LIKE '%{WP_DOMAIN}%'
                    ORDER BY id DESC LIMIT 5
                    """, (ip,),
                ).fetchall()

                # 유입경로 파악
                utm_sources = r[13].split(",") if r[13] else []
                referrers = r[15].split(",") if r[15] else []
                source = _classify_source(
                    utm_sources[0] if utm_sources else None,
                    None,
                    referrers[0] if referrers else None,
                )

                items.append({
                    "ip_address": ip,
                    "country": r[1] or "",
                    "region": r[2] or "",
                    "city": r[3] or "",
                    "page_views": r[4],
                    "sessions": r[5],
                    "max_duration": r[6] or 0,
                    "first_visit": str(r[7]) if r[7] else "",
                    "last_visit": str(r[8]) if r[8] else "",
                    "os": r[9] or "",
                    "browser": r[10] or "",
                    "device_type": r[11] or "",
                    "is_mobile": bool(r[12]) if r[12] is not None else False,
                    "source": source,
                    "utm_campaign": (r[14] or "").split(",")[0],
                    "pages_visited": [p[0] for p in pages_visited],
                })

            return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visitors")
async def list_wp_visitors(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """WordPress 방문자 로그 목록 (페이지네이션)"""
    try:
        with get_connection() as con:
            _ensure_columns(con)
            where, params = _build_where(date_from, date_to)

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
                    "country": r[2], "region": r[3], "city": r[4],
                    "page_url": r[5], "referrer": r[6],
                    "os": r[7], "browser": r[8], "device_type": r[9],
                    "screen_width": r[10], "screen_height": r[11],
                    "language": r[12], "timezone": r[13], "session_id": r[14],
                    "created_at": str(r[15]) if r[15] else "",
                    "is_touch_device": bool(r[16]) if r[16] is not None else None,
                    "is_mobile": bool(r[17]) if r[17] is not None else None,
                    "inner_width": r[18], "inner_height": r[19],
                    "utm_source": r[20], "utm_medium": r[21], "utm_campaign": r[22],
                    "duration_seconds": r[23] or 0,
                    "source": _classify_source(r[20], r[21], r[6]),
                }
                for r in rows
            ]

            return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
