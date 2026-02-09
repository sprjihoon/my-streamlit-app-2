"""
backend/app/api/work_log.py - 작업일지 API
───────────────────────────────────────
봇 또는 엑셀로 입력된 작업일지를 관리합니다.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import pandas as pd

from logic.db import get_connection
from backend.app.api.logs import add_log

router = APIRouter(prefix="/work-log", tags=["work-log"])


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class WorkLogCreate(BaseModel):
    """작업일지 생성 모델"""
    날짜: str
    업체명: str
    분류: str
    단가: int
    수량: int = 1
    비고1: Optional[str] = None
    작성자: Optional[str] = None
    출처: str = "manual"  # 'bot', 'excel', 'manual'
    works_user_id: Optional[str] = None


class WorkLogUpdate(BaseModel):
    """작업일지 수정 모델"""
    날짜: Optional[str] = None
    업체명: Optional[str] = None
    분류: Optional[str] = None
    단가: Optional[int] = None
    수량: Optional[int] = None
    비고1: Optional[str] = None


class WorkLogResponse(BaseModel):
    """작업일지 응답 모델"""
    id: int
    날짜: Optional[str]
    업체명: Optional[str]
    분류: Optional[str]
    단가: Optional[int]
    수량: Optional[int]
    합계: Optional[int]
    비고1: Optional[str]
    작성자: Optional[str]
    저장시간: Optional[str]
    출처: Optional[str]


# ─────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────

def ensure_work_log_columns():
    """work_log 테이블에 새 컬럼 추가 (기존 데이터 보존)"""
    with get_connection() as con:
        # 테이블 존재 확인
        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_log'"
        ).fetchone()
        
        if not table_exists:
            return
        
        # 기존 컬럼 확인
        existing_cols = [c[1] for c in con.execute("PRAGMA table_info(work_log);")]
        
        # 새 컬럼 추가
        new_cols = [
            ("작성자", "TEXT"),
            ("저장시간", "TIMESTAMP"),
            ("출처", "TEXT"),
            ("works_user_id", "TEXT"),
        ]
        
        for col, coltype in new_cols:
            if col not in existing_cols:
                try:
                    con.execute(f"ALTER TABLE work_log ADD COLUMN [{col}] {coltype};")
                except Exception:
                    pass
        
        con.commit()


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.get("")
@router.get("/")
async def get_work_logs(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    vendor: Optional[str] = None,
    work_type: Optional[str] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(default=500, le=2000),
    offset: int = 0,
):
    """
    작업일지 목록 조회
    
    Args:
        period_from: 시작일 (YYYY-MM-DD)
        period_to: 종료일 (YYYY-MM-DD)
        vendor: 업체명 필터
        work_type: 작업 종류 필터
        author: 작성자 필터
        source: 출처 필터 ('bot', 'excel', 'manual')
        limit: 조회 건수 제한
        offset: 오프셋
    """
    ensure_work_log_columns()
    
    with get_connection() as con:
        # 기본 쿼리
        query = "SELECT * FROM work_log WHERE 1=1"
        params = []
        
        if period_from:
            query += " AND 날짜 >= ?"
            params.append(period_from)
        
        if period_to:
            query += " AND 날짜 <= ?"
            params.append(period_to)
        
        if vendor:
            query += " AND 업체명 LIKE ?"
            params.append(f"%{vendor}%")
        
        if work_type:
            query += " AND 분류 LIKE ?"
            params.append(f"%{work_type}%")
        
        if author:
            query += " AND 작성자 LIKE ?"
            params.append(f"%{author}%")
        
        if source:
            query += " AND 출처 = ?"
            params.append(source)
        
        # 정렬 및 페이지네이션
        query += " ORDER BY COALESCE(저장시간, 날짜) DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        df = pd.read_sql(query, con, params=params)
        
        # 전체 건수
        count_query = "SELECT COUNT(*) FROM work_log WHERE 1=1"
        count_params = params[:-2]  # limit, offset 제외
        
        # 필터 적용된 count 쿼리 재구성
        count_query = "SELECT COUNT(*) FROM work_log WHERE 1=1"
        count_params = []
        if period_from:
            count_query += " AND 날짜 >= ?"
            count_params.append(period_from)
        if period_to:
            count_query += " AND 날짜 <= ?"
            count_params.append(period_to)
        if vendor:
            count_query += " AND 업체명 LIKE ?"
            count_params.append(f"%{vendor}%")
        if work_type:
            count_query += " AND 분류 LIKE ?"
            count_params.append(f"%{work_type}%")
        if author:
            count_query += " AND 작성자 LIKE ?"
            count_params.append(f"%{author}%")
        if source:
            count_query += " AND 출처 = ?"
            count_params.append(source)
        
        total = con.execute(count_query, count_params).fetchone()[0]
        
        # 필터 옵션들
        vendors = pd.read_sql(
            "SELECT DISTINCT 업체명 FROM work_log WHERE 업체명 IS NOT NULL ORDER BY 업체명", con
        )['업체명'].tolist()
        
        work_types = pd.read_sql(
            "SELECT DISTINCT 분류 FROM work_log WHERE 분류 IS NOT NULL ORDER BY 분류", con
        )['분류'].tolist()
        
        authors = pd.read_sql(
            "SELECT DISTINCT 작성자 FROM work_log WHERE 작성자 IS NOT NULL ORDER BY 작성자", con
        )['작성자'].tolist()
    
    # 응답 구성
    logs = []
    for _, row in df.iterrows():
        logs.append({
            "id": int(row['id']) if 'id' in row else None,
            "날짜": row.get('날짜'),
            "업체명": row.get('업체명'),
            "분류": row.get('분류'),
            "단가": int(row['단가']) if pd.notna(row.get('단가')) else None,
            "수량": int(row['수량']) if pd.notna(row.get('수량')) else None,
            "합계": int(row['합계']) if pd.notna(row.get('합계')) else None,
            "비고1": row.get('비고1') if pd.notna(row.get('비고1')) else None,
            "작성자": row.get('작성자') if pd.notna(row.get('작성자')) else None,
            "저장시간": str(row['저장시간']) if pd.notna(row.get('저장시간')) else None,
            "출처": row.get('출처') if pd.notna(row.get('출처')) else None,
        })
    
    return {
        "logs": logs,
        "total": total,
        "filters": {
            "vendors": vendors,
            "work_types": work_types,
            "authors": authors,
            "sources": ["bot", "excel", "manual"],
        }
    }


@router.get("/stats")
async def get_work_log_stats(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
):
    """작업일지 통계"""
    ensure_work_log_columns()
    
    with get_connection() as con:
        # 기간 조건
        where = "WHERE 1=1"
        params = []
        if period_from:
            where += " AND 날짜 >= ?"
            params.append(period_from)
        if period_to:
            where += " AND 날짜 <= ?"
            params.append(period_to)
        
        # 전체 건수
        total = con.execute(f"SELECT COUNT(*) FROM work_log {where}", params).fetchone()[0]
        
        # 전체 금액
        total_amount = con.execute(
            f"SELECT COALESCE(SUM(합계), 0) FROM work_log {where}", params
        ).fetchone()[0]
        
        # 오늘 건수
        today = con.execute(
            f"SELECT COUNT(*) FROM work_log {where} AND 날짜 = date('now')", params
        ).fetchone()[0]
        
        # 업체별 통계
        by_vendor = pd.read_sql(
            f"""SELECT 업체명, COUNT(*) as count, SUM(합계) as total_amount 
                FROM work_log {where} AND 업체명 IS NOT NULL
                GROUP BY 업체명 ORDER BY total_amount DESC LIMIT 10""",
            con, params=params
        ).to_dict(orient='records')
        
        # 작업 종류별 통계
        by_work_type = pd.read_sql(
            f"""SELECT 분류, COUNT(*) as count, SUM(합계) as total_amount 
                FROM work_log {where} AND 분류 IS NOT NULL
                GROUP BY 분류 ORDER BY total_amount DESC LIMIT 10""",
            con, params=params
        ).to_dict(orient='records')
        
        # 출처별 통계
        by_source = pd.read_sql(
            f"""SELECT COALESCE(출처, 'unknown') as 출처, COUNT(*) as count 
                FROM work_log {where}
                GROUP BY 출처 ORDER BY count DESC""",
            con, params=params
        ).to_dict(orient='records')
    
    return {
        "total": total,
        "total_amount": int(total_amount) if total_amount else 0,
        "today": today,
        "by_vendor": by_vendor,
        "by_work_type": by_work_type,
        "by_source": by_source,
    }


@router.post("")
async def create_work_log(log: WorkLogCreate):
    """작업일지 생성"""
    ensure_work_log_columns()
    
    합계 = log.단가 * log.수량
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        cursor = con.execute(
            """INSERT INTO work_log 
               (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.날짜, log.업체명, log.분류, log.단가, log.수량, 합계, 
             log.비고1, log.작성자, 저장시간, log.출처, log.works_user_id)
        )
        con.commit()
        log_id = cursor.lastrowid
    
    # 활동 로그 기록
    출처_label = {"bot": "봇", "excel": "엑셀", "manual": "수동"}.get(log.출처, log.출처)
    add_log(
        action_type="작업일지_생성",
        target_type="work_log",
        target_id=str(log_id),
        target_name=f"{log.업체명} {log.분류}",
        user_nickname=log.작성자 or "시스템",
        details=f"날짜: {log.날짜}, 합계: {합계:,}원 ({출처_label})"
    )
    
    return {
        "success": True,
        "id": log_id,
        "message": "작업일지가 저장되었습니다."
    }


