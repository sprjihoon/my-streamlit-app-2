"""
pages/shipping_insight.py - 전체 데이터 인사이트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 가장 많이 팔린 상품 TOP 20
• 가장 많은 출고가 된 상품 TOP 20
• 가장 많이 출고된 거래처 TOP 20
• 매출이 가장 높은 거래처 TOP 20
"""
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

st.set_page_config(page_title="📊 데이터 인사이트", layout="wide")
st.title("📊 전체 데이터 인사이트")

# ─────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────
@st.cache_data(ttl=60)
def load_shipping_data():
    with sqlite3.connect("billing.db") as con:
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
        
        # 날짜 컬럼 찾기 및 변환
        date_cols = ["배송일", "송장등록일", "출고일자", "기록일자"]
        date_col = next((c for c in date_cols if c in df.columns), None)
        
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df['년월'] = df[date_col].dt.strftime('%Y-%m')
        
        return df

df = load_shipping_data()

if df.empty:
    st.info("배송 통계 데이터가 없습니다.")
    st.stop()

# 컬럼 자동 감지
col_vendor = next((c for c in ["공급처", "업체", "vendor"] if c in df.columns), None)
col_item = next((c for c in ["상품명", "어드민상품명", "상품", "item"] if c in df.columns), None)
col_qty = next((c for c in ["수량", "qty", "Qty"] if c in df.columns), None)
col_amount = next((c for c in ["정산예정금액", "총금액", "금액", "amount"] if c in df.columns), None)

if not all([col_vendor, col_item, col_qty]):
    st.error(f"필수 컬럼 누락: 공급처({col_vendor}), 상품명({col_item}), 수량({col_qty})")
    st.stop()

# ─────────────────────────────────────
# 전역 기간 필터 (모든 탭에 적용)
# ─────────────────────────────────────
selected_period_global = "전체"
invoice_period_global = "전체"

if '년월' in df.columns:
    all_months = sorted(df['년월'].dropna().unique(), reverse=True)
    if all_months:
        st.markdown("### 📅 기간 필터 (전체 탭 적용)")
        col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
        
        with col_f1:
            selected_period_global = st.selectbox("출고 데이터 기간", ["전체"] + all_months, index=0, key="global_period")
        
        with col_f2:
            # 인보이스 기간 필터 (우리 매출용)
            invoice_months = ["전체"] + all_months
            invoice_period_global = st.selectbox("인보이스 기간", invoice_months, index=0, key="global_inv_period")
        
        with col_f3:
            # 적용 정보 표시
            df_display = df.copy()
            if selected_period_global != "전체":
                df_display = df_display[df_display['년월'] == selected_period_global]
            
            st.info(f"📊 출고: {len(df_display):,}건 | 인보이스: {invoice_period_global}")
        
        # 출고 데이터 필터 적용
        if selected_period_global != "전체":
            df = df[df['년월'] == selected_period_global]

st.markdown("---")

# ─────────────────────────────────────
# 핵심 지표 (KPI)
# ─────────────────────────────────────
st.subheader("📈 핵심 지표")

col1, col2, col3, col4 = st.columns(4)

with col1:
    total_orders = len(df)
    st.metric("총 주문 건수", f"{total_orders:,}건")

with col2:
    total_qty = int(df[col_qty].sum())
    st.metric("총 출고 수량", f"{total_qty:,}개")

with col3:
    total_vendors = df[col_vendor].nunique()
    st.metric("거래처 수", f"{total_vendors}개")

with col4:
    if col_amount and col_amount in df.columns:
        total_amount = int(df[col_amount].sum())
        st.metric("총 정산액", f"₩{total_amount:,}")
    else:
        avg_qty = total_qty / total_orders if total_orders > 0 else 0
        st.metric("평균 수량/건", f"{avg_qty:.1f}개")

st.markdown("---")

