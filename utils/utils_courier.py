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
DEBUG_MODE = True  # 터미널 디버깅을 위해 True로 유지

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
        # 모든 컬럼(*) 조회 → 일부 테이블에 특정 송장번호 컬럼이 없더라도 오류 없이 로드
        df_post = pd.read_sql(
            f"""
            SELECT *
              FROM kpost_in
             WHERE TRIM(발송인명) IN ({','.join('?' * len(name_list))})
               AND DATE(접수일자) BETWEEN ? AND ?
            """,
            con, params=(*name_list, d_from, d_to)
        )

        # ── 필수 컬럼/행 체크 ──
        if df_post.empty or "부피" not in df_post.columns:
            return

        # ── 1️⃣·2️⃣  송장/등기 번호 컬럼 → 문자열 & 정규화 ─────────────────
        # 1️⃣·2️⃣  ─────────────────────────────────────────────
        track_cols = [c for c in TRACK_COLS if c in df_post.columns]
        for col in track_cols:
            df_post[col] = normalize_tracking(df_post[col])

        # ── 부피 숫자 추출 로직 보강 ─────────────────────────────
        #   ① 숫자·소수점 이외 문자 제거 → "80cm" → "80"
        #   ② 첫 번째 정수/소수 패턴 추출 → r"(\d+(?:\.\d+)?)"
        #   ③ float → round → int
        df_post["부피"] = (
            df_post["부피"].astype(str)
            .str.replace(r"[^0-9.]", "", regex=True)           # 숫자·. 만 남김
            .str.extract(r"(\d+(?:\.\d+)?)")[0]
            .astype(float, errors="ignore")
        )

        df_post["부피"] = df_post["부피"].fillna(0).round(0).astype(int)

        # ── 3️⃣  두 컬럼 조합으로 중복 제거 + 4️⃣ 로그 출력 ────────────────
        # 3️⃣  중복 제거 (두 컬럼 모두 같을 때만)
        before = len(df_post)

        # 빈 값 통일
        for c in ("송장번호", "TrackingNo"):
            if c in df_post.columns:
                df_post[c] = df_post[c].fillna("")

        # 두 키 모두 공백이면 중복 판단 대상 제외
        if {"송장번호", "TrackingNo"}.issubset(df_post.columns):
            has_key = ~((df_post["송장번호"] == "") & (df_post["TrackingNo"] == ""))
            dedup = df_post[has_key].drop_duplicates(subset=["송장번호", "TrackingNo"], keep="first")
            df_post = pd.concat([dedup, df_post[~has_key]], ignore_index=True)
        elif "송장번호" in df_post.columns:
            has_key = df_post["송장번호"] != ""
            dedup = df_post[has_key].drop_duplicates(subset=["송장번호"], keep="first")
            df_post = pd.concat([dedup, df_post[~has_key]], ignore_index=True)

        print(f"\n[DEBUG] 중복 제거 전: {before} 행")
        if DEBUG_MODE:
            print(f"[DEBUG] 중복 제거 후: {len(df_post)} 행")

        # ④ shipping_zone 테이블에서 해당 요금제 구간 불러오기
        df_zone = pd.read_sql("SELECT * FROM shipping_zone WHERE 요금제 = ?", con, params=(rate_type,))
        df_zone[["len_min_cm","len_max_cm"]] = df_zone[["len_min_cm","len_max_cm"]].apply(pd.to_numeric, errors="coerce")
        df_zone = df_zone.sort_values("len_min_cm").reset_index(drop=True)

        if DEBUG_MODE:
            print("\n[DEBUG] 부피(cm) 값 분포 (상위 10개):")
            print(df_post['부피'].value_counts().head(10))
            if 80 in df_post['부피'].values:
                print("✅ 부피 80cm 데이터가 존재합니다.")
            else:
                print("❌ 부피 80cm 데이터가 누락되었습니다.")

        # ⑤ 구간 매핑 및 수량 집계
        remaining = df_post.copy()
        size_counts = {}
        for _, row in df_zone.iterrows():
            label = row["구간"]
            min_len, max_len = row["len_min_cm"], row["len_max_cm"]
            cond = (remaining["부피"] >= min_len) & (remaining["부피"] <= max_len)
            count = int(cond.sum())

            if DEBUG_MODE and count > 0:
                print(f"  - 구간 '{label}' ({min_len}~{max_len}cm): {count} 건")

            if count > 0:
                size_counts[label] = {"count": count, "fee": row["요금"]}
                remaining = remaining[~cond]  # 중복 방지

        if not size_counts:
            print("[DEBUG] 매핑된 구간이 하나도 없습니다.")

        # ⑥ session_state["items"]에 추가
        for label, info in size_counts.items():
            st.session_state["items"].append(
                {
                    "항목": f"택배요금 ({label})",
                    "수량": info["count"],
                    "단가": info["fee"],
                    "금액": info["count"] * info["fee"],
                }
            )

        # 기존 디버그 출력은 위에서 통합

        # 함수 결과: 각 구간별 수량 딕셔너리 반환
        return {k: v["count"] for k, v in size_counts.items()}