@router.put("/{log_id}")
async def update_work_log(log_id: int, log: WorkLogUpdate):
    """작업일지 수정"""
    ensure_work_log_columns()
    
    with get_connection() as con:
        # 기존 레코드 확인
        existing = con.execute(
            "SELECT * FROM work_log WHERE id = ?", (log_id,)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="작업일지를 찾을 수 없습니다.")
        
        # 컬럼 정보 가져오기 (수정 전 데이터 기록용)
        cols = [c[0] for c in con.execute("PRAGMA table_info(work_log);").fetchall()]
        existing_data = dict(zip(cols, existing))
        
        # 업데이트할 필드 구성
        update_fields = []
        params = []
        changed_fields = []
        
        if log.날짜 is not None:
            update_fields.append("날짜 = ?")
            params.append(log.날짜)
            changed_fields.append(f"날짜: {existing_data.get('날짜')} → {log.날짜}")
        
        if log.업체명 is not None:
            update_fields.append("업체명 = ?")
            params.append(log.업체명)
            changed_fields.append(f"업체명: {existing_data.get('업체명')} → {log.업체명}")
        
        if log.분류 is not None:
            update_fields.append("분류 = ?")
            params.append(log.분류)
            changed_fields.append(f"분류: {existing_data.get('분류')} → {log.분류}")
        
        if log.단가 is not None:
            update_fields.append("단가 = ?")
            params.append(log.단가)
            changed_fields.append(f"단가: {existing_data.get('단가'):,}원 → {log.단가:,}원")
        
        if log.수량 is not None:
            update_fields.append("수량 = ?")
            params.append(log.수량)
            changed_fields.append(f"수량: {existing_data.get('수량')} → {log.수량}")
        
        if log.비고1 is not None:
            update_fields.append("비고1 = ?")
            params.append(log.비고1)
        
        # 합계 재계산
        if log.단가 is not None or log.수량 is not None:
            new_단가 = log.단가 if log.단가 is not None else existing_data.get('단가', 0)
            new_수량 = log.수량 if log.수량 is not None else existing_data.get('수량', 1)
            update_fields.append("합계 = ?")
            params.append(new_단가 * new_수량)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")
        
        params.append(log_id)
        query = f"UPDATE work_log SET {', '.join(update_fields)} WHERE id = ?"
        con.execute(query, params)
        con.commit()
    
    # 활동 로그 기록
    add_log(
        action_type="작업일지_수정",
        target_type="work_log",
        target_id=str(log_id),
        target_name=f"{log.업체명 or existing_data.get('업체명')} {log.분류 or existing_data.get('분류')}",
        user_nickname="웹",
        details=", ".join(changed_fields) if changed_fields else "수정됨"
    )
    
    return {"success": True, "message": "작업일지가 수정되었습니다."}


