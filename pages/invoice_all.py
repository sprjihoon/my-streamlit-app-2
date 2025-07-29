"""pages/청구서_일괄_생성.py – 전체 공급처 인보이스 일괄 계산 (안정화+버그패치 v2)
────────────────────────────────────────────
• 기간‑선택 → 전체/선택 공급처 인보이스 자동 계산·확정
• 진행 바 + 공급처별 처리 시간·결과 로그 (성공/실패) 표시
• 출고 데이터 없는 공급처도 기본·기타 비용 계산 후 인보이스 생성
• DB 경로 불일치, 캐시 미무효화, 미‑commit 등 자주‑발생 버그 패치
• NEW: "수취인명" 컬럼 누락 시도 graceful‑skip (add_return_pickup_fee)
"""
import sys
import os

# --- 프로젝트 루트를 sys.path에 추가 ---
# Streamlit Cloud 등에서 'pages' 폴더 내 스크립트 실행 시 모듈을 찾지 못하는 문제 해결
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# ------------------------------------

from __future__ import annotations
import time
from datetime import date, datetime
from typing import List, Tuple

import pandas as pd
import streamlit as st
import sqlite3

from actions.invoice_actions import (
    add_basic_shipping, add_courier_fee_by_zone, add_box_fee_by_zone,
    add_barcode_fee, add_void_fee, add_ppbag_fee, add_video_out_fee,
    add_return_pickup_fee, add_return_courier_fee, add_video_ret_fee,
    add_worklog_items, create_and_finalize_invoice
)
from core.utils_shipping import shipping_stats
from utils.utils_combined import add_combined_pack_fee
from utils.utils_inbound import add_inbound_inspection_fee
from utils.utils_remote import add_remote_area_fee
from common import get_connection

# ─────────────────────────────────────
# 0. 페이지 설정
# ─────────────────────────────────────
st.set_page_config(page_title="📊 인보이스 일괄 계산기", layout="wide")
st.title("📊 전체 공급처 인보이스 자동 계산")

col1, col2 = st.columns(2)
with col1:
    date_from: date = st.date_input("📅 시작일", value=datetime.today().replace(day=1))
with col2:
    date_to: date = st.date_input("📅 종료일", value=datetime.today())

# ─────────────────────────────────────
# 1. 공급처 로드
# ─────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_vendors() -> pd.DataFrame:
    with get_connection() as con:
        return pd.read_sql("SELECT vendor_id, vendor FROM vendors ORDER BY vendor", con)

df_vendors = load_vendors()
vendor_id_map = dict(zip(df_vendors.vendor, df_vendors.vendor_id))
all_vendors: List[str] = df_vendors.vendor.tolist()

selected_vendors = st.multiselect("✅ 계산할 공급처 (비우면 전체)", all_vendors, default=all_vendors)

# ─────────────────────────────────────
# 2. 인보이스 일괄 계산·확정
# ─────────────────────────────────────
if st.button("🚀 인보이스 일괄 생성 시작", type="primary"):

    total_cnt = len(selected_vendors)
    if total_cnt == 0:
        st.warning("⚠️ 선택된 공급처가 없습니다.")
        st.stop()

    progress = st.progress(0.0, text="대기 중…")
    log: List[Tuple[str, str]] = []

    for idx, vendor in enumerate(selected_vendors, start=1):
        step_start = time.time()
        progress.progress((idx - 1) / total_cnt, text=f"🔄 {vendor} 처리 중 … ({idx}/{total_cnt})")
        try:
            st.session_state["items"] = []

            # 1) 출고 통계
            df_ship = shipping_stats(vendor, str(date_from), str(date_to))
            if df_ship.empty:
                st.info(f"{vendor}: 출고 데이터 없음 – 기본/기타 비용만 계산")

            # NEW ⚙️  중복 출고 행 제거
            for key_col in ("송장번호", "운송장번호", "TrackingNo", "tracking_no"):
                if key_col in df_ship.columns:
                    df_ship = df_ship.drop_duplicates(subset=[key_col])
                    break

            # 2) 기본 출고비
            df_basic = add_basic_shipping(pd.DataFrame(), vendor, date_from, date_to)
            st.session_state["items"].extend(df_basic.to_dict("records"))

            # 3) 기타 비용
            zone_cnt = add_courier_fee_by_zone(vendor, str(date_from), str(date_to))
            add_box_fee_by_zone(st.session_state["items"], vendor, zone_cnt)

            add_combined_pack_fee(df_ship)
            add_remote_area_fee(vendor, str(date_from), str(date_to))
            add_inbound_inspection_fee(vendor, str(date_from), str(date_to))

            add_barcode_fee(st.session_state["items"], vendor)
            add_void_fee(st.session_state["items"], vendor)
            add_ppbag_fee(st.session_state["items"], vendor)
            add_video_out_fee(st.session_state["items"], vendor)

            # 4) 반품 / 회수 항목 (컬럼 누락 graceful‑skip)
            try:
                add_return_pickup_fee(st.session_state["items"], vendor, str(date_from), str(date_to))
            except sqlite3.OperationalError as err:
                if "no such column" in str(err):
                    st.warning(f"{vendor}: 반품 회수 컬럼(수취인명 등) 없음 – 건너뜀")
                else:
                    raise
            try:
                add_return_courier_fee(vendor, str(date_from), str(date_to))
            except sqlite3.OperationalError as err:
                if "no such column" in str(err):
                    st.warning(f"{vendor}: 반품 택배 컬럼 없음 – 건너뜀")
                else:
                    raise
            try:
                add_video_ret_fee(st.session_state["items"], vendor, str(date_from), str(date_to))
            except sqlite3.OperationalError as err:
                if "no such column" in str(err):
                    st.warning(f"{vendor}: 영상 반품 컬럼 없음 – 건너뜀")
                else:
                    raise

            # 5) 작업일지 자동 반영
            add_worklog_items(st.session_state["items"], vendor, str(date_from), str(date_to))

            # 6) 인보이스 생성·확정
            invoice_id = create_and_finalize_invoice(
                vendor_id=vendor_id_map[vendor],
                period_from=str(date_from),
                period_to=str(date_to),
                items=st.session_state["items"],
            )
            log.append((vendor, f"✅ #{invoice_id} ({time.time() - step_start:.2f}s)"))
        except Exception as e:
            log.append((vendor, f"❌ 실패: {e} ({time.time() - step_start:.2f}s)"))

        progress.progress(idx / total_cnt)

    st.cache_data.clear()
    progress.empty()
    st.success("✅ 인보이스 일괄 계산·확정 완료")
    st.dataframe(pd.DataFrame(log, columns=["공급처", "결과"]), use_container_width=True)

    with get_connection() as con:
        df_recent = pd.read_sql(
            "SELECT invoice_id, vendor_id, period_from, period_to, created_at FROM invoices ORDER BY invoice_id DESC LIMIT 5",
            con,
        )
    st.write("🔍 최근 5건", df_recent)
    st.page_link("pages/invoice_list.py", label="💠 인보이스 목록 열기", icon="📜")
