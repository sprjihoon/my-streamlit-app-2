import pandas as pd
from datetime import date
from common import get_connection

def shipping_stats(vendor: str, d_from: date, d_to: date, date_col: str = None) -> pd.DataFrame:
    with get_connection() as con:
        # 1) 배송통계 원본
        df = pd.read_sql("SELECT * FROM shipping_stats", con)
        df.columns = [c.strip() for c in df.columns]
        # count 컬럼이 있다면 제거 (PyArrow 에러 방지)
        if "count" in df.columns:
            df = df.drop(columns=["count"])

        # ────────── 날짜 컬럼 자동 감지 ──────────
        if not date_col:
            preferred_cols = ["배송일", "송장등록일", "출고일자", "기록일자", "등록일자"]
            date_col = next((col for col in preferred_cols if col in df.columns), None)
        if date_col not in df.columns:
            raise KeyError(f"❌ 날짜 컬럼 '{date_col}'이 shipping_stats에 없습니다.")

        # 🔍 ① 날짜 필터 전·후 행 수 확인
        before = len(df)
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df[(df[date_col] >= pd.to_datetime(d_from)) & (df[date_col] <= pd.to_datetime(d_to))]
        print("🗓️  날짜필터:", before, "→", len(df))

        # 2) 별칭 가져오기
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor = ? AND file_type = 'shipping_stats'",
            con, params=(vendor,)
        )
        name_list = [vendor] + alias_df["alias"].tolist()

        # 🔍 ② 별칭 리스트 확인
        print("🔖 name_list =", name_list[:5], "...")

        # 3) 공급처 필터
        if "공급처" not in df.columns:
            raise KeyError("❌ shipping_stats 테이블에 '공급처' 컬럼이 없습니다.")
        before = len(df)
        df = df[df["공급처"].isin(name_list)]
        print("🏷️  공급처필터:", before, "→", len(df))

        # 4) 중복 제거 – 동일 송장번호(트래킹) 행은 1건만 남김
        for key in ("송장번호", "운송장번호", "TrackingNo", "tracking_no"):
            if key in df.columns:
                dedup_before = len(df)
                df = df.drop_duplicates(subset=[key])
                print("🔁 중복제거:", dedup_before, "→", len(df))
                break

        return df.reset_index(drop=True)