@router.delete("/{log_id}")
async def delete_work_log(log_id: int):
    """작업일지 삭제"""
    with get_connection() as con:
        # 삭제 전 데이터 조회 (로그용)
        existing = con.execute(
            "SELECT id, 날짜, 업체명, 분류, 합계 FROM work_log WHERE id = ?", (log_id,)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="작업일지를 찾을 수 없습니다.")
        
        날짜 = existing[1]
        업체명 = existing[2]
        분류 = existing[3]
        합계 = existing[4] or 0
        
        con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
        con.commit()
    
    # 활동 로그 기록
    add_log(
        action_type="작업일지_삭제",
        target_type="work_log",
        target_id=str(log_id),
        target_name=f"{업체명} {분류}",
        user_nickname="웹",
        details=f"날짜: {날짜}, 합계: {합계:,}원"
    )
    
    return {"success": True, "message": "작업일지가 삭제되었습니다."}


@router.get("/check-duplicate")
async def check_duplicate(
    날짜: str,
    업체명: str,
    분류: str,
    수량: int,
    단가: int,
):
    """중복 작업일지 확인"""
    with get_connection() as con:
        row = con.execute(
            """SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간 
               FROM work_log 
               WHERE 날짜 = ? AND 업체명 = ? AND 분류 = ? AND 수량 = ? AND 단가 = ?
               ORDER BY 저장시간 DESC LIMIT 1""",
            (날짜, 업체명, 분류, 수량, 단가)
        ).fetchone()
        
        if row:
            return {
                "is_duplicate": True,
                "existing": {
                    "id": row[0],
                    "날짜": row[1],
                    "업체명": row[2],
                    "분류": row[3],
                    "수량": row[4],
                    "단가": row[5],
                    "합계": row[6],
                    "저장시간": str(row[7]) if row[7] else None,
                }
            }
        
        return {"is_duplicate": False, "existing": None}


