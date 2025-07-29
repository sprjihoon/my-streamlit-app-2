# pages/invoice_list.py – 인보이스 관리 페이지 (LEFT JOIN + 전체 기능 완결)
# -----------------------------------------------------------
# * LEFT JOIN 으로 누락 인보이스까지 표시
# * 필터·삭제·상세 수정·개별/전체 XLSX 다운로드 모두 지원
# * Pylance 오류·미완성 부분 제거 → 완전 실행 가능

import sqlite3
import io
import re
import struct
from typing import Any, List

import pandas as pd
import streamlit as st

# ──────────────────────────────────────
# 0. 페이지 설정
# ──────────────────────────────────────
st.set_page_config(page_title="Invoice List", layout="wide")
st.title("📜 Invoice List")
DB_PATH = "billing.db"

# ──────────────────────────────────────
# 1. BLOB → 안전한 파이썬 값 변환
# ──────────────────────────────────────
_digit_re = re.compile(rb"^[0-9]+(\.[0-9]+)?$")

def _bytes_to_val(x: Any):
    if not isinstance(x, (bytes, bytearray, memoryview)):
        return x
    b = bytes(x)
    if _digit_re.match(b):
        s = b.decode("ascii")
        return int(s) if "." not in s else float(s)
    if len(b) <= 8:
        n = int.from_bytes(b, "little", signed=False)
        if n or b.rstrip(b"\x00") == b"\x00":
            return n
    if len(b) == 8:
        try:
            f = struct.unpack("<d", b)[0]
            if 1e-6 <= abs(f) < 1e12:
                return f
        except struct.error:
            pass
    for enc in ("utf-8", "euc-kr", "latin1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return None

def _post_numeric(df: pd.DataFrame) -> pd.DataFrame:
    num_cols = {"수량", "단가", "금액", "total_amount"}
    for c in num_cols & set(df.columns):
        s = df[c].apply(_bytes_to_val).pipe(pd.to_numeric, errors="coerce").fillna(0)
        df[c] = s.astype("Int64") if (s % 1 == 0).all() else s.astype("float64")
    return df

# ──────────────────────────────────────
# 2. 인보이스 목록 로드 (캐시)
# ──────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=60)
def load_invoices() -> pd.DataFrame:
    sql = """
        SELECT i.invoice_id,
               v.vendor AS 업체,
               i.vendor_id,
               i.period_from,
               i.period_to,
               i.created_at,
               IFNULL(i.status,'미확정') AS status,
               i.total_amount
          FROM invoices i
     LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
         ORDER BY i.invoice_id DESC
    """
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql(sql, con)

# ──────────────────────────────────────
# 3. 강제 새로고침
# ──────────────────────────────────────
if st.button("🔄 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()

# ──────────────────────────────────────
# 4. DataFrame 준비 + 필터
# ──────────────────────────────────────

df = load_invoices().applymap(_bytes_to_val).pipe(_post_numeric)
if df.empty:
    st.info("인보이스가 없습니다.")
    st.stop()

df['period_from'] = pd.to_datetime(df['period_from']).dt.date

# 기간(년‑월) 필터
ym_opts = sorted(pd.to_datetime(df['period_from']).dt.strftime('%Y-%m').unique())
ym_opts.insert(0, '전체')  # '전체' 옵션 추가
def_ym = ym_opts[-1] if '전체' not in ym_opts[-1] else ym_opts[1]
sel_ym = st.selectbox("기간 (YYYY-MM)", ym_opts, index=ym_opts.index(def_ym))
# '전체' 선택 시 모든 행 포함
if sel_ym == '전체':
    mask = pd.Series(True, index=df.index)
else:
    mask = df['period_from'].apply(lambda d: d.strftime('%Y-%m')) == sel_ym

# 업체·상태 필터
col1, col2 = st.columns(2)
ven_sel = col1.multiselect("업체", sorted(df['업체'].dropna().unique()))
sta_sel = col2.multiselect("상태", sorted(df['status'].unique()))
if ven_sel:
    mask &= df['업체'].isin(ven_sel)
if sta_sel:
    mask &= df['status'].isin(sta_sel)

# ──────────────────────────────────────
# 4-bis. 목록 표시 + 선택(내장) + 전체 선택 체크박스
# ──────────────────────────────────────
st.markdown("---")
col_del1, col_del2 = st.columns(2)

# 보기용 DataFrame (편집 불필요→dataframe 사용)
view_df = df.loc[mask].set_index('invoice_id').copy()

st.markdown(f"📋 {len(view_df)}건 / 기간 {sel_ym} / 총 합계 ₩{int(view_df['total_amount'].sum()):,}")

# Streamlit 1.35+ built-in row selection
event = st.dataframe(
    view_df,
    use_container_width=True,
    hide_index=False,
    on_select="rerun",
    selection_mode="multi-row",
    key="inv_table"
)

# 선택된 인보이스 ID 추출 (positional index → actual invoice_id)
try:
    selected_pos = event.selection.rows  # type: ignore[attr-defined]
except AttributeError:
    selected_pos = []

selected_ids: List[int] = [view_df.index[i] for i in selected_pos]

with col_del1:
    if st.button("🗑️ 선택 항목 삭제", disabled=not selected_ids, use_container_width=True):
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            for iid in selected_ids:
                cur.execute("DELETE FROM invoice_items WHERE invoice_id=?", (iid,))
                cur.execute("DELETE FROM invoices WHERE invoice_id=?", (iid,))
            con.commit()
        st.cache_data.clear()
        st.success(f"🗑️ 선택된 {len(selected_ids)}건 삭제 완료")
        st.rerun()

with col_del2:
    if st.button("🗑️ 필터된 전체 삭제", disabled=view_df.empty, type="primary", use_container_width=True):
        st.session_state["confirm_delete_all"] = True

if st.session_state.get("confirm_delete_all"):
    st.warning(f"**경고**: 현재 필터링된 **{len(view_df)}** 건의 인보이스를 정말로 모두 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
    c1, c2 = st.columns(2)
    if c1.button("예, 전체 삭제를 실행합니다", type="primary"):
        all_filtered_ids = view_df.index.tolist()
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            for iid in all_filtered_ids:
                cur.execute("DELETE FROM invoice_items WHERE invoice_id=?", (iid,))
                cur.execute("DELETE FROM invoices WHERE invoice_id=?", (iid,))
            con.commit()
        
        st.cache_data.clear()
        del st.session_state["confirm_delete_all"]
        st.success(f"🗑️ 필터링된 {len(all_filtered_ids)}건 전체 삭제 완료")
        st.rerun()

    if c2.button("아니요, 취소합니다"):
        del st.session_state["confirm_delete_all"]
        st.rerun()

st.markdown("---")

# ──────────────────────────────────────
# 6. 상세 보기 / 수정 / 확정 / 개별 XLSX
# ──────────────────────────────────────
if not view_df.empty:
    inv_sel = st.selectbox("🔍 상세 조회할 Invoice", view_df.index, format_func=lambda x: f"#{x}")
    if st.button("🔎 상세 보기"):
        with sqlite3.connect(DB_PATH) as con:
            det = pd.read_sql("SELECT item_id, invoice_id, item_name, qty, unit_price, amount, remark FROM invoice_items WHERE invoice_id=?", con, params=(inv_sel,))
        det = det.applymap(_bytes_to_val).pipe(_post_numeric)
        if det.empty:
            st.warning("항목이 없습니다.")
        else:
            st.subheader(f"Invoice #{inv_sel} 상세")
            edt = st.data_editor(det, num_rows='dynamic', hide_index=True, key='detail_edit')
            if st.button("💾 수정 사항 저장"):
                with sqlite3.connect(DB_PATH) as con:
                    cur = con.cursor()
                    cur.execute("DELETE FROM invoice_items WHERE invoice_id=?", (inv_sel,))
                    cur.executemany(
                        "INSERT INTO invoice_items (invoice_id,item_name,qty,unit_price,amount,remark) VALUES (?,?,?,?,?,?)",
                        [(inv_sel, r['item_name'], r['qty'], r['unit_price'], r['amount'], r.get('remark','')) for _, r in edt.iterrows()]
                    )
                    con.commit()
                st.success("✅ 저장 완료")
            if st.button("✅ 인보이스 확정"):
                with sqlite3.connect(DB_PATH) as con:
                    con.execute("UPDATE invoices SET status='확정' WHERE invoice_id=?", (inv_sel,))
                    con.commit()
                st.success("✅ 확정 완료")

            ven_name = view_df.loc[inv_sel, '업체'] or 'Unknown'
            ym_tag = pd.to_datetime(view_df.loc[inv_sel, 'period_from']).strftime('%Y-%m')
            def _to_xlsx(df_x):
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
                    df_x.to_excel(w, index=False, sheet_name=ven_name[:31])
                return buf.getvalue()
            st.download_button("📥 이 인보이스 XLSX", data=_to_xlsx(edt), file_name=f"{ven_name}_{ym_tag}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ──────────────────────────────────────
# 7. 필터링된 전체 인보이스 XLSX 다운로드
# ──────────────────────────────────────

def export_all_invoices() -> bytes:
    ids = view_df.index.tolist()
    if not ids:
        return b""
    marks = ','.join(['?'] * len(ids))
    with sqlite3.connect(DB_PATH) as con:
        inv = pd.read_sql(
            f"SELECT i.invoice_id, v.vendor AS vendor_name, i.period_from "
            f"FROM invoices i LEFT JOIN vendors v ON i.vendor_id=v.vendor_id "
            f"WHERE i.invoice_id IN ({marks})",
            con, params=ids
        )
        items = pd.read_sql(
            f"SELECT * FROM invoice_items WHERE invoice_id IN ({marks})",
            con, params=ids
        )

    # 컬럼 순서 정리
    col_order = ['item_id', 'invoice_id', 'item_name', 'qty', 'unit_price', 'amount', 'remark']
    items = items.reindex(columns=col_order)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wrt:
        inv[['invoice_id', 'vendor_name', 'period_from']].to_excel(wrt, sheet_name='Invoice_List', index=False)
        for iid, grp in items.groupby('invoice_id', sort=False):
            vendor_nm = inv.loc[inv['invoice_id'] == iid, 'vendor_name'].iloc[0] or 'Unknown'
            sheet = f"{vendor_nm}_{iid}"[:31]
            grp.to_excel(wrt, sheet_name=sheet, index=False)
    return buf.getvalue()

# 다운로드 버튼
st.download_button(
    "📥 전체 인보이스 XLSX (필터 적용)",
    data=export_all_invoices(),
    file_name=f"filtered_invoices_{sel_ym if sel_ym!='전체' else 'all'}.xlsx",
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)