# ─────────────────────────────────────
# TOP 순위 (탭 구성)
# ─────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🏆 인기 상품", 
    "📦 거래처별 출고량", 
    "💰 거래처별 매출", 
    "💎 우리 매출 분석",
    "📈 월별 트렌드",
    "🎯 거래처 분석",
    "🔍 상세 검색"
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭1: 가장 많이 팔린 상품
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.subheader("🏆 가장 많이 팔린 상품 TOP 20")
    
    top_products = (df.groupby(col_item)[col_qty]
                    .sum()
                    .reset_index()
                    .sort_values(col_qty, ascending=False)
                    .head(20))
    top_products.columns = ['상품명', '총판매수량']
    top_products['순위'] = range(1, len(top_products) + 1)
    
    col_chart, col_table = st.columns([2, 1])
    
    with col_chart:
        st.bar_chart(top_products.set_index('상품명')['총판매수량'], height=400)
    
    with col_table:
        st.dataframe(
            top_products[['순위', '상품명', '총판매수량']],
            width='stretch',
            height=400,
            hide_index=True
        )
    
    st.download_button(
        "📥 CSV 다운로드",
        top_products.to_csv(index=False, encoding='utf-8-sig'),
        f"인기상품_TOP20_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv",
        use_container_width=True
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭2: 가장 많이 출고된 거래처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.subheader("📦 가장 많이 출고된 거래처 TOP 20")
    
    vendor_stats = (df.groupby(col_vendor)
                    .agg({col_qty: ['sum', 'count']})
                    .reset_index())
    vendor_stats.columns = ['거래처', '총출고수량', '주문건수']
    vendor_stats = vendor_stats.sort_values('총출고수량', ascending=False).head(20)
    vendor_stats['순위'] = range(1, len(vendor_stats) + 1)
    vendor_stats['평균수량/건'] = (vendor_stats['총출고수량'] / vendor_stats['주문건수']).round(1)
    
    col_chart, col_table = st.columns([2, 1])
    
    with col_chart:
        st.bar_chart(vendor_stats.set_index('거래처')['총출고수량'], height=400)
    
    with col_table:
        st.dataframe(
            vendor_stats[['순위', '거래처', '총출고수량', '주문건수', '평균수량/건']],
            width='stretch',
            height=400,
            hide_index=True
        )
    
    st.download_button(
        "📥 CSV 다운로드",
        vendor_stats.to_csv(index=False, encoding='utf-8-sig'),
        f"거래처별출고_TOP20_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv",
        use_container_width=True
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭3: 매출이 가장 높은 거래처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.subheader("💰 매출이 가장 높은 거래처 TOP 20")
    
    if col_amount and col_amount in df.columns:
        # 숫자 변환
        df_revenue = df.copy()
        df_revenue[col_amount] = pd.to_numeric(df_revenue[col_amount], errors='coerce').fillna(0)
        
        revenue_stats = (df_revenue.groupby(col_vendor)
                        .agg({col_amount: ['sum', 'count']})
                        .reset_index())
        revenue_stats.columns = ['거래처', '총매출', '주문건수']
        revenue_stats = revenue_stats.sort_values('총매출', ascending=False).head(20)
        revenue_stats['순위'] = range(1, len(revenue_stats) + 1)
        revenue_stats['객단가'] = (revenue_stats['총매출'] / revenue_stats['주문건수']).round(0)
        
        # 표시용 컬럼 추가
        revenue_stats['총매출_표시'] = revenue_stats['총매출'].apply(lambda x: f"₩{int(x):,}")
        revenue_stats['객단가_표시'] = revenue_stats['객단가'].apply(lambda x: f"₩{int(x):,}")
        
        col_chart, col_table = st.columns([2, 1])
        
        with col_chart:
            st.markdown("##### 총매출 TOP 20")
            st.bar_chart(revenue_stats.set_index('거래처')['총매출'], height=300)
            
            st.markdown("##### 평균 객단가 TOP 20")
            top_avg = revenue_stats.sort_values('객단가', ascending=False).head(20)
            st.bar_chart(top_avg.set_index('거래처')['객단가'], height=300)
        
        with col_table:
            st.markdown("##### 📊 상세 데이터")
            st.dataframe(
                revenue_stats[['순위', '거래처', '총매출_표시', '주문건수', '객단가_표시']].rename(columns={
                    '총매출_표시': '총매출',
                    '객단가_표시': '평균 객단가'
                }),
                width='stretch',
                height=620,
                hide_index=True
            )
        
        st.download_button(
            "📥 CSV 다운로드",
            revenue_stats[['순위', '거래처', '총매출', '주문건수', '객단가']].to_csv(index=False, encoding='utf-8-sig'),
            f"거래처별매출_TOP20_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv",
            use_container_width=True
        )
        
        # 전체 평균과 비교
        st.markdown("---")
        st.markdown("#### 📊 전체 평균과 비교")
        
        total_revenue = df_revenue[col_amount].sum()
        total_orders = len(df_revenue)
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        col_avg1, col_avg2, col_avg3 = st.columns(3)
        
        with col_avg1:
            st.metric("전체 평균 객단가", f"₩{int(avg_order_value):,}")
        
        with col_avg2:
            max_avg = revenue_stats['객단가'].max()
            st.metric("최고 객단가", f"₩{int(max_avg):,}", 
                     delta=f"+{int(max_avg - avg_order_value):,}")
        
        with col_avg3:
            min_avg = revenue_stats['객단가'].min()
            st.metric("최저 객단가", f"₩{int(min_avg):,}", 
                     delta=f"{int(min_avg - avg_order_value):,}")
    else:
        st.warning("⚠️ 매출 정보 컬럼(정산예정금액/총금액)이 없습니다.")
        st.info("배송통계 테이블에 금액 컬럼을 추가하면 매출 순위를 확인할 수 있습니다.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭4: 우리 매출 분석 (인보이스 기반)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    st.subheader("💎 우리 매출 분석 (인보이스 기반)")
    st.caption("📌 실제 청구된 인보이스 데이터를 기반으로 한 순수 우리 매출")
    
    try:
        with sqlite3.connect("billing.db") as con:
            # 각 인보이스별로 객단가 계산 후 거래처별 집계
            # 1단계: 인보이스별 기본출고비 건수 추출
            
            # 전역 날짜 필터 사용
            date_filter = ""
            if invoice_period_global != "전체":
                date_filter = f"AND strftime('%Y-%m', i.period_from) = '{invoice_period_global}'"
            
            df_invoice_detail = pd.read_sql(f"""
                SELECT 
                    i.invoice_id,
                    v.vendor as 거래처,
                    v.name as 거래처명,
                    v.active as 활성상태,
                    i.total_amount as 청구금액,
                    COALESCE(
                        (SELECT SUM(qty) 
                         FROM invoice_items 
                         WHERE invoice_id = i.invoice_id 
                           AND (item_name LIKE '%기본%출고%' OR item_name = '기본 출고비')
                        ), 0
                    ) as 기본출고비건수,
                    i.period_from,
                    i.period_to
                FROM invoices i
                JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE i.status != 'cancelled'
                  AND (v.active IS NULL OR v.active = 'YES')
                {date_filter}
            """, con)
            
            # 2단계: 각 인보이스별 객단가 계산
            df_invoice_detail['객단가'] = df_invoice_detail.apply(
                lambda row: row['청구금액'] / row['기본출고비건수'] if row['기본출고비건수'] > 0 else 0,
                axis=1
            )
            
            # 3단계: 거래처별 집계
            df_our_revenue = df_invoice_detail.groupby(['거래처', '거래처명']).agg({
                'invoice_id': 'count',
                '청구금액': 'sum',
                '기본출고비건수': 'sum',
                '객단가': 'mean',  # 인보이스별 객단가의 평균
                'period_from': 'min',
                'period_to': 'max'
            }).reset_index()
            
            df_our_revenue.columns = ['거래처', '거래처명', '인보이스수', '총매출', '총주문건수', '평균객단가', '최초거래일', '최근거래일']
            df_our_revenue = df_our_revenue.sort_values('총매출', ascending=False)
            
            # 최소/최대 금액 추가
            min_max = df_invoice_detail.groupby('거래처')['청구금액'].agg(['min', 'max']).reset_index()
            min_max.columns = ['거래처', '최소금액', '최대금액']
            df_our_revenue = df_our_revenue.merge(min_max, on='거래처', how='left')
            
            # 객단가를 정수로 변환
            df_our_revenue['평균객단가'] = df_our_revenue['평균객단가'].round(0)
        
        if df_our_revenue.empty:
            st.info("생성된 인보이스가 없습니다. 인보이스를 먼저 생성해주세요.")
        else:
            # 순위 추가
            df_our_revenue['순위'] = range(1, len(df_our_revenue) + 1)
            
            # 탭 내부 서브탭
            subtab1, subtab2, subtab3 = st.tabs(["💰 총매출 순위", "💎 객단가 순위", "📊 종합 분석"])
            
            # 서브탭1: 총매출 순위
            with subtab1:
                st.markdown("#### 💰 총매출 TOP 20")
                
                top_revenue = df_our_revenue.head(20).copy()
                top_revenue['총매출_표시'] = top_revenue['총매출'].apply(lambda x: f"₩{int(x):,}")
                top_revenue['객단가_표시'] = top_revenue['평균객단가'].apply(lambda x: f"₩{int(x):,}")
                
                col_c1, col_c2 = st.columns([2, 1])
                
                with col_c1:
                    st.bar_chart(top_revenue.set_index('거래처')['총매출'], height=400)
                
                with col_c2:
                    st.dataframe(
                        top_revenue[['순위', '거래처', '총주문건수', '총매출_표시', '객단가_표시']].rename(columns={
                            '총매출_표시': '총매출',
                            '객단가_표시': '평균객단가'
                        }),
                        width='stretch',
                        height=400,
                        hide_index=True
                    )
                    
                    st.caption("💡 객단가 = 인보이스 청구금액 / 기본출고비 건수")
            
            # 서브탭2: 객단가 순위
            with subtab2:
                st.markdown("#### 💎 객단가 TOP 20 (주문당)")
                st.caption("📌 객단가 = 인보이스 청구금액 / 기본출고비 건수")
                
                top_avg_order = df_our_revenue.sort_values('평균객단가', ascending=False).head(20).copy()
                top_avg_order['순위'] = range(1, len(top_avg_order) + 1)
                top_avg_order['총매출_표시'] = top_avg_order['총매출'].apply(lambda x: f"₩{int(x):,}")
                top_avg_order['객단가_표시'] = top_avg_order['평균객단가'].apply(lambda x: f"₩{int(x):,}")
                
                col_c1, col_c2 = st.columns([2, 1])
                
                with col_c1:
                    st.bar_chart(top_avg_order.set_index('거래처')['평균객단가'], height=400)
                
                with col_c2:
                    st.dataframe(
                        top_avg_order[['순위', '거래처', '총주문건수', '객단가_표시', '총매출_표시']].rename(columns={
                            '객단가_표시': '평균객단가',
                            '총매출_표시': '총매출'
                        }),
                        width='stretch',
                        height=400,
                        hide_index=True
                    )
                    
                    st.caption("💡 각 인보이스별 객단가의 평균")
            
            # 서브탭3: 종합 분석
            with subtab3:
                st.markdown("#### 📊 우리 매출 종합 분석")
                
                # 전체 통계
                total_invoices = df_our_revenue['인보이스수'].sum()
                total_our_revenue = df_our_revenue['총매출'].sum()
                total_base_orders = df_our_revenue['총주문건수'].sum()
                avg_order_value = total_our_revenue / total_base_orders if total_base_orders > 0 else 0
                
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                
                with col_s1:
                    st.metric("총 인보이스", f"{int(total_invoices):,}건")
                with col_s2:
                    st.metric("총 매출 (우리)", f"₩{int(total_our_revenue):,}")
                with col_s3:
                    st.metric("총 주문 건수", f"{int(total_base_orders):,}건", help="기본포장비 건수")
                with col_s4:
                    st.metric("전체 평균 객단가", f"₩{int(avg_order_value):,}", help="총매출 / 주문건수")
                
                st.markdown("---")
                
                # 두 개의 분포 분석
                col_dist1, col_dist2 = st.columns(2)
                
                # 객단가 분포
                with col_dist1:
                    st.markdown("##### 💎 객단가별 거래처 분포")
                    
                    # 객단가 구간별 분류
                    bins_avg = [0, 500, 1000, 2000, 3000, 5000, float('inf')]
                    labels_avg = ['~500원', '500~1천', '1천~2천', '2천~3천', '3천~5천', '5천+']
                    
                    df_our_revenue['객단가구간'] = pd.cut(df_our_revenue['평균객단가'], bins=bins_avg, labels=labels_avg)
                    
                    dist_avg_df = df_our_revenue['객단가구간'].value_counts().sort_index().reset_index()
                    dist_avg_df.columns = ['객단가 구간', '거래처 수']
                    
                    st.dataframe(dist_avg_df, width='stretch', hide_index=True)
                    st.bar_chart(dist_avg_df.set_index('객단가 구간')['거래처 수'])
                
                # 총매출(청구금액) 분포
                with col_dist2:
                    st.markdown("##### 💰 총매출(청구금액)별 거래처 분포")
                    
                    # 총매출 구간별 분류
                    bins_revenue = [0, 100000, 500000, 1000000, 3000000, 5000000, 10000000, float('inf')]
                    labels_revenue = ['~10만', '10~50만', '50~100만', '100~300만', '300~500만', '500~1천만', '1천만+']
                    
                    df_our_revenue['총매출구간'] = pd.cut(df_our_revenue['총매출'], bins=bins_revenue, labels=labels_revenue)
                    
                    dist_revenue_df = df_our_revenue['총매출구간'].value_counts().sort_index().reset_index()
                    dist_revenue_df.columns = ['청구금액 구간', '거래처 수']
                    
                    st.dataframe(dist_revenue_df, width='stretch', hide_index=True)
                    st.bar_chart(dist_revenue_df.set_index('청구금액 구간')['거래처 수'])
                    
                    # 구간별 비율
                    total_vendors = len(df_our_revenue)
                    st.caption(f"총 {total_vendors}개 거래처")
                    
                    # TOP 구간 표시
                    if not dist_revenue_df.empty:
                        top_segment = dist_revenue_df.iloc[0]
                        st.caption(f"최다: {top_segment['청구금액 구간']} ({top_segment['거래처 수']}개, {top_segment['거래처 수']/total_vendors*100:.1f}%)")
                
                # 상위/하위 거래처 분석
                st.markdown("---")
                st.markdown("#### 🔝 상위 5개 vs 하위 5개 거래처")
                
                col_top, col_bottom = st.columns(2)
                
                with col_top:
                    st.markdown("##### 📈 상위 5개 거래처 (총매출 기준)")
                    
                    top5 = df_our_revenue.head(5).copy()
                    top5['총매출_fmt'] = top5['총매출'].apply(lambda x: f"₩{int(x):,}")
                    top5['객단가_fmt'] = top5['평균객단가'].apply(lambda x: f"₩{int(x):,}")
                    
                    st.dataframe(
                        top5[['순위', '거래처', '총주문건수', '총매출_fmt', '객단가_fmt']].rename(columns={
                            '총매출_fmt': '총매출',
                            '객단가_fmt': '객단가'
                        }),
                        width='stretch',
                        hide_index=True
                    )
                    
                    # 상위 5개 합계
                    top5_total = top5['총매출'].sum()
                    top5_pct = (top5_total / total_our_revenue * 100) if total_our_revenue > 0 else 0
                    st.metric("상위 5개 매출 비중", f"{top5_pct:.1f}%", delta=f"₩{int(top5_total):,}")
                
                with col_bottom:
                    st.markdown("##### 📉 하위 5개 거래처 (총매출 기준)")
                    
                    bottom5 = df_our_revenue.tail(5).copy()
                    bottom5 = bottom5.sort_values('총매출', ascending=True).reset_index(drop=True)
                    bottom5['순위'] = range(len(df_our_revenue) - 4, len(df_our_revenue) + 1)
                    bottom5['총매출_fmt'] = bottom5['총매출'].apply(lambda x: f"₩{int(x):,}")
                    bottom5['객단가_fmt'] = bottom5['평균객단가'].apply(lambda x: f"₩{int(x):,}")
                    
                    st.dataframe(
                        bottom5[['순위', '거래처', '총주문건수', '총매출_fmt', '객단가_fmt']].rename(columns={
                            '총매출_fmt': '총매출',
                            '객단가_fmt': '객단가'
                        }),
                        width='stretch',
                        hide_index=True
                    )
                    
                    # 하위 5개 합계
                    bottom5_total = bottom5['총매출'].sum()
                    bottom5_pct = (bottom5_total / total_our_revenue * 100) if total_our_revenue > 0 else 0
                    st.metric("하위 5개 매출 비중", f"{bottom5_pct:.1f}%", delta=f"₩{int(bottom5_total):,}")
                
                # 전체 데이터 다운로드
                st.markdown("---")
                st.download_button(
                    "📥 전체 거래처 매출 데이터 다운로드",
                    df_our_revenue[['순위', '거래처', '거래처명', '인보이스수', '총주문건수', '총매출', '평균객단가', '최소금액', '최대금액', '최초거래일', '최근거래일']].to_csv(index=False, encoding='utf-8-sig'),
                    f"우리매출_전체거래처_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv",
                    use_container_width=True
                )
    
    except Exception as e:
        st.error(f"인보이스 데이터 로드 오류: {e}")
        st.info("인보이스를 먼저 생성해주세요.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭5: 월별 트렌드 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.subheader("📈 시간대별 트렌드 분석")
    
    # 적용 중인 필터 표시
    if selected_period_global != "전체":
        st.info(f"📌 현재 필터: {selected_period_global} 출고 데이터만 표시 중")
    
    if '년월' in df.columns:
        # 서브탭: 월별 / 주별 / 요일별 / 일별
        trend_tab1, trend_tab2, trend_tab3, trend_tab4 = st.tabs(["📅 월별", "📆 주별", "🗓️ 요일별", "📆 일별 TOP"])
        
        # ────────────────────────────────────
        # 월별 트렌드
        # ────────────────────────────────────
        with trend_tab1:
            st.markdown("#### 📅 월별 트렌드")
            
            monthly_stats = df.groupby('년월').agg({
                col_qty: 'sum',
                col_vendor: 'count'
            }).reset_index()
            monthly_stats.columns = ['년월', '총출고수량', '주문건수']
            
            if col_amount and col_amount in df.columns:
                df_amt = df.copy()
                df_amt[col_amount] = pd.to_numeric(df_amt[col_amount], errors='coerce').fillna(0)
                monthly_revenue = df_amt.groupby('년월')[col_amount].sum().reset_index()
                monthly_revenue.columns = ['년월', '총매출']
                monthly_stats = monthly_stats.merge(monthly_revenue, on='년월')
            
            monthly_stats = monthly_stats.sort_values('년월')
            
            # 성장률 계산
            monthly_stats['출고_성장률'] = monthly_stats['총출고수량'].pct_change() * 100
            if '총매출' in monthly_stats.columns:
                monthly_stats['매출_성장률'] = monthly_stats['총매출'].pct_change() * 100
            
            col_t1, col_t2 = st.columns([3, 2])
            
            with col_t1:
                st.line_chart(monthly_stats.set_index('년월')[['총출고수량', '주문건수']])
                
                if '총매출' in monthly_stats.columns:
                    st.line_chart(monthly_stats.set_index('년월')['총매출'])
            
            with col_t2:
                st.dataframe(monthly_stats, width='stretch', height=400, hide_index=True)
                
                # 최근 월 vs 이전 월 비교
                if len(monthly_stats) >= 2:
                    latest = monthly_stats.iloc[-1]
                    previous = monthly_stats.iloc[-2]
                    
                    st.markdown("#### 📊 월간 변화")
                    
                    qty_change = latest['총출고수량'] - previous['총출고수량']
                    qty_change_pct = (qty_change / previous['총출고수량'] * 100) if previous['총출고수량'] > 0 else 0
                    
                    st.metric(
                        f"{latest['년월']} 출고량",
                        f"{int(latest['총출고수량']):,}개",
                        delta=f"{qty_change_pct:+.1f}% ({int(qty_change):+,}개)"
                    )
                    
                    if '총매출' in monthly_stats.columns:
                        revenue_change = latest['총매출'] - previous['총매출']
                        revenue_change_pct = (revenue_change / previous['총매출'] * 100) if previous['총매출'] > 0 else 0
                        
                        st.metric(
                            f"{latest['년월']} 매출",
                            f"₩{int(latest['총매출']):,}",
                            delta=f"{revenue_change_pct:+.1f}%"
                        )
        
        # ────────────────────────────────────
        # 주별 트렌드
        # ────────────────────────────────────
        with trend_tab2:
            st.markdown("#### 📆 주별 트렌드")
            
            # 배송일 컬럼에서 주차 추출
            date_col = next((c for c in ["배송일", "송장등록일", "출고일자"] if c in df.columns), None)
            
            if date_col:
                df_week = df.copy()
                df_week[date_col] = pd.to_datetime(df_week[date_col], errors='coerce')
                df_week = df_week.dropna(subset=[date_col])
                
                # 년-주차 생성 (ISO 주차)
                df_week['년주'] = df_week[date_col].dt.strftime('%Y-W%U')
                
                weekly_stats = df_week.groupby('년주').agg({
                    col_qty: 'sum',
                    col_vendor: 'count'
                }).reset_index()
                weekly_stats.columns = ['년주', '총출고수량', '주문건수']
                weekly_stats = weekly_stats.sort_values('년주')
                
                col_w1, col_w2 = st.columns([3, 2])
                
                with col_w1:
                    st.line_chart(weekly_stats.set_index('년주')['총출고수량'])
                    st.caption("주별 출고량 추이")
                
                with col_w2:
                    st.dataframe(weekly_stats.tail(10), width='stretch', height=400, hide_index=True)
                    st.caption("최근 10주")
                    
                    # 주간 평균
                    avg_week_qty = weekly_stats['총출고수량'].mean()
                    avg_week_orders = weekly_stats['주문건수'].mean()
                    
                    st.metric("주간 평균 출고량", f"{int(avg_week_qty):,}개")
                    st.metric("주간 평균 주문", f"{int(avg_week_orders):,}건")
            else:
                st.warning("날짜 컬럼이 없어서 주별 분석을 할 수 없습니다.")
        
        # ────────────────────────────────────
        # 요일별 트렌드
        # ────────────────────────────────────
        with trend_tab3:
            st.markdown("#### 🗓️ 요일별 출고 패턴")
            
            date_col = next((c for c in ["배송일", "송장등록일", "출고일자"] if c in df.columns), None)
            
            if date_col:
                df_dow = df.copy()
                df_dow[date_col] = pd.to_datetime(df_dow[date_col], errors='coerce')
                df_dow = df_dow.dropna(subset=[date_col])
                
                # 요일 추출 (0=월요일, 6=일요일)
                df_dow['요일번호'] = df_dow[date_col].dt.dayofweek
                df_dow['요일명'] = df_dow[date_col].dt.day_name()
                
                # 한글 요일명
                dow_map = {
                    'Monday': '월요일',
                    'Tuesday': '화요일',
                    'Wednesday': '수요일',
                    'Thursday': '목요일',
                    'Friday': '금요일',
                    'Saturday': '토요일',
                    'Sunday': '일요일'
                }
                df_dow['요일'] = df_dow['요일명'].map(dow_map)
                
                # 요일별 집계
                dow_stats = df_dow.groupby(['요일번호', '요일']).agg({
                    col_qty: ['sum', 'count']
                }).reset_index()
                dow_stats.columns = ['요일번호', '요일', '총출고수량', '주문건수']
                dow_stats = dow_stats.sort_values('요일번호')
                dow_stats['비율(%)'] = (dow_stats['총출고수량'] / dow_stats['총출고수량'].sum() * 100).round(1)
                
                col_d1, col_d2 = st.columns([2, 1])
                
                with col_d1:
                    st.markdown("##### 📊 요일별 출고량")
                    st.bar_chart(dow_stats.set_index('요일')['총출고수량'])
                    
                    st.markdown("##### 📊 요일별 주문 건수")
                    st.bar_chart(dow_stats.set_index('요일')['주문건수'])
                
                with col_d2:
                    st.markdown("##### 📋 요일별 통계")
                    
                    st.dataframe(
                        dow_stats[['요일', '주문건수', '총출고수량', '비율(%)']],
                        width='stretch',
                        hide_index=True
                    )
                    
                    # 인사이트
                    st.markdown("##### 💡 인사이트")
                    
                    max_dow = dow_stats.loc[dow_stats['총출고수량'].idxmax()]
                    min_dow = dow_stats.loc[dow_stats['총출고수량'].idxmin()]
                    
                    st.metric("출고 최다 요일", max_dow['요일'], 
                             delta=f"{int(max_dow['총출고수량']):,}개")
                    st.metric("출고 최소 요일", min_dow['요일'], 
                             delta=f"{int(min_dow['총출고수량']):,}개")
                    
                    # 평일 vs 주말
                    weekday = dow_stats[dow_stats['요일번호'] < 5]['총출고수량'].sum()
                    weekend = dow_stats[dow_stats['요일번호'] >= 5]['총출고수량'].sum()
                    
                    st.markdown("##### 📅 평일 vs 주말")
                    st.metric("평일 (월~금)", f"{int(weekday):,}개", 
                             delta=f"{weekday/(weekday+weekend)*100:.1f}%")
                    st.metric("주말 (토~일)", f"{int(weekend):,}개", 
                             delta=f"{weekend/(weekday+weekend)*100:.1f}%")
            else:
                st.warning("날짜 컬럼이 없어서 요일별 분석을 할 수 없습니다.")
        
        # ────────────────────────────────────
        # 일별 TOP (가장 많이 출고된 날)
        # ────────────────────────────────────
        with trend_tab4:
            st.markdown("#### 📆 일별 출고량 분석")
            
            date_col = next((c for c in ["배송일", "송장등록일", "출고일자"] if c in df.columns), None)
            
            if date_col:
                df_daily = df.copy()
                df_daily[date_col] = pd.to_datetime(df_daily[date_col], errors='coerce')
                df_daily = df_daily.dropna(subset=[date_col])
                
                # 날짜만 추출 (시간 제거)
                df_daily['날짜'] = df_daily[date_col].dt.date
                df_daily['요일'] = df_daily[date_col].dt.day_name().map({
                    'Monday': '월', 'Tuesday': '화', 'Wednesday': '수',
                    'Thursday': '목', 'Friday': '금', 'Saturday': '토', 'Sunday': '일'
                })
                
                # 일별 집계
                daily_stats = df_daily.groupby(['날짜', '요일']).agg({
                    col_qty: 'sum',
                    col_vendor: 'count'
                }).reset_index()
                daily_stats.columns = ['날짜', '요일', '총출고수량', '주문건수']
                daily_stats = daily_stats.sort_values('총출고수량', ascending=False)
                
                col_top, col_chart = st.columns([1, 2])
                
                with col_top:
                    st.markdown("##### 🏆 출고량 TOP 10 일자")
                    
                    top10_days = daily_stats.head(10).copy()
                    top10_days['순위'] = range(1, len(top10_days) + 1)
                    
                    st.dataframe(
                        top10_days[['순위', '날짜', '요일', '주문건수', '총출고수량']],
                        width='stretch',
                        hide_index=True
                    )
                    
                    # 최다 출고일 하이라이트
                    top1 = top10_days.iloc[0]
                    st.success(f"🏆 최다: {top1['날짜']} ({top1['요일']}) - {int(top1['총출고수량']):,}개")
                
                with col_chart:
                    st.markdown("##### 📈 일별 출고량 추이")
                    
                    # 최근 30일 차트
                    recent_30 = daily_stats.sort_values('날짜').tail(30)
                    recent_30_chart = recent_30.copy()
                    recent_30_chart['날짜_str'] = recent_30_chart['날짜'].astype(str)
                    
                    st.line_chart(recent_30_chart.set_index('날짜_str')['총출고수량'])
                    st.caption("최근 30일 출고량 추이")
                
                # 통계 요약
                st.markdown("---")
                st.markdown("#### 📊 일별 출고 통계")
                
                col_avg1, col_avg2, col_avg3, col_avg4 = st.columns(4)
                
                with col_avg1:
                    daily_avg = daily_stats['총출고수량'].mean()
                    st.metric("일 평균 출고량", f"{int(daily_avg):,}개")
                
                with col_avg2:
                    daily_median = daily_stats['총출고수량'].median()
                    st.metric("일 중앙값", f"{int(daily_median):,}개")
                
                with col_avg3:
                    daily_max = daily_stats['총출고수량'].max()
                    st.metric("일 최대 출고량", f"{int(daily_max):,}개")
                
                with col_avg4:
                    daily_min = daily_stats['총출고수량'].min()
                    st.metric("일 최소 출고량", f"{int(daily_min):,}개")
                
                # 출고량 구간별 일수
                st.markdown("##### 📊 출고량 구간별 일수")
                
                bins_daily = [0, 100, 300, 500, 1000, 2000, float('inf')]
                labels_daily = ['~100개', '100~300', '300~500', '500~1천', '1천~2천', '2천+']
                
                daily_stats['출고량구간'] = pd.cut(daily_stats['총출고수량'], bins=bins_daily, labels=labels_daily)
                
                segment_counts = daily_stats['출고량구간'].value_counts().sort_index().reset_index()
                segment_counts.columns = ['출고량 구간', '일수']
                
                col_seg1, col_seg2 = st.columns([2, 1])
                
                with col_seg1:
                    st.bar_chart(segment_counts.set_index('출고량 구간')['일수'])
                
                with col_seg2:
                    st.dataframe(segment_counts, width='stretch', hide_index=True)
                    
                    total_days = len(daily_stats)
                    st.caption(f"총 {total_days}일 분석")
            else:
                st.warning("날짜 컬럼이 없어서 일별 분석을 할 수 없습니다.")
    else:
        st.warning("날짜 정보가 없어서 트렌드 분석을 할 수 없습니다.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭6: 거래처 상세 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    st.subheader("🎯 거래처별 상세 분석")
    
    # 거래처별 SKU 다양성
    vendor_sku = (df.groupby(col_vendor)[col_item]
                  .nunique()
                  .reset_index()
                  .sort_values(col_item, ascending=False))
    vendor_sku.columns = ['거래처', '상품종류수']
    
    col_a1, col_a2 = st.columns(2)
    
    with col_a1:
        st.markdown("#### 📦 거래처별 상품 다양성 TOP 10")
        st.dataframe(
            vendor_sku.head(10).reset_index(drop=True),
            width='stretch',
            height=300
        )
        st.caption("상품종류수가 많을수록 다양한 상품 취급")
    
    with col_a2:
        st.markdown("#### 📦 택배 구간별 분포 (부피 기준)")
        
        # kpost_in 테이블에서 부피 데이터 가져오기
        try:
            with sqlite3.connect("billing.db") as con:
                # shipping_zone 구간 정보
                df_zone = pd.read_sql("SELECT 구간, len_min_cm, len_max_cm FROM shipping_zone WHERE 요금제 = 'A' ORDER BY len_min_cm", con)
                
                # kpost_in에서 부피 데이터
                df_volume = pd.read_sql("SELECT 부피 FROM kpost_in WHERE 부피 IS NOT NULL", con)
                
                if not df_volume.empty and not df_zone.empty:
                    df_volume['부피'] = pd.to_numeric(df_volume['부피'], errors='coerce')
                    df_volume = df_volume.dropna()
                    
                    # 구간별 분류
                    size_dist = {}
                    remaining = df_volume.copy()
                    
                    for _, row in df_zone.iterrows():
                        label = row['구간']
                        min_cm = pd.to_numeric(row['len_min_cm'], errors='coerce')
                        max_cm = pd.to_numeric(row['len_max_cm'], errors='coerce')
                        
                        if pd.notna(min_cm) and pd.notna(max_cm):
                            cond = (remaining['부피'] >= min_cm) & (remaining['부피'] <= max_cm)
                            count = int(cond.sum())
                            
                            if count > 0:
                                size_dist[label] = count
                                remaining = remaining[~cond]
                    
                    if size_dist:
                        size_df = pd.DataFrame(list(size_dist.items()), columns=['구간', '건수'])
                        size_df = size_df.sort_values('건수', ascending=False)
                        
                        st.dataframe(size_df, width='stretch', height=250, hide_index=True)
                        st.bar_chart(size_df.set_index('구간')['건수'])
                        
                        # 비율 표시
                        total_size = size_df['건수'].sum()
                        st.caption(f"총 {total_size:,}건 | 극소: {size_dist.get('극소', 0):,}건 ({size_dist.get('극소', 0)/total_size*100:.1f}%)")
                    else:
                        st.info("구간별 데이터 없음")
                else:
                    st.info("kpost_in 테이블에 부피 데이터가 없습니다.")
        except Exception as e:
            st.warning(f"택배 구간 분석 오류: {e}")
    
    # 택배사 분포
    if '택배사' in df.columns:
        st.markdown("#### 🚚 택배사별 배송 현황")
        
        courier_stats = df.groupby('택배사').agg({
            col_qty: 'sum',
            col_vendor: 'count'
        }).reset_index()
        courier_stats.columns = ['택배사', '총수량', '건수']
        courier_stats = courier_stats.sort_values('건수', ascending=False)
        
        if '택배요금' in df.columns or '택배비' in df.columns:
            fee_col = '택배요금' if '택배요금' in df.columns else '택배비'
            
            # 숫자 변환
            df_fee = df.copy()
            df_fee[fee_col] = pd.to_numeric(df_fee[fee_col], errors='coerce').fillna(0)
            
            courier_fee = df_fee.groupby('택배사')[fee_col].sum().reset_index()
            courier_fee.columns = ['택배사', '총택배비']
            courier_stats = courier_stats.merge(courier_fee, on='택배사', how='left')
            courier_stats['평균택배비'] = (courier_stats['총택배비'] / courier_stats['건수']).round(0)
        
        col_c1, col_c2 = st.columns([2, 1])
        
        with col_c1:
            st.bar_chart(courier_stats.set_index('택배사')['건수'])
        
        with col_c2:
            st.dataframe(courier_stats, width='stretch', height=300, hide_index=True)
    
    # 합포장 분석
    if '내품수량' in df.columns:
        st.markdown("#### 📦 합포장 분석")
        
        df['내품수량_num'] = pd.to_numeric(df['내품수량'], errors='coerce').fillna(1)
        
        single = len(df[df['내품수량_num'] == 1])
        multi = len(df[df['내품수량_num'] > 1])
        total = len(df)
        
        col_m1, col_m2, col_m3 = st.columns(3)
        
        with col_m1:
            st.metric("단일 상품", f"{single:,}건", delta=f"{single/total*100:.1f}%")
        with col_m2:
            st.metric("합포장 (2개 이상)", f"{multi:,}건", delta=f"{multi/total*100:.1f}%")
        with col_m3:
            avg_items = df['내품수량_num'].mean()
            st.metric("평균 내품수량", f"{avg_items:.1f}개")
        
        # 거래처별 합포장 비율
        vendor_multi = (df.groupby(col_vendor)
                       .apply(lambda x: (x['내품수량_num'] > 1).sum() / len(x) * 100)
                       .reset_index()
                       .sort_values(0, ascending=False)
                       .head(10))
        vendor_multi.columns = ['거래처', '합포장비율(%)']
        
        st.markdown("##### 거래처별 합포장 비율 TOP 10")
        st.dataframe(vendor_multi, width='stretch', hide_index=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭7: 상세 검색
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab7:
    st.subheader("🔍 상세 검색 및 필터")
    
    col_s1, col_s2 = st.columns([1, 3])
    
    with col_s1:
        sel_vendor_detail = st.selectbox("🏢 거래처", ["전체"] + sorted(df[col_vendor].unique().tolist()))
    
    with col_s2:
        keyword = st.text_input("🔍 상품명 키워드", placeholder="예: 케이스, 액세서리...")
    
    # 필터 적용
    df_filtered = df.copy()
    
    if sel_vendor_detail != "전체":
        df_filtered = df_filtered[df_filtered[col_vendor] == sel_vendor_detail]
    
    if keyword:
        df_filtered = df_filtered[df_filtered[col_item].str.contains(keyword, case=False, na=False)]
    
    # 결과 통계
    st.markdown("#### 📊 필터 결과")
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    
    with col_r1:
        st.metric("검색 건수", f"{len(df_filtered):,}건")
    with col_r2:
        st.metric("총 수량", f"{int(df_filtered[col_qty].sum()):,}개")
    with col_r3:
        if col_amount and col_amount in df_filtered.columns:
            st.metric("총 금액", f"₩{int(df_filtered[col_amount].sum()):,}")
    with col_r4:
        if len(df_filtered) > 0:
            avg_qty = df_filtered[col_qty].sum() / len(df_filtered)
            st.metric("평균 수량/건", f"{avg_qty:.1f}개")
    
    # 결과 테이블
    if len(df_filtered) > 0:
        st.markdown("#### 📋 검색 결과 (최근 100건)")
        
        # 주요 컬럼만 표시
        display_cols = [col_vendor, col_item, col_qty]
        if col_amount and col_amount in df_filtered.columns:
            display_cols.append(col_amount)
        
        st.dataframe(
            df_filtered[display_cols].head(100),
            width='stretch',
            height=400
        )
        
        col_dl1, col_dl2 = st.columns([1, 3])
        with col_dl1:
            st.download_button(
                "📥 검색결과 전체 다운로드",
                df_filtered.to_csv(index=False, encoding='utf-8-sig'),
                f"검색결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv",
                use_container_width=True
            )
    else:
        st.info("검색 결과가 없습니다.")