@router.get("/export")
async def export_work_logs(
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    format: str = Query("excel", description="출력 형식 (excel, csv, json)")
):
    """
    기간별 작업일지 내보내기
    
    Args:
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD)
        format: 출력 형식 (excel, csv, json)
    """
    from fastapi.responses import StreamingResponse
    import io
    
    with get_connection() as con:
        rows = con.execute(
            """SELECT 날짜, 업체명, 분류, 수량, 단가, 합계, 비고1, 작성자, 출처, 저장시간
               FROM work_log 
               WHERE 날짜 >= ? AND 날짜 <= ?
               ORDER BY 날짜 DESC, id DESC""",
            (start_date, end_date)
        ).fetchall()
    
    if not rows:
        raise HTTPException(status_code=404, detail="해당 기간에 작업일지가 없습니다.")
    
    # DataFrame 생성
    df = pd.DataFrame(rows, columns=[
        "날짜", "업체명", "분류", "수량", "단가", "합계", "비고", "작성자", "출처", "저장시간"
    ])
    
    if format == "json":
        return {
            "period": f"{start_date} ~ {end_date}",
            "total_count": len(rows),
            "total_amount": int(df["합계"].sum()),
            "data": df.to_dict(orient="records")
        }
    
    elif format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False, encoding="utf-8-sig")
        output.seek(0)
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=work_log_{start_date}_{end_date}.csv"
            }
        )
    
    else:  # excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="작업일지")
            
            # 요약 시트 추가
            summary_by_vendor = df.groupby("업체명").agg({
                "합계": "sum",
                "날짜": "count"
            }).rename(columns={"날짜": "건수"}).reset_index()
            summary_by_vendor.to_excel(writer, index=False, sheet_name="업체별 요약")
            
            summary_by_type = df.groupby("분류").agg({
                "합계": "sum",
                "날짜": "count"
            }).rename(columns={"날짜": "건수"}).reset_index()
            summary_by_type.to_excel(writer, index=False, sheet_name="작업별 요약")
        
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=work_log_{start_date}_{end_date}.xlsx"
            }
        )


# ─────────────────────────────────────
# /{log_id} 엔드포인트는 /export, /check-duplicate 보다 뒤에 위치해야 함
# ─────────────────────────────────────

@router.get("/{log_id}")
async def get_work_log(log_id: int):
    """작업일지 상세 조회"""
    ensure_work_log_columns()
    
    with get_connection() as con:
        row = con.execute(
            "SELECT * FROM work_log WHERE id = ?", (log_id,)
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="작업일지를 찾을 수 없습니다.")
        
        cols = [c[0] for c in con.execute("PRAGMA table_info(work_log);").fetchall()]
        data = dict(zip(cols, row))
    
    return {
        "id": data.get('id'),
        "날짜": data.get('날짜'),
        "업체명": data.get('업체명'),
        "분류": data.get('분류'),
        "단가": data.get('단가'),
        "수량": data.get('수량'),
        "합계": data.get('합계'),
        "비고1": data.get('비고1'),
        "작성자": data.get('작성자'),
        "저장시간": str(data['저장시간']) if data.get('저장시간') else None,
        "출처": data.get('출처'),
    }
