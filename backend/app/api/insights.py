"""
backend/app/api/insights.py - 데이터 인사이트 API
배송 통계, 인기 상품, 거래처별 분석 등
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
import pandas as pd
from datetime import datetime

from logic.db import get_connection

router = APIRouter(prefix="/insights", tags=["insights"])


# ─────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────

def get_shipping_data(period: Optional[str] = None) -> pd.DataFrame:
    """배송 통계 데이터 로드"""
    with get_connection() as con:
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
    
    if df.empty:
        return df
    
    # 날짜 컬럼 찾기 및 변환
    date_cols = ["배송일", "송장등록일", "출고일자", "기록일자"]
    date_col = next((c for c in date_cols if c in df.columns), None)
    
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df['년월'] = df[date_col].dt.strftime('%Y-%m')
        
        # 기간 필터 적용
        if period and period != "전체":
            df = df[df['년월'] == period]
    
    return df


def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """컬럼명 자동 감지"""
    return {
        'vendor': next((c for c in ["공급처", "업체", "vendor"] if c in df.columns), None),
        'item': next((c for c in ["상품명", "어드민상품명", "상품", "item"] if c in df.columns), None),
        'qty': next((c for c in ["수량", "qty", "Qty"] if c in df.columns), None),
        'amount': next((c for c in ["정산예정금액", "총금액", "금액", "amount"] if c in df.columns), None),
    }


# ─────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────

@router.get("/summary")
async def get_summary(period: Optional[str] = None):
    """핵심 지표 요약"""
    df = get_shipping_data(period)
    
    if df.empty:
        return {
            "total_orders": 0,
            "total_qty": 0,
            "total_vendors": 0,
            "total_amount": 0,
            "periods": []
        }
    
    cols = detect_columns(df)
    
    # 수량 숫자 변환
    if cols['qty']:
        df[cols['qty']] = pd.to_numeric(df[cols['qty']], errors='coerce').fillna(0)
    
    # 금액 숫자 변환
    if cols['amount'] and cols['amount'] in df.columns:
        df[cols['amount']] = pd.to_numeric(df[cols['amount']], errors='coerce').fillna(0)
    
    # 사용 가능한 기간 목록
    periods = []
    if '년월' in df.columns:
        periods = sorted(df['년월'].dropna().unique().tolist(), reverse=True)
    
    return {
        "total_orders": len(df),
        "total_qty": int(df[cols['qty']].sum()) if cols['qty'] else 0,
        "total_vendors": int(df[cols['vendor']].nunique()) if cols['vendor'] else 0,
        "total_amount": int(df[cols['amount']].sum()) if cols['amount'] and cols['amount'] in df.columns else 0,
        "periods": periods
    }


@router.get("/top-products")
async def get_top_products(period: Optional[str] = None, limit: int = 20):
    """인기 상품 TOP N"""
    df = get_shipping_data(period)
    
    if df.empty:
        return []
    
    cols = detect_columns(df)
    
    if not cols['item'] or not cols['qty']:
        return []
    
    df[cols['qty']] = pd.to_numeric(df[cols['qty']], errors='coerce').fillna(0)
    
    top_products = (df.groupby(cols['item'])[cols['qty']]
                    .sum()
                    .reset_index()
                    .sort_values(cols['qty'], ascending=False)
                    .head(limit))
    
    result = []
    for idx, row in top_products.iterrows():
        result.append({
            "rank": len(result) + 1,
            "product": str(row[cols['item']]),
            "quantity": int(row[cols['qty']])
        })
    
    return result


@router.get("/top-vendors-by-qty")
async def get_top_vendors_by_qty(period: Optional[str] = None, limit: int = 20):
    """거래처별 출고량 TOP N"""
    df = get_shipping_data(period)
    
    if df.empty:
        return []
    
    cols = detect_columns(df)
    
    if not cols['vendor'] or not cols['qty']:
        return []
    
    df[cols['qty']] = pd.to_numeric(df[cols['qty']], errors='coerce').fillna(0)
    
    vendor_stats = (df.groupby(cols['vendor'])
                    .agg({cols['qty']: ['sum', 'count']})
                    .reset_index())
    vendor_stats.columns = ['vendor', 'total_qty', 'order_count']
    vendor_stats = vendor_stats.sort_values('total_qty', ascending=False).head(limit)
    vendor_stats['avg_qty_per_order'] = (vendor_stats['total_qty'] / vendor_stats['order_count']).round(1)
    
    result = []
    for idx, row in vendor_stats.iterrows():
        result.append({
            "rank": len(result) + 1,
            "vendor": str(row['vendor']),
            "total_qty": int(row['total_qty']),
            "order_count": int(row['order_count']),
            "avg_qty_per_order": float(row['avg_qty_per_order'])
        })
    
    return result


@router.get("/top-vendors-by-revenue")
async def get_top_vendors_by_revenue(period: Optional[str] = None, limit: int = 20):
    """거래처별 매출 TOP N"""
    df = get_shipping_data(period)
    
    if df.empty:
        return []
    
    cols = detect_columns(df)
    
    if not cols['vendor'] or not cols['amount'] or cols['amount'] not in df.columns:
        return []
    
    df[cols['amount']] = pd.to_numeric(df[cols['amount']], errors='coerce').fillna(0)
    
    revenue_stats = (df.groupby(cols['vendor'])
                    .agg({cols['amount']: ['sum', 'count']})
                    .reset_index())
    revenue_stats.columns = ['vendor', 'total_revenue', 'order_count']
    revenue_stats = revenue_stats.sort_values('total_revenue', ascending=False).head(limit)
    revenue_stats['avg_order_value'] = (revenue_stats['total_revenue'] / revenue_stats['order_count']).round(0)
    
    result = []
    for idx, row in revenue_stats.iterrows():
        result.append({
            "rank": len(result) + 1,
            "vendor": str(row['vendor']),
            "total_revenue": int(row['total_revenue']),
            "order_count": int(row['order_count']),
            "avg_order_value": int(row['avg_order_value'])
        })
    
    return result


@router.get("/monthly-trend")
async def get_monthly_trend():
    """월별 트렌드"""
    df = get_shipping_data()
    
    if df.empty or '년월' not in df.columns:
        return []
    
    cols = detect_columns(df)
    
    if not cols['qty']:
        return []
    
    df[cols['qty']] = pd.to_numeric(df[cols['qty']], errors='coerce').fillna(0)
    
    monthly_stats = df.groupby('년월').agg({
        cols['qty']: 'sum',
        cols['vendor']: 'count' if cols['vendor'] else lambda x: len(x)
    }).reset_index()
    monthly_stats.columns = ['period', 'total_qty', 'order_count']
    
    if cols['amount'] and cols['amount'] in df.columns:
        df[cols['amount']] = pd.to_numeric(df[cols['amount']], errors='coerce').fillna(0)
        monthly_revenue = df.groupby('년월')[cols['amount']].sum().reset_index()
        monthly_revenue.columns = ['period', 'total_revenue']
        monthly_stats = monthly_stats.merge(monthly_revenue, on='period')
    
    monthly_stats = monthly_stats.sort_values('period')
    
    # 성장률 계산
    monthly_stats['qty_growth'] = monthly_stats['total_qty'].pct_change() * 100
    
    result = []
    for _, row in monthly_stats.iterrows():
        item = {
            "period": row['period'],
            "total_qty": int(row['total_qty']),
            "order_count": int(row['order_count']),
            "qty_growth": round(row['qty_growth'], 1) if pd.notna(row['qty_growth']) else None
        }
        if 'total_revenue' in row:
            item['total_revenue'] = int(row['total_revenue'])
        result.append(item)
    
    return result


@router.get("/our-revenue")
async def get_our_revenue(period: Optional[str] = None):
    """우리 매출 분석 (인보이스 기반)"""
    try:
        with get_connection() as con:
            # 날짜 필터
            date_filter = ""
            if period and period != "전체":
                date_filter = f"AND strftime('%Y-%m', i.period_from) = '{period}'"
            
            df_invoice = pd.read_sql(f"""
                SELECT 
                    i.invoice_id,
                    v.vendor as vendor,
                    v.name as vendor_name,
                    i.total_amount as amount,
                    COALESCE(
                        (SELECT SUM(qty) 
                         FROM invoice_items 
                         WHERE invoice_id = i.invoice_id 
                           AND (item_name LIKE '%기본%출고%' OR item_name = '기본 출고비')
                        ), 0
                    ) as base_order_count,
                    i.period_from,
                    i.period_to
                FROM invoices i
                JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE i.status != 'cancelled'
                  AND (v.active IS NULL OR v.active = 'YES')
                {date_filter}
            """, con)
        
        if df_invoice.empty:
            return {
                "total_invoices": 0,
                "total_revenue": 0,
                "total_orders": 0,
                "avg_order_value": 0,
                "vendors": []
            }
        
        # 객단가 계산
        df_invoice['order_value'] = df_invoice.apply(
            lambda row: row['amount'] / row['base_order_count'] if row['base_order_count'] > 0 else 0,
            axis=1
        )
        
        # 거래처별 집계
        vendor_stats = df_invoice.groupby(['vendor', 'vendor_name']).agg({
            'invoice_id': 'count',
            'amount': 'sum',
            'base_order_count': 'sum',
            'order_value': 'mean'
        }).reset_index()
        vendor_stats.columns = ['vendor', 'vendor_name', 'invoice_count', 'total_revenue', 'total_orders', 'avg_order_value']
        vendor_stats = vendor_stats.sort_values('total_revenue', ascending=False)
        
        # 전체 통계
        total_invoices = int(vendor_stats['invoice_count'].sum())
        total_revenue = int(vendor_stats['total_revenue'].sum())
        total_orders = int(vendor_stats['total_orders'].sum())
        avg_order_value = int(total_revenue / total_orders) if total_orders > 0 else 0
        
        vendors = []
        for idx, row in vendor_stats.iterrows():
            vendors.append({
                "rank": len(vendors) + 1,
                "vendor": str(row['vendor']),
                "vendor_name": str(row['vendor_name']) if row['vendor_name'] else str(row['vendor']),
                "invoice_count": int(row['invoice_count']),
                "total_revenue": int(row['total_revenue']),
                "total_orders": int(row['total_orders']),
                "avg_order_value": int(row['avg_order_value'])
            })
        
        return {
            "total_invoices": total_invoices,
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "avg_order_value": avg_order_value,
            "vendors": vendors
        }
    
    except Exception as e:
        return {
            "total_invoices": 0,
            "total_revenue": 0,
            "total_orders": 0,
            "avg_order_value": 0,
            "vendors": [],
            "error": str(e)
        }


@router.get("/vendor-detail/{vendor_name}")
async def get_vendor_detail(vendor_name: str, period: Optional[str] = None):
    """거래처별 상세 분석"""
    df = get_shipping_data(period)
    
    if df.empty:
        return {"error": "데이터 없음"}
    
    cols = detect_columns(df)
    
    if not cols['vendor']:
        return {"error": "거래처 컬럼 없음"}
    
    # 해당 거래처 필터
    df_vendor = df[df[cols['vendor']] == vendor_name]
    
    if df_vendor.empty:
        return {"error": "해당 거래처 데이터 없음"}
    
    df_vendor[cols['qty']] = pd.to_numeric(df_vendor[cols['qty']], errors='coerce').fillna(0)
    
    result = {
        "vendor": vendor_name,
        "total_orders": len(df_vendor),
        "total_qty": int(df_vendor[cols['qty']].sum()),
        "unique_products": int(df_vendor[cols['item']].nunique()) if cols['item'] else 0
    }
    
    if cols['amount'] and cols['amount'] in df_vendor.columns:
        df_vendor[cols['amount']] = pd.to_numeric(df_vendor[cols['amount']], errors='coerce').fillna(0)
        result['total_amount'] = int(df_vendor[cols['amount']].sum())
    
    # 상품별 판매량
    if cols['item']:
        top_items = (df_vendor.groupby(cols['item'])[cols['qty']]
                     .sum()
                     .sort_values(ascending=False)
                     .head(10))
        result['top_products'] = [
            {"product": str(k), "quantity": int(v)} 
            for k, v in top_items.items()
        ]
    
    return result


@router.get("/search")
async def search_data(
    vendor: Optional[str] = None,
    keyword: Optional[str] = None,
    period: Optional[str] = None,
    limit: int = 100
):
    """상세 검색"""
    df = get_shipping_data(period)
    
    if df.empty:
        return {"count": 0, "total_qty": 0, "data": []}
    
    cols = detect_columns(df)
    
    # 거래처 필터
    if vendor and vendor != "전체" and cols['vendor']:
        df = df[df[cols['vendor']] == vendor]
    
    # 키워드 필터
    if keyword and cols['item']:
        df = df[df[cols['item']].str.contains(keyword, case=False, na=False)]
    
    if cols['qty']:
        df[cols['qty']] = pd.to_numeric(df[cols['qty']], errors='coerce').fillna(0)
    
    total_qty = int(df[cols['qty']].sum()) if cols['qty'] else 0
    
    # 결과 반환
    display_cols = [c for c in [cols['vendor'], cols['item'], cols['qty'], cols['amount']] if c and c in df.columns]
    df_result = df[display_cols].head(limit)
    
    return {
        "count": len(df),
        "total_qty": total_qty,
        "data": df_result.to_dict(orient='records')
    }


@router.get("/vendors-list")
async def get_vendors_list(period: Optional[str] = None):
    """거래처 목록 조회"""
    df = get_shipping_data(period)
    
    if df.empty:
        return []
    
    cols = detect_columns(df)
    
    if not cols['vendor']:
        return []
    
    return sorted(df[cols['vendor']].dropna().unique().tolist())


# ─────────────────────────────────────
# 인보이스 기반 분석
# ─────────────────────────────────────

@router.get("/invoice-summary")
async def get_invoice_summary(period: Optional[str] = None):
    """인보이스 기반 전체 요약 (보관료, 택배비, 항목별 비용 등)"""
    try:
        with get_connection() as con:
            # 기간 필터
            date_filter = ""
            if period and period != "전체":
                date_filter = f"WHERE strftime('%Y-%m', i.period_from) = '{period}'"
            
            # 인보이스 목록
            df_invoices = pd.read_sql(f"""
                SELECT invoice_id, vendor_id, total_amount, period_from
                FROM invoices
                {date_filter}
            """, con)
            
            if df_invoices.empty:
                return {
                    "total_invoices": 0,
                    "total_amount": 0,
                    "total_storage_fee": 0,
                    "total_courier_fee": 0,
                    "total_basic_shipping": 0,
                    "total_box_fee": 0,
                    "category_breakdown": [],
                    "vendor_breakdown": [],
                    "periods": []
                }
            
            invoice_ids = df_invoices['invoice_id'].tolist()
            placeholders = ",".join(["?"] * len(invoice_ids))
            
            # 모든 인보이스 항목
            df_items = pd.read_sql(f"""
                SELECT ii.invoice_id, ii.item_name, ii.qty, ii.unit_price, ii.amount,
                       i.vendor_id, v.name as vendor_name
                FROM invoice_items ii
                JOIN invoices i ON ii.invoice_id = i.invoice_id
                LEFT JOIN vendors v ON i.vendor_id = v.vendor
                WHERE ii.invoice_id IN ({placeholders})
            """, con, params=invoice_ids)
            
            # 사용 가능한 기간 목록
            periods_df = pd.read_sql("""
                SELECT DISTINCT strftime('%Y-%m', period_from) as period
                FROM invoices
                ORDER BY period DESC
            """, con)
            periods = periods_df['period'].tolist()
        
        if df_items.empty:
            return {
                "total_invoices": len(df_invoices),
                "total_amount": int(df_invoices['total_amount'].sum()),
                "total_storage_fee": 0,
                "total_courier_fee": 0,
                "total_basic_shipping": 0,
                "total_box_fee": 0,
                "category_breakdown": [],
                "vendor_breakdown": [],
                "periods": periods
            }
        
        # 항목 분류
        def categorize_item(name: str) -> str:
            name_lower = name.lower() if name else ""
            if '보관료' in name_lower or '보관' in name_lower:
                return '보관료'
            elif '택배' in name_lower:
                return '택배요금'
            elif '기본' in name_lower and ('출고' in name_lower or '출고비' in name_lower):
                return '기본출고비'
            elif '박스' in name_lower or '봉투' in name_lower:
                return '박스/봉투'
            elif '입고' in name_lower and '검수' in name_lower:
                return '입고검수'
            elif '도서산간' in name_lower:
                return '도서산간'
            elif '합포장' in name_lower:
                return '합포장'
            elif '바코드' in name_lower:
                return '바코드'
            elif '완충' in name_lower:
                return '완충작업'
            elif '반품' in name_lower:
                return '반품'
            elif '영상' in name_lower or '촬영' in name_lower:
                return '영상촬영'
            else:
                return '기타'
        
        df_items['category'] = df_items['item_name'].apply(categorize_item)
        
        # 카테고리별 집계
        category_stats = df_items.groupby('category').agg({
            'amount': 'sum',
            'qty': 'sum',
            'item_name': 'count'
        }).reset_index()
        category_stats.columns = ['category', 'total_amount', 'total_qty', 'item_count']
        category_stats = category_stats.sort_values('total_amount', ascending=False)
        
        category_breakdown = []
        for _, row in category_stats.iterrows():
            category_breakdown.append({
                "category": row['category'],
                "total_amount": int(row['total_amount']),
                "total_qty": int(row['total_qty']),
                "item_count": int(row['item_count'])
            })
        
        # 거래처별 집계
        vendor_stats = df_items.groupby(['vendor_id', 'vendor_name']).agg({
            'amount': 'sum',
            'item_name': 'count'
        }).reset_index()
        vendor_stats.columns = ['vendor_id', 'vendor_name', 'total_amount', 'item_count']
        vendor_stats = vendor_stats.sort_values('total_amount', ascending=False)
        
        vendor_breakdown = []
        for _, row in vendor_stats.iterrows():
            vendor_breakdown.append({
                "vendor": row['vendor_id'],
                "vendor_name": row['vendor_name'] or row['vendor_id'],
                "total_amount": int(row['total_amount']),
                "item_count": int(row['item_count'])
            })
        
        # 주요 비용 합계
        total_storage = int(df_items[df_items['category'] == '보관료']['amount'].sum())
        total_courier = int(df_items[df_items['category'] == '택배요금']['amount'].sum())
        total_basic = int(df_items[df_items['category'] == '기본출고비']['amount'].sum())
        total_box = int(df_items[df_items['category'] == '박스/봉투']['amount'].sum())
        
        return {
            "total_invoices": len(df_invoices),
            "total_amount": int(df_invoices['total_amount'].sum()),
            "total_storage_fee": total_storage,
            "total_courier_fee": total_courier,
            "total_basic_shipping": total_basic,
            "total_box_fee": total_box,
            "category_breakdown": category_breakdown,
            "vendor_breakdown": vendor_breakdown,
            "periods": periods
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "total_invoices": 0,
            "total_amount": 0,
            "total_storage_fee": 0,
            "total_courier_fee": 0,
            "total_basic_shipping": 0,
            "total_box_fee": 0,
            "category_breakdown": [],
            "vendor_breakdown": [],
            "periods": []
        }


@router.get("/invoice-items-detail")
async def get_invoice_items_detail(
    period: Optional[str] = None,
    category: Optional[str] = None,
    vendor: Optional[str] = None
):
    """인보이스 항목 상세 조회"""
    try:
        with get_connection() as con:
            # 기본 쿼리
            query = """
                SELECT 
                    ii.item_name,
                    SUM(ii.qty) as total_qty,
                    ii.unit_price,
                    SUM(ii.amount) as total_amount,
                    COUNT(DISTINCT ii.invoice_id) as invoice_count,
                    v.name as vendor_name,
                    i.vendor_id
                FROM invoice_items ii
                JOIN invoices i ON ii.invoice_id = i.invoice_id
                LEFT JOIN vendors v ON i.vendor_id = v.vendor
                WHERE 1=1
            """
            params = []
            
            if period and period != "전체":
                query += " AND strftime('%Y-%m', i.period_from) = ?"
                params.append(period)
            
            if vendor and vendor != "전체":
                query += " AND i.vendor_id = ?"
                params.append(vendor)
            
            query += " GROUP BY ii.item_name, ii.unit_price, i.vendor_id"
            query += " ORDER BY total_amount DESC"
            
            df = pd.read_sql(query, con, params=params)
        
        if df.empty:
            return []
        
        # 카테고리 필터
        if category and category != "전체":
            def categorize_item(name: str) -> str:
                name_lower = name.lower() if name else ""
                if '보관료' in name_lower or '보관' in name_lower:
                    return '보관료'
                elif '택배' in name_lower:
                    return '택배요금'
                elif '기본' in name_lower and ('출고' in name_lower or '출고비' in name_lower):
                    return '기본출고비'
                elif '박스' in name_lower or '봉투' in name_lower:
                    return '박스/봉투'
                else:
                    return '기타'
            
            df['category'] = df['item_name'].apply(categorize_item)
            df = df[df['category'] == category]
        
        result = []
        for _, row in df.iterrows():
            result.append({
                "item_name": row['item_name'],
                "vendor": row['vendor_id'],
                "vendor_name": row['vendor_name'] or row['vendor_id'],
                "total_qty": int(row['total_qty']),
                "unit_price": int(row['unit_price']),
                "total_amount": int(row['total_amount']),
                "invoice_count": int(row['invoice_count'])
            })
        
        return result
    
    except Exception as e:
        return {"error": str(e)}
