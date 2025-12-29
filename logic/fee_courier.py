# ─────────────────────────────────────
# logic/fee_courier.py
#   • 송장번호 컬럼 정규화 (과학적 표기 → 숫자)
#   • 복합키 중복 제거
#   • Streamlit 의존성 제거 - 순수 Python 함수
# ─────────────────────────────────────

import sqlite3
from typing import Dict, List, Tuple, Optional

import pandas as pd

from .db import get_connection
from .clean import TRACK_COLS, normalize_tracking

# 개발용 플래그
DEBUG_MODE = False


def calculate_courier_fee_by_zone(
    vendor: str,
    d_from: str,
    d_to: str,
    items: Optional[List[Dict]] = None
) -> Dict[str, int]:
    """
    공급처 + 날짜 기준으로 kpost_in에서 부피 → 사이즈 구간 매핑 후,
    shipping_zone 요금표 적용하여 구간별 택배요금 계산.
    
    Args:
        vendor: 공급처명
        d_from: 시작일 (YYYY-MM-DD)
        d_to: 종료일 (YYYY-MM-DD)
        items: 인보이스 항목 리스트 (제공시 in-place 수정)
    
    Returns:
        구간별 수량 딕셔너리 {구간명: 수량}
    """
    with get_connection() as con:
        # 필수 테이블 존재 확인
        tables = [
            row[0] for row in
            con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        required_tables = ["vendors", "kpost_in", "shipping_zone"]
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            if DEBUG_MODE:
                print(f"❌ {vendor}: 필요한 테이블 누락 - {missing_tables}")
            return {}

        # ① 공급처의 rate_type 확인
        cur = con.cursor()
        try:
            cur.execute("SELECT rate_type FROM vendors WHERE vendor = ?", (vendor,))
            row = cur.fetchone()
        except Exception as e:
            if DEBUG_MODE:
                print(f"❌ {vendor}: vendors 테이블 조회 실패 - {e}")
            return {}

        # rate_type 정규화
        raw_val = row[0] if row else None
        _val = (raw_val or "").strip()
        _up = _val.upper()

        if _up in ("", "STD", "STANDARD") or _val in ("기본", "표준"):
            rate_type = "표준"
        elif _up == "A":
            rate_type = "A"
        else:
            rate_type = "표준"

        # ② 별칭 목록 불러오기 (file_type = 'kpost_in')
        try:
            if "aliases" in tables:
                alias_df = pd.read_sql(
                    "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'kpost_in'",
                    con, params=(vendor,)
                )
            else:
                alias_df = pd.DataFrame(columns=["alias"])
        except Exception as e:
            if DEBUG_MODE:
                print(f"⚠️ {vendor}: aliases 조회 실패, 공급처명만 사용 - {e}")
            alias_df = pd.DataFrame(columns=["alias"])

        name_list = [vendor] + alias_df["alias"].astype(str).str.strip().tolist()

        if DEBUG_MODE:
            print(f"\n=== {vendor} 별칭 매칭 ===")
            print(f"기본 공급처명: {vendor}")
            print(f"별칭 목록: {alias_df['alias'].tolist() if not alias_df.empty else '없음'}")
            print(f"최종 검색 리스트: {name_list}")

        # ③ kpost_in 에서 부피 + 송장번호 계열 데이터 추출
        try:
            df_post = pd.read_sql(
                f"""
                SELECT *
                  FROM kpost_in
                 WHERE TRIM(발송인명) IN ({','.join('?' * len(name_list))})
                   AND DATE(접수일자) BETWEEN ? AND ?
                """,
                con, params=(*name_list, d_from, d_to)
            )
            # count 컬럼이 있다면 제거 (PyArrow 에러 방지)
            if "count" in df_post.columns:
                df_post = df_post.drop(columns=["count"])
        except Exception as e:
            if DEBUG_MODE:
                print(f"❌ {vendor}: kpost_in 조회 실패 - {e}")
            return {}

        if DEBUG_MODE:
            print(f"kpost_in 조회 결과: {len(df_post)}건")
            if not df_post.empty and "발송인명" in df_post.columns:
                발송인_counts = df_post["발송인명"].value_counts()
                print(f"발송인명별 건수: {발송인_counts.head(10).to_dict()}")

        # 필수 컬럼/행 체크
        if df_post.empty or "부피" not in df_post.columns:
            if DEBUG_MODE:
                print(f"❌ {vendor}: 데이터 없음 또는 부피 컬럼 없음")
            return {}

        # 송장/등기 번호 컬럼 → 문자열 & 정규화
        track_cols = [c for c in TRACK_COLS if c in df_post.columns]
        for col in track_cols:
            df_post[col] = normalize_tracking(df_post[col])

        # 부피 숫자 추출 로직 보강
        df_post["부피"] = (
            df_post["부피"].astype(str)
            .str.replace(r"[^0-9.]", "", regex=True)
            .str.extract(r"(\d+(?:\.\d+)?)")[0]
            .astype(float, errors="ignore")
        )
        df_post["부피"] = df_post["부피"].fillna(0).round(0).astype(int)

        # 중복 제거 (두 컬럼 모두 같을 때만)
        before = len(df_post)

        for c in ("송장번호", "TrackingNo"):
            if c in df_post.columns:
                df_post[c] = df_post[c].fillna("")

        if {"송장번호", "TrackingNo"}.issubset(df_post.columns):
            has_key = ~((df_post["송장번호"] == "") & (df_post["TrackingNo"] == ""))
            dedup = df_post[has_key].drop_duplicates(
                subset=["송장번호", "TrackingNo"], keep="first"
            )
            df_post = pd.concat([dedup, df_post[~has_key]], ignore_index=True)
        elif "송장번호" in df_post.columns:
            has_key = df_post["송장번호"] != ""
            dedup = df_post[has_key].drop_duplicates(subset=["송장번호"], keep="first")
            df_post = pd.concat([dedup, df_post[~has_key]], ignore_index=True)

        if DEBUG_MODE:
            print(f"중복 제거: {before} → {len(df_post)} 행")
            volume_counts = df_post["부피"].value_counts().head(10)
            print(f"상위 부피값: {volume_counts.to_dict()}")
            cond_80 = (df_post["부피"] == 80).sum()
            cond_mid = ((df_post["부피"] >= 71) & (df_post["부피"] <= 100)).sum()
            print(f"부피 80cm: {cond_80}건, 71-100cm 구간: {cond_mid}건")

        # ④ shipping_zone 테이블에서 해당 요금제 구간 불러오기
        df_zone = pd.read_sql(
            "SELECT * FROM shipping_zone WHERE 요금제 = ?",
            con, params=(rate_type,)
        )
        df_zone[["len_min_cm", "len_max_cm"]] = df_zone[["len_min_cm", "len_max_cm"]].apply(
            pd.to_numeric, errors="coerce"
        )
        df_zone = df_zone.sort_values("len_min_cm").reset_index(drop=True)

        # ⑤ 구간 매핑 및 수량 집계
        remaining = df_post.copy()
        size_counts = {}
        for _, row in df_zone.iterrows():
            label = row["구간"]
            min_len, max_len = row["len_min_cm"], row["len_max_cm"]
            cond = (remaining["부피"] >= min_len) & (remaining["부피"] <= max_len)
            count = int(cond.sum())

            if count > 0:
                size_counts[label] = {"count": count, "fee": row["요금"]}
                remaining = remaining[~cond]

        # ⑥ items 리스트가 제공되면 항목 추가
        if items is not None:
            for label, info in size_counts.items():
                items.append({
                    "항목": f"택배요금 ({label})",
                    "수량": info["count"],
                    "단가": info["fee"],
                    "금액": info["count"] * info["fee"],
                })

        if DEBUG_MODE:
            final_counts = {k: v.get("count", 0) for k, v in size_counts.items()}
            print(f"최종 size_counts: {final_counts}")
            print("=" * 50)

        # 함수 결과: 각 구간별 수량 딕셔너리 반환
        return {k: v.get("count", 0) for k, v in size_counts.items()}


def get_courier_fee_items(
    vendor: str,
    d_from: str,
    d_to: str
) -> List[Dict]:
    """
    구간별 택배요금 항목 리스트 반환.
    
    Returns:
        [{"항목": str, "수량": int, "단가": int, "금액": int}, ...]
    """
    items: List[Dict] = []
    calculate_courier_fee_by_zone(vendor, d_from, d_to, items)
    return items

