"""
backend/app/api/estimate_analytics.py - 견적서 접속 로그 및 분석 API
────────────────────────────────────────────────────────
사용자 접속 정보 수집, 견적 계산 횟수 모니터링, 로그 분석
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from datetime import datetime
import json
import httpx

from logic.db import get_connection

router = APIRouter(prefix="/estimate-analytics", tags=["estimate-analytics"])


class VisitorLogRequest(BaseModel):
    """방문자 로그 요청"""
    page_url: str
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    platform: Optional[str] = None
    vendor: Optional[str] = None
    session_id: Optional[str] = None
    is_touch_device: Optional[bool] = None
    is_mobile: Optional[bool] = None
    inner_width: Optional[int] = None
    inner_height: Optional[int] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None


class CalculateLogRequest(BaseModel):
    """견적 계산 로그 요청"""
    company_name: Optional[str] = None
    email: Optional[str] = None
    brand_type: Optional[str] = None
    monthly_outbound: Optional[int] = None
    total_amount: Optional[int] = None
    session_id: Optional[str] = None


class HeartbeatRequest(BaseModel):
    """체류시간 하트비트 요청"""
    session_id: str
    duration_seconds: int


def _ensure_tables(con):
    """로그 테이블 생성"""
    con.execute("""
        CREATE TABLE IF NOT EXISTS estimate_visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            country TEXT,
            region TEXT,
            city TEXT,
            page_url TEXT,
            referrer TEXT,
            user_agent TEXT,
            os TEXT,
            browser TEXT,
            device_type TEXT,
            screen_width INTEGER,
            screen_height INTEGER,
            language TEXT,
            timezone TEXT,
            platform TEXT,
            vendor TEXT,
            session_id TEXT,
            is_touch_device INTEGER,
            is_mobile INTEGER,
            inner_width INTEGER,
            inner_height INTEGER,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            utm_content TEXT,
            utm_term TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 기존 테이블에 새 컬럼 추가 (없으면)
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN is_touch_device INTEGER")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN is_mobile INTEGER")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN inner_width INTEGER")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN inner_height INTEGER")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN utm_source TEXT")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN utm_medium TEXT")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN utm_campaign TEXT")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN utm_content TEXT")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN utm_term TEXT")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE estimate_visitor_logs ADD COLUMN duration_seconds INTEGER DEFAULT 0")
    except Exception:
        pass
    con.execute("""
        CREATE TABLE IF NOT EXISTS estimate_calculate_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            session_id TEXT,
            company_name TEXT,
            email TEXT,
            brand_type TEXT,
            monthly_outbound INTEGER,
            total_amount INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()


def _parse_user_agent(ua: str) -> Dict[str, str]:
    """User-Agent 파싱하여 OS, 브라우저, 디바이스 타입 추출"""
    ua_lower = ua.lower() if ua else ""
    
    # OS 판별
    os_name = "Unknown"
    if "windows" in ua_lower:
        os_name = "Windows"
        if "windows nt 10" in ua_lower:
            os_name = "Windows 10/11"
        elif "windows nt 6.3" in ua_lower:
            os_name = "Windows 8.1"
        elif "windows nt 6.2" in ua_lower:
            os_name = "Windows 8"
        elif "windows nt 6.1" in ua_lower:
            os_name = "Windows 7"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        os_name = "macOS"
    elif "iphone" in ua_lower:
        os_name = "iOS (iPhone)"
    elif "ipad" in ua_lower:
        os_name = "iOS (iPad)"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "linux" in ua_lower:
        os_name = "Linux"
    
    # 브라우저 판별
    browser = "Unknown"
    if "edg/" in ua_lower or "edge/" in ua_lower:
        browser = "Edge"
    elif "chrome/" in ua_lower and "safari/" in ua_lower:
        if "opr/" in ua_lower or "opera" in ua_lower:
            browser = "Opera"
        else:
            browser = "Chrome"
    elif "firefox/" in ua_lower:
        browser = "Firefox"
    elif "safari/" in ua_lower and "chrome/" not in ua_lower:
        browser = "Safari"
    elif "msie" in ua_lower or "trident/" in ua_lower:
        browser = "Internet Explorer"
    elif "kakaotalk" in ua_lower:
        browser = "KakaoTalk"
    elif "naver" in ua_lower:
        browser = "Naver"
    elif "instagram" in ua_lower:
        browser = "Instagram"
    elif "facebook" in ua_lower:
        browser = "Facebook"
    
    # 디바이스 타입 판별
    device_type = "Desktop"
    if "mobile" in ua_lower or "android" in ua_lower and "mobile" in ua_lower:
        device_type = "Mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device_type = "Tablet"
    elif "iphone" in ua_lower:
        device_type = "Mobile"
    
    return {
        "os": os_name,
        "browser": browser,
        "device_type": device_type,
    }


def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 주소 추출"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


async def _get_ip_location(ip_address: str) -> Dict[str, str]:
    """IP 주소로 위치 정보 조회 (ip-api.com 무료 API 사용)"""
    result = {"country": "", "region": "", "city": ""}
    
    if not ip_address or ip_address in ("unknown", "127.0.0.1", "localhost", "::1"):
        return result
    
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"http://ip-api.com/json/{ip_address}?lang=ko")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    result["country"] = data.get("country", "")
                    result["region"] = data.get("regionName", "")
                    result["city"] = data.get("city", "")
    except Exception:
        pass
    
    return result


@router.post("/visit")
async def log_visit(body: VisitorLogRequest, request: Request):
    """
    페이지 방문 로그 기록.
    프론트엔드에서 견적 페이지 접속 시 호출.
    """
    try:
        from zoneinfo import ZoneInfo
        kst_now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
        
        ip_address = _get_client_ip(request)
        ua_info = _parse_user_agent(body.user_agent or "")
        
        # IP 기반 위치 정보 조회
        location = await _get_ip_location(ip_address)
        country = location["country"]
        region = location["region"]
        city = location["city"]
        
        # 터치 기반 모바일 판별이 있으면 그것을 우선 사용
        device_type = ua_info["device_type"]
        if body.is_mobile is True:
            device_type = "Mobile"
        elif body.is_touch_device is True and device_type == "Desktop":
            device_type = "Tablet/Touch"
        
        with get_connection() as con:
            _ensure_tables(con)
            con.execute(
                """
                INSERT INTO estimate_visitor_logs 
                (ip_address, country, region, city, page_url, referrer, user_agent, 
                 os, browser, device_type, screen_width, screen_height, language, 
                 timezone, platform, vendor, session_id, is_touch_device, is_mobile,
                 inner_width, inner_height, utm_source, utm_medium, utm_campaign,
                 utm_content, utm_term, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ip_address, country, region, city,
                    body.page_url, body.referrer, body.user_agent,
                    ua_info["os"], ua_info["browser"], device_type,
                    body.screen_width, body.screen_height, body.language,
                    body.timezone, body.platform, body.vendor,
                    body.session_id, 
                    1 if body.is_touch_device else 0,
                    1 if body.is_mobile else 0,
                    body.inner_width, body.inner_height,
                    body.utm_source, body.utm_medium, body.utm_campaign,
                    body.utm_content, body.utm_term,
                    kst_now,
                ),
            )
            con.commit()
        
        return {"success": True, "ip": ip_address, "is_mobile": body.is_mobile, "is_touch": body.is_touch_device}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate")
