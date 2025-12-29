"""
backend/app/api/invoices.py - 인보이스 목록 및 관리 API
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import pandas as pd
import io

from logic.db import get_connection
from backend.app.api.logs import add_log

router = APIRouter(prefix="/invoices", tags=["invoices"])


# ─────────────────────────────────────
# 권한 체크 헬퍼
# ─────────────────────────────────────

def check_admin(token: Optional[str]) -> tuple:
    """관리자 권한 확인, (is_admin, nickname) 반환"""
    if not token:
        return False, None
    with get_connection() as con:
        result = con.execute(
            "SELECT u.is_admin, u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        if result:
            return bool(result[0]), result[1]
    return False, None


def get_user_nickname(token: Optional[str]) -> str:
    """토큰에서 닉네임 가져오기"""
    if not token:
        return '시스템'
    with get_connection() as con:
        result = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        return result[0] if result else '시스템'


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.get("")
@router.get("/")
async def list_invoices(
    period: Optional[str] = None,
    vendor: Optional[str] = None,
    status: Optional[str] = None
):
    """인보이스 목록 조회"""
    try:
        with get_connection() as con:
            # 테이블 존재 확인
            tables = [row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            
            if "invoices" not in tables:
                return {"invoices": [], "total": 0, "sum_amount": 0}
            
            # 컬럼 존재 확인
            cols = [c[1] for c in con.execute("PRAGMA table_info(invoices);")]
            has_modified_by = 'modified_by' in cols
            has_confirmed_by = 'confirmed_by' in cols
            
            # 기본 쿼리
            select_cols = """
                    i.invoice_id,
                    i.vendor_id,
                    COALESCE(v.name, v.vendor, i.vendor_id) as vendor_name,
                    i.period_from,
                    i.period_to,
                    i.total_amount,
                    COALESCE(i.status, '미확정') as status,
                    i.created_at"""
            
            if has_modified_by:
                select_cols += ", i.modified_by, i.modified_at"
            if has_confirmed_by:
                select_cols += ", i.confirmed_by, i.confirmed_at"
            
            query = f"""
                SELECT {select_cols}
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE 1=1
            """
            params = []
            
            # 필터 적용
            if period:
                query += " AND strftime('%Y-%m', i.period_from) = ?"
                params.append(period)
            
            if vendor:
                query += " AND (v.vendor = ? OR v.name = ?)"
                params.extend([vendor, vendor])
            
            if status:
                query += " AND i.status = ?"
                params.append(status)
            
            query += " ORDER BY i.invoice_id DESC"
            
            df = pd.read_sql(query, con, params=params)
            
            # 합계 계산
            df['total_amount'] = pd.to_numeric(df['total_amount'], errors='coerce').fillna(0)
            sum_amount = int(df['total_amount'].sum())
            
            invoices = []
            for _, row in df.iterrows():
                inv_data = {
                    "invoice_id": int(row['invoice_id']),
                    "vendor_id": row['vendor_id'],
                    "vendor": str(row['vendor_name']) if row['vendor_name'] else '',
                    "period_from": str(row['period_from']) if row['period_from'] else '',
                    "period_to": str(row['period_to']) if row['period_to'] else '',
                    "total_amount": int(row['total_amount']),
                    "status": str(row['status']),
                    "created_at": str(row['created_at']) if row['created_at'] else '',
                    "modified_by": str(row['modified_by']) if has_modified_by and pd.notna(row.get('modified_by')) else None,
                    "modified_at": str(row['modified_at']) if has_modified_by and pd.notna(row.get('modified_at')) else None,
                    "confirmed_by": str(row['confirmed_by']) if has_confirmed_by and pd.notna(row.get('confirmed_by')) else None,
                    "confirmed_at": str(row['confirmed_at']) if has_confirmed_by and pd.notna(row.get('confirmed_at')) else None,
                }
                invoices.append(inv_data)
            
            # 사용 가능한 기간 목록
            periods_df = pd.read_sql(
                "SELECT DISTINCT strftime('%Y-%m', period_from) as ym FROM invoices ORDER BY ym DESC",
                con
            )
            periods = periods_df['ym'].dropna().tolist()
            
            return {
                "invoices": invoices,
                "total": len(invoices),
                "sum_amount": sum_amount,
                "periods": periods
            }
    
    except Exception as e:
        return {"invoices": [], "total": 0, "sum_amount": 0, "error": str(e)}


@router.get("/{invoice_id}")
async def get_invoice_detail(invoice_id: int):
    """인보이스 상세 조회"""
    try:
        with get_connection() as con:
            # 인보이스 기본 정보
            inv_df = pd.read_sql(
                """
                SELECT 
                    i.invoice_id,
                    i.vendor_id,
                    COALESCE(v.name, v.vendor) as vendor_name,
                    i.period_from,
                    i.period_to,
                    i.total_amount,
                    COALESCE(i.status, '미확정') as status,
                    i.created_at
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE i.invoice_id = ?
                """,
                con, params=[invoice_id]
            )
            
            if inv_df.empty:
                raise HTTPException(status_code=404, detail="Invoice not found")
            
            inv = inv_df.iloc[0]
            
            # 인보이스 항목
            items_df = pd.read_sql(
                "SELECT item_name, qty, unit_price, amount, remark FROM invoice_items WHERE invoice_id = ?",
                con, params=[invoice_id]
            )
            
            items = []
            for _, row in items_df.iterrows():
                items.append({
                    "항목": str(row['item_name']) if row['item_name'] else '',
                    "수량": int(row['qty']) if pd.notna(row['qty']) else 0,
                    "단가": int(row['unit_price']) if pd.notna(row['unit_price']) else 0,
                    "금액": int(row['amount']) if pd.notna(row['amount']) else 0,
                    "비고": str(row['remark']) if row['remark'] else ''
                })
            
            return {
                "invoice_id": int(inv['invoice_id']),
                "vendor": str(inv['vendor_name']) if inv['vendor_name'] else '',
                "period_from": str(inv['period_from']) if inv['period_from'] else '',
                "period_to": str(inv['period_to']) if inv['period_to'] else '',
                "total_amount": int(inv['total_amount']) if pd.notna(inv['total_amount']) else 0,
                "status": str(inv['status']),
                "created_at": str(inv['created_at']) if inv['created_at'] else '',
                "items": items
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: int, token: Optional[str] = None):
    """인보이스 삭제 (관리자만)"""
    # 관리자 권한 체크
    is_admin, nickname = check_admin(token)
    if not is_admin:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    try:
        with get_connection() as con:
            # 삭제 전 인보이스 정보 가져오기
            inv = con.execute(
                "SELECT vendor_id FROM invoices WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()
            vendor_name = inv[0] if inv else "알 수 없음"
            
            con.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            con.execute("DELETE FROM invoices WHERE invoice_id = ?", (invoice_id,))
            con.commit()
        
        # 로그 기록
        add_log(
            action_type="인보이스 삭제",
            target_type="invoice",
            target_id=str(invoice_id),
            target_name=vendor_name,
            user_nickname=nickname,
            details=f"인보이스 ID {invoice_id} 삭제"
        )
        
        return {"status": "success", "deleted": invoice_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{invoice_id}/confirm")
async def confirm_invoice(invoice_id: int, token: Optional[str] = None, user_nickname: Optional[str] = None):
    """인보이스 확정"""
    try:
        with get_connection() as con:
            # 컬럼 존재 확인 및 추가
            ensure_invoice_user_columns(con)
            
            # 사용자 닉네임 가져오기
            nickname = user_nickname or get_nickname_from_token(con, token) or '시스템'
            
            # 인보이스 정보 가져오기
            inv = con.execute(
                "SELECT vendor_id FROM invoices WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()
            vendor_name = inv[0] if inv else "알 수 없음"
            
            con.execute(
                "UPDATE invoices SET status = '확정', confirmed_by = ?, confirmed_at = CURRENT_TIMESTAMP WHERE invoice_id = ?",
                (nickname, invoice_id)
            )
            con.commit()
        
        # 로그 기록
        add_log(
            action_type="인보이스 확정",
            target_type="invoice",
            target_id=str(invoice_id),
            target_name=vendor_name,
            user_nickname=nickname,
            details=f"인보이스 ID {invoice_id} 확정 처리"
        )
        
        return {"status": "success", "invoice_id": invoice_id, "new_status": "확정", "confirmed_by": nickname}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{invoice_id}/unconfirm")
async def unconfirm_invoice(invoice_id: int, token: Optional[str] = None, user_nickname: Optional[str] = None):
    """인보이스 미확정으로 변경"""
    try:
        with get_connection() as con:
            # 컬럼 존재 확인 및 추가
            ensure_invoice_user_columns(con)
            
            # 사용자 닉네임 가져오기
            nickname = user_nickname or get_nickname_from_token(con, token) or '시스템'
            
            # 인보이스 정보 가져오기
            inv = con.execute(
                "SELECT vendor_id FROM invoices WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()
            vendor_id = inv[0] if inv else "알 수 없음"
            
            con.execute(
                "UPDATE invoices SET status = '미확정', confirmed_by = NULL, confirmed_at = NULL, modified_by = ?, modified_at = CURRENT_TIMESTAMP WHERE invoice_id = ?",
                (nickname, invoice_id)
            )
            con.commit()
        
        # 로그 기록
        add_log(
            action_type="인보이스 미확정",
            target_type="invoice",
            target_id=str(invoice_id),
            target_name=vendor_id,
            user_nickname=nickname,
            details=f"인보이스 ID {invoice_id} 미확정 처리"
        )
        
        return {"status": "success", "invoice_id": invoice_id, "new_status": "미확정", "modified_by": nickname}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel

class InvoiceItemUpdate(BaseModel):
    항목: str
    수량: int
    단가: int
    금액: int
    비고: str = ""

class InvoiceUpdateRequest(BaseModel):
    items: List[InvoiceItemUpdate]
    user_nickname: Optional[str] = None


def ensure_invoice_user_columns(con):
    """인보이스 테이블에 사용자 관련 컬럼 추가"""
    cols = [c[1] for c in con.execute("PRAGMA table_info(invoices);")]
    if 'modified_by' not in cols:
        con.execute("ALTER TABLE invoices ADD COLUMN modified_by TEXT;")
    if 'modified_at' not in cols:
        con.execute("ALTER TABLE invoices ADD COLUMN modified_at DATETIME;")
    if 'confirmed_by' not in cols:
        con.execute("ALTER TABLE invoices ADD COLUMN confirmed_by TEXT;")
    if 'confirmed_at' not in cols:
        con.execute("ALTER TABLE invoices ADD COLUMN confirmed_at DATETIME;")


def get_nickname_from_token(con, token: Optional[str]) -> Optional[str]:
    """토큰에서 사용자 닉네임 가져오기"""
    if not token:
        return None
    try:
        result = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        return result[0] if result else None
    except:
        return None


@router.put("/{invoice_id}/items")
async def update_invoice_items(invoice_id: int, request: InvoiceUpdateRequest, token: Optional[str] = None):
    """인보이스 항목 수정"""
    try:
        with get_connection() as con:
            # 컬럼 존재 확인 및 추가
            ensure_invoice_user_columns(con)
            
            # 기존 인보이스 확인
            existing = con.execute(
                "SELECT invoice_id, vendor_id FROM invoices WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()
            
            if not existing:
                raise HTTPException(status_code=404, detail="Invoice not found")
            
            vendor_name = existing[1] if existing[1] else "알 수 없음"
            
            # 사용자 닉네임
            nickname = request.user_nickname or get_nickname_from_token(con, token) or '시스템'
            
            # 기존 항목 삭제
            con.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            
            # 새 항목 삽입
            total_amount = 0
            for item in request.items:
                con.execute(
                    "INSERT INTO invoice_items (invoice_id, item_name, qty, unit_price, amount, remark) VALUES (?, ?, ?, ?, ?, ?)",
                    (invoice_id, item.항목, item.수량, item.단가, item.금액, item.비고)
                )
                total_amount += item.금액
            
            # 총액 및 수정자 업데이트
            con.execute(
                "UPDATE invoices SET total_amount = ?, modified_by = ?, modified_at = CURRENT_TIMESTAMP WHERE invoice_id = ?",
                (total_amount, nickname, invoice_id)
            )
            
            con.commit()
        
        # 로그 기록
        add_log(
            action_type="인보이스 수정",
            target_type="invoice",
            target_id=str(invoice_id),
            target_name=vendor_name,
            user_nickname=nickname,
            details=f"인보이스 ID {invoice_id} 항목 수정, 총액: {total_amount:,}원"
        )
            
        return {
            "status": "success",
            "invoice_id": invoice_id,
            "item_count": len(request.items),
            "total_amount": total_amount,
            "modified_by": nickname
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/batch/delete")
async def delete_invoices_batch(invoice_ids: List[int], token: Optional[str] = None):
    """인보이스 일괄 삭제 (관리자만)"""
    # 관리자 권한 체크
    is_admin, nickname = check_admin(token)
    if not is_admin:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    try:
        with get_connection() as con:
            for iid in invoice_ids:
                con.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (iid,))
                con.execute("DELETE FROM invoices WHERE invoice_id = ?", (iid,))
            con.commit()
        
        # 로그 기록
        add_log(
            action_type="인보이스 일괄 삭제",
            target_type="invoice",
            target_id=",".join(str(i) for i in invoice_ids),
            target_name=f"{len(invoice_ids)}건",
            user_nickname=nickname,
            details=f"인보이스 {len(invoice_ids)}건 일괄 삭제: {invoice_ids}"
        )
        
        return {"status": "success", "deleted_count": len(invoice_ids)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/xlsx")
async def export_invoices_xlsx(
    period: Optional[str] = None,
    vendor: Optional[str] = None,
    invoice_ids: Optional[str] = None  # comma-separated
):
    """인보이스 엑셀 다운로드"""
    try:
        with get_connection() as con:
            # ID 목록 파싱
            ids_list = None
            if invoice_ids:
                ids_list = [int(x.strip()) for x in invoice_ids.split(',') if x.strip()]
            
            # 인보이스 조회
            query = """
                SELECT 
                    i.invoice_id,
                    COALESCE(v.name, v.vendor, i.vendor_id) as vendor_name,
                    i.period_from,
                    i.period_to,
                    i.total_amount,
                    COALESCE(i.status, '미확정') as status
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE 1=1
            """
            params = []
            
            if ids_list:
                placeholders = ','.join(['?' for _ in ids_list])
                query += f" AND i.invoice_id IN ({placeholders})"
                params.extend(ids_list)
            elif period:
                query += " AND strftime('%Y-%m', i.period_from) = ?"
                params.append(period)
            
            if vendor:
                query += " AND (v.vendor = ? OR v.name = ?)"
                params.extend([vendor, vendor])
            
            query += " ORDER BY i.invoice_id DESC"
            
            inv_df = pd.read_sql(query, con, params=params)
            
            if inv_df.empty:
                raise HTTPException(status_code=404, detail="No invoices found")
            
            invoice_ids_list = inv_df['invoice_id'].tolist()
            
            # 모든 항목 조회
            if invoice_ids_list:
                placeholders = ','.join(['?' for _ in invoice_ids_list])
                items_df = pd.read_sql(
                    f"SELECT invoice_id, item_name, qty, unit_price, amount, remark FROM invoice_items WHERE invoice_id IN ({placeholders})",
                    con, params=invoice_ids_list
                )
            else:
                items_df = pd.DataFrame()
            
            # 엑셀 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 인보이스 목록 시트
                inv_df[['invoice_id', 'vendor_name', 'period_from', 'period_to', 'total_amount', 'status']].to_excel(
                    writer, sheet_name='Invoice_List', index=False
                )
                
                # 각 인보이스별 시트
                for _, inv_row in inv_df.iterrows():
                    iid = inv_row['invoice_id']
                    vendor_nm = str(inv_row['vendor_name'])[:20] if inv_row['vendor_name'] else 'Unknown'
                    sheet_name = f"{vendor_nm}_{iid}"[:31]
                    
                    inv_items = items_df[items_df['invoice_id'] == iid].copy()
                    if not inv_items.empty:
                        inv_items[['item_name', 'qty', 'unit_price', 'amount', 'remark']].to_excel(
                            writer, sheet_name=sheet_name, index=False
                        )
            
            output.seek(0)
            
            filename = f"invoices_{period if period else 'all'}.xlsx"
            
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{invoice_id}/export/xlsx")
async def export_single_invoice_xlsx(invoice_id: int):
    """단일 인보이스 엑셀 다운로드"""
    try:
        with get_connection() as con:
            # 인보이스 정보
            inv_df = pd.read_sql(
                """
                SELECT 
                    i.invoice_id,
                    COALESCE(v.name, v.vendor) as vendor_name,
                    i.period_from
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE i.invoice_id = ?
                """,
                con, params=[invoice_id]
            )
            
            if inv_df.empty:
                raise HTTPException(status_code=404, detail="Invoice not found")
            
            inv = inv_df.iloc[0]
            vendor_name = str(inv['vendor_name']) if inv['vendor_name'] else 'Unknown'
            period = str(inv['period_from'])[:7] if inv['period_from'] else ''
            
            # 항목 조회
            items_df = pd.read_sql(
                "SELECT item_name as 항목, qty as 수량, unit_price as 단가, amount as 금액, remark as 비고 FROM invoice_items WHERE invoice_id = ?",
                con, params=[invoice_id]
            )
            
            # 엑셀 생성
            output = io.BytesIO()
            
            # 시트명은 31자 제한, 특수문자 제거
            import re
            safe_sheet_name = re.sub(r'[\\/*?:\[\]]', '', vendor_name)[:31] or 'Invoice'
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                items_df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
            
            output.seek(0)
            
            # 파일명 생성 (ASCII만 사용)
            ascii_filename = f"invoice_{invoice_id}_{period}.xlsx"
            
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f"attachment; filename={ascii_filename}"
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

