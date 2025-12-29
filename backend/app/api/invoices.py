"""
backend/app/api/invoices.py - 인보이스 목록 및 관리 API
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import pandas as pd
import io

from logic.db import get_connection

router = APIRouter(prefix="/invoices", tags=["invoices"])


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
            
            # 기본 쿼리
            query = """
                SELECT 
                    i.invoice_id,
                    i.vendor_id,
                    COALESCE(v.name, v.vendor, i.vendor_id) as vendor_name,
                    i.period_from,
                    i.period_to,
                    i.total_amount,
                    COALESCE(i.status, '미확정') as status,
                    i.created_at
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
                invoices.append({
                    "invoice_id": int(row['invoice_id']),
                    "vendor_id": row['vendor_id'],
                    "vendor": str(row['vendor_name']) if row['vendor_name'] else '',
                    "period_from": str(row['period_from']) if row['period_from'] else '',
                    "period_to": str(row['period_to']) if row['period_to'] else '',
                    "total_amount": int(row['total_amount']),
                    "status": str(row['status']),
                    "created_at": str(row['created_at']) if row['created_at'] else ''
                })
            
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
async def delete_invoice(invoice_id: int):
    """인보이스 삭제"""
    try:
        with get_connection() as con:
            con.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            con.execute("DELETE FROM invoices WHERE invoice_id = ?", (invoice_id,))
            con.commit()
        return {"status": "success", "deleted": invoice_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{invoice_id}/confirm")
async def confirm_invoice(invoice_id: int):
    """인보이스 확정"""
    try:
        with get_connection() as con:
            con.execute("UPDATE invoices SET status = '확정' WHERE invoice_id = ?", (invoice_id,))
            con.commit()
        return {"status": "success", "invoice_id": invoice_id, "new_status": "확정"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/batch/delete")
async def delete_invoices_batch(invoice_ids: List[int]):
    """인보이스 일괄 삭제"""
    try:
        with get_connection() as con:
            for iid in invoice_ids:
                con.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (iid,))
                con.execute("DELETE FROM invoices WHERE invoice_id = ?", (iid,))
            con.commit()
        return {"status": "success", "deleted_count": len(invoice_ids)}
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
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                items_df.to_excel(writer, sheet_name=vendor_name[:31], index=False)
            
            output.seek(0)
            
            filename = f"{vendor_name}_{period}.xlsx"
            
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