async def log_calculate(body: CalculateLogRequest, request: Request):
    """
    견적 계산 로그 기록.
    견적 계산 버튼 클릭 시 호출.
    """
    try:
        from zoneinfo import ZoneInfo
        kst_now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
        
        ip_address = _get_client_ip(request)
        
        with get_connection() as con:
            _ensure_tables(con)
            con.execute(
                """
                INSERT INTO estimate_calculate_logs 
                (ip_address, session_id, company_name, email, brand_type, 
                 monthly_outbound, total_amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ip_address, body.session_id, body.company_name, body.email,
                    body.brand_type, body.monthly_outbound, body.total_amount,
                    kst_now,
                ),
            )
            con.commit()
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat")
async def log_heartbeat(request: Request):
    """
    체류시간 업데이트.
    sendBeacon(text/plain) 또는 fetch(application/json) 모두 처리.
    """
    try:
        import json as _json
        raw = await request.body()
        try:
            data = _json.loads(raw)
        except Exception:
            return {"success": False, "reason": "invalid body"}

        session_id = data.get("session_id", "")
        duration_seconds = int(data.get("duration_seconds", 0))

        if not session_id:
            return {"success": False, "reason": "missing session_id"}

        ip_address = _get_client_ip(request)
        with get_connection() as con:
            _ensure_tables(con)
            con.execute(
                """
                UPDATE estimate_visitor_logs
                SET duration_seconds = ?
                WHERE session_id = ? AND ip_address = ?
                  AND id = (
                    SELECT id FROM estimate_visitor_logs
                    WHERE session_id = ? AND ip_address = ?
                    ORDER BY id DESC LIMIT 1
                  )
                """,
                (duration_seconds, session_id, ip_address, session_id, ip_address),
            )
            con.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(
    date_from: Optional[str] = Query(None, description="시작일 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="종료일 YYYY-MM-DD"),
):
    """
    견적서 로그 통계.
    총 방문수, 계산 횟수, OS별/브라우저별/디바이스별 통계 등.
    """
    try:
        with get_connection() as con:
            _ensure_tables(con)
            
            # 날짜 필터
            where_visit = "1=1"
            where_calc = "1=1"
            params_visit: List[Any] = []
            params_calc: List[Any] = []
            
            if date_from:
                where_visit += " AND date(created_at) >= ?"
                where_calc += " AND date(created_at) >= ?"
                params_visit.append(date_from)
                params_calc.append(date_from)
            if date_to:
                where_visit += " AND date(created_at) <= ?"
                where_calc += " AND date(created_at) <= ?"
                params_visit.append(date_to)
                params_calc.append(date_to)
            
            # 총 방문수
            visit_count = con.execute(
                f"SELECT COUNT(*) FROM estimate_visitor_logs WHERE {where_visit}",
                params_visit
            ).fetchone()[0]
            
            # 고유 방문자 수 (IP 기준)
            unique_visitors = con.execute(
                f"SELECT COUNT(DISTINCT ip_address) FROM estimate_visitor_logs WHERE {where_visit}",
                params_visit
            ).fetchone()[0]
            
            # 총 계산 횟수
            calc_count = con.execute(
                f"SELECT COUNT(*) FROM estimate_calculate_logs WHERE {where_calc}",
                params_calc
            ).fetchone()[0]
            
            # 고유 계산자 수 (IP 기준)
            unique_calculators = con.execute(
                f"SELECT COUNT(DISTINCT ip_address) FROM estimate_calculate_logs WHERE {where_calc}",
                params_calc
            ).fetchone()[0]
            
            # OS별 통계
            os_stats = con.execute(
                f"""
                SELECT os, COUNT(*) as cnt 
                FROM estimate_visitor_logs 
                WHERE {where_visit} AND os IS NOT NULL AND os != ''
                GROUP BY os ORDER BY cnt DESC
                """,
                params_visit
            ).fetchall()
            
            # 브라우저별 통계
            browser_stats = con.execute(
                f"""
                SELECT browser, COUNT(*) as cnt 
                FROM estimate_visitor_logs 
                WHERE {where_visit} AND browser IS NOT NULL AND browser != ''
                GROUP BY browser ORDER BY cnt DESC
                """,
                params_visit
            ).fetchall()
            
            # 디바이스 타입별 통계
            device_stats = con.execute(
                f"""
                SELECT device_type, COUNT(*) as cnt 
                FROM estimate_visitor_logs 
                WHERE {where_visit} AND device_type IS NOT NULL AND device_type != ''
                GROUP BY device_type ORDER BY cnt DESC
                """,
                params_visit
            ).fetchall()
            
            # 브랜드 타입별 계산 통계
            brand_stats = con.execute(
                f"""
                SELECT brand_type, COUNT(*) as cnt, 
                       AVG(monthly_outbound) as avg_outbound,
                       AVG(total_amount) as avg_amount
                FROM estimate_calculate_logs 
                WHERE {where_calc} AND brand_type IS NOT NULL AND brand_type != ''
                GROUP BY brand_type ORDER BY cnt DESC
                """,
                params_calc
            ).fetchall()
            
            # 일별 방문/계산 추이 (최근 30일)
            daily_visits = con.execute(
                f"""
                SELECT date(created_at) as day, COUNT(*) as cnt
                FROM estimate_visitor_logs 
                WHERE {where_visit}
                GROUP BY date(created_at) ORDER BY day DESC LIMIT 30
                """,
                params_visit
            ).fetchall()
            
            daily_calcs = con.execute(
                f"""
                SELECT date(created_at) as day, COUNT(*) as cnt
                FROM estimate_calculate_logs 
                WHERE {where_calc}
                GROUP BY date(created_at) ORDER BY day DESC LIMIT 30
                """,
                params_calc
            ).fetchall()
            
            # 시간대별 방문 통계
            hourly_stats = con.execute(
                f"""
                SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
                FROM estimate_visitor_logs 
                WHERE {where_visit}
                GROUP BY strftime('%H', created_at) ORDER BY hour
                """,
                params_visit
            ).fetchall()
            
            # Referrer 통계 (접속 경로) - UTM 소스 우선, 없으면 referrer 분석
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
                                WHEN LOWER(utm_source) = 'kakao' OR LOWER(utm_source) = 'kakaotalk' THEN 'KakaoTalk'
                                WHEN LOWER(utm_source) = 'tiktok' THEN 'TikTok'
                                WHEN LOWER(utm_source) = 'twitter' OR LOWER(utm_source) = 'x' THEN 'X(Twitter)'
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
                        ELSE '기타'
                    END as source,
                    COUNT(*) as cnt
                FROM estimate_visitor_logs 
                WHERE {where_visit}
                GROUP BY source ORDER BY cnt DESC LIMIT 15
                """,
                params_visit
            ).fetchall()
            
            # UTM 캠페인별 통계
            utm_campaign_stats = con.execute(
                f"""
                SELECT utm_campaign, COUNT(*) as cnt
                FROM estimate_visitor_logs 
                WHERE {where_visit} AND utm_campaign IS NOT NULL AND utm_campaign != ''
                GROUP BY utm_campaign ORDER BY cnt DESC LIMIT 10
                """,
                params_visit
            ).fetchall()
            
            # 터치/모바일 통계
            touch_stats = con.execute(
                f"""
                SELECT 
                    SUM(CASE WHEN is_touch_device = 1 THEN 1 ELSE 0 END) as touch_count,
                    SUM(CASE WHEN is_mobile = 1 THEN 1 ELSE 0 END) as mobile_count,
                    COUNT(*) as total
                FROM estimate_visitor_logs 
                WHERE {where_visit}
                """,
                params_visit
            ).fetchone()
            
            # 평균 체류시간 (duration_seconds > 0인 방문만)
            dwell_stats = con.execute(
                f"""
                SELECT 
                    AVG(duration_seconds) as avg_duration,
                    MAX(duration_seconds) as max_duration,
                    COUNT(CASE WHEN duration_seconds > 0 THEN 1 END) as tracked_count
                FROM estimate_visitor_logs 
                WHERE {where_visit} AND duration_seconds > 0
                """,
                params_visit
            ).fetchone()
            
            # 지역별 통계
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
                WHERE {where_visit}
                GROUP BY location ORDER BY cnt DESC LIMIT 10
                """,
                params_visit
            ).fetchall()
            
            return {
                "summary": {
                    "total_visits": visit_count,
                    "unique_visitors": unique_visitors,
                    "total_calculations": calc_count,
                    "unique_calculators": unique_calculators,
                    "conversion_rate": round(calc_count / visit_count * 100, 1) if visit_count > 0 else 0,
                    "touch_device_count": touch_stats[0] if touch_stats else 0,
                    "mobile_count": touch_stats[1] if touch_stats else 0,
                    "mobile_rate": round((touch_stats[1] or 0) / touch_stats[2] * 100, 1) if touch_stats and touch_stats[2] > 0 else 0,
                    "avg_duration_seconds": int(dwell_stats[0]) if dwell_stats and dwell_stats[0] else 0,
                    "max_duration_seconds": int(dwell_stats[1]) if dwell_stats and dwell_stats[1] else 0,
                    "tracked_visit_count": dwell_stats[2] if dwell_stats else 0,
                },
                "os_stats": [{"os": r[0], "count": r[1]} for r in os_stats],
                "browser_stats": [{"browser": r[0], "count": r[1]} for r in browser_stats],
                "device_stats": [{"device": r[0], "count": r[1]} for r in device_stats],
                "brand_stats": [
                    {
                        "brand_type": r[0],
                        "count": r[1],
                        "avg_outbound": int(r[2]) if r[2] else 0,
                        "avg_amount": int(r[3]) if r[3] else 0,
                    }
                    for r in brand_stats
                ],
                "daily_visits": [{"date": r[0], "count": r[1]} for r in daily_visits],
                "daily_calculations": [{"date": r[0], "count": r[1]} for r in daily_calcs],
                "hourly_stats": [{"hour": r[0], "count": r[1]} for r in hourly_stats],
                "referrer_stats": [{"source": r[0], "count": r[1]} for r in referrer_stats],
                "location_stats": [{"location": r[0], "count": r[1]} for r in location_stats],
                "utm_campaign_stats": [{"campaign": r[0], "count": r[1]} for r in utm_campaign_stats],
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/visitors")
async def list_visitors(
    date_from: Optional[str] = Query(None, description="시작일 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="종료일 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    방문자 로그 목록.
    """
    try:
        with get_connection() as con:
            _ensure_tables(con)
            
            where = "1=1"
            params: List[Any] = []
            
            if date_from:
                where += " AND date(created_at) >= ?"
                params.append(date_from)
            if date_to:
                where += " AND date(created_at) <= ?"
                params.append(date_to)
            
            # 총 개수
            total = con.execute(
                f"SELECT COUNT(*) FROM estimate_visitor_logs WHERE {where}",
                params
            ).fetchone()[0]
            
            # 목록 조회
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
                params + [page_size, offset]
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
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calculations")
async def list_calculations(
    date_from: Optional[str] = Query(None, description="시작일 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="종료일 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    견적 계산 로그 목록.
    """
    try:
        with get_connection() as con:
            _ensure_tables(con)
            
            where = "1=1"
            params: List[Any] = []
            
            if date_from:
                where += " AND date(created_at) >= ?"
                params.append(date_from)
            if date_to:
                where += " AND date(created_at) <= ?"
                params.append(date_to)
            
            # 총 개수
            total = con.execute(
                f"SELECT COUNT(*) FROM estimate_calculate_logs WHERE {where}",
                params
            ).fetchone()[0]
            
            # 목록 조회
            offset = (page - 1) * page_size
            rows = con.execute(
                f"""
                SELECT id, ip_address, session_id, company_name, email, brand_type,
                       monthly_outbound, total_amount, created_at
                FROM estimate_calculate_logs 
                WHERE {where}
                ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                params + [page_size, offset]
            ).fetchall()
            
            items = [
                {
                    "id": r[0],
                    "ip_address": r[1],
                    "session_id": r[2],
                    "company_name": r[3],
                    "email": r[4],
                    "brand_type": r[5],
                    "monthly_outbound": r[6],
                    "total_amount": r[7],
                    "created_at": str(r[8]) if r[8] else "",
                }
                for r in rows
            ]
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
