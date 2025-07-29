# ─────────────────────────────────────
# utils/utils_courier.py
#   • 송장번호 컬럼 정규화 (과학적 표기 → 숫자)
#   • 복합키 중복 제거
# ─────────────────────────────────────

import sqlite3
import pandas as pd
import streamlit as st
from common import get_connection
from utils.clean import TRACK_COLS, normalize_tracking

# 개발용 플래그
DEBUG_MODE = True

def add_courier_fee_by_zone(vendor: str, d_from: str, d_to: str) -> None:
    """
    공급처 + 날짜 기준으로 kpost_in에서 부피 → 사이즈 구간 매핑 후,
    shipping_zone 요금표 적용하여 구간별 택배요금 항목을 session_state["items"]에 추가.
    """
    with get_connection() as con:
        # ① 공급처의 rate_type 확인
        cur = con.cursor()
        cur.execute("SELECT rate_type FROM vendors WHERE vendor = ?", (vendor,))
        row = cur.fetchone()

        # ─ rate_type 정규화 ────────────────────────────
        raw_val = row[0] if row else None
        _val = (raw_val or "").strip()
        _up  = _val.upper()

        if _up in ("", "STD", "STANDARD") or _val in ("기본", "표준"):
            rate_type = "표준"
        elif _up == "A":
            rate_type = "A"
        else:
            rate_type = "표준"

        # ② 별칭 목록 불러오기 (file_type = 'kpost_in')
        alias_df = pd.read_sql(
            "SELECT alias FROM alias_vendor_v WHERE vendor = ?",
            con, params=(vendor,)
        )
        name_list = [vendor] + alias_df["alias"].astype(str).str.strip().tolist()

        # ③ kpost_in 에서 부피 + 송장번호 계열 데이터 추출
        df_post = pd.read_sql(
            f"""
            SELECT 부피, 등기번호, 송장번호, 운송장번호, TrackingNo, tracking_no
            FROM kpost_in
            WHERE TRIM(발송인명) IN ({','.join('?' * len(name_list))})
              AND 접수일자 BETWEEN ? AND ?
            """, con, params=(*name_list, d_from, d_to)
        )

        # ── 필수 컬럼/행 체크 ──
        if df_post.empty or "부피" not in df_post.columns:
            return

        # ── 1️⃣·2️⃣  송장/등기 번호 컬럼 → 문자열 & 정규화 ─────────────────
        # 1️⃣·2️⃣  ─────────────────────────────────────────────
        track_cols = [c for c in TRACK_COLS if c in df_post.columns]
        for col in track_cols:
            df_post[col] = normalize_tracking(df_post[col])

        # ── 부피 값 숫자만 추출
        df_post["부피"] = (df_post["부피"].astype(str)
                             .str.extract(r"(\d+\.?\d*)")[0]
                             .astype(float))
        df_post["부피"] = df_post["부피"].fillna(0).round(0).astype(int)

        # ── 3️⃣  두 컬럼 조합으로 중복 제거 + 4️⃣ 로그 출력 ────────────────
        # 3️⃣  중복 제거 (두 컬럼 모두 같을 때만)
        before = len(df_post)

        # 빈 값 통일
        for c in ("송장번호", "TrackingNo"):
            if c in df_post.columns:
                df_post[c] = df_post[c].fillna("")

        if {"송장번호", "TrackingNo"}.issubset(df_post.columns):
            df_post = df_post.drop_duplicates(subset=["송장번호", "TrackingNo"], keep="first")
        elif "송장번호" in df_post.columns:
            df_post = df_post.drop_duplicates(subset=["송장번호"], keep="first")

        if DEBUG_MODE:
            st.write(f"🔁 중복제거: {before} → {len(df_post)}")

        # ④ shipping_zone 테이블에서 해당 요금제 구간 불러오기
        df_zone = pd.read_sql("SELECT * FROM shipping_zone WHERE 요금제 = ?", con, params=(rate_type,))
        df_zone[["len_min_cm","len_max_cm"]] = df_zone[["len_min_cm","len_max_cm"]].apply(pd.to_numeric, errors="coerce")
        df_zone = df_zone.sort_values("len_min_cm").reset_index(drop=True)

        # ⑤ 구간 매핑 및 수량 집계
        remaining = df_post.copy()
        size_counts = {}
        for _, row in df_zone.iterrows():
            min_len = row["len_min_cm"]
            max_len = row["len_max_cm"]
            label = row["구간"]
            fee = row["요금"]

            cond = (remaining["부피"] >= min_len) & (remaining["부피"] <= max_len)
            count = int(cond.sum())
            remaining = remaining[~cond]
            if count > 0:
                size_counts[label] = {"count": count, "fee": fee}

        # ⑥ session_state["items"]에 추가
        for label, info in size_counts.items():
            qty = info["count"]
            unit = info["fee"]
            st.session_state["items"].append({
                "항목": f"택배요금 ({label})",
                "수량": qty,
                "단가": unit,
                "금액": qty * unit
            })

        if DEBUG_MODE:
            vol80 = df_post[df_post["부피"] == 80].shape[0]
            cond_mid = ((df_post["부피"] >= 71) & (df_post["부피"] <= 100)).sum()
            st.write(
                {
                    "📝 80cm": vol80,
                    "📝 71~100cm": cond_mid,
                    "📊 size_counts": {k: v["count"] for k, v in size_counts.items()},
                }
            )
