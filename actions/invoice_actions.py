# actions/invoice_actions.py
# -----------------------------------------------------------
# • 인보이스 계산에 필요한 모든 액션
# • Python 3.12  / Streamlit 1.44
# -----------------------------------------------------------
import sqlite3
from typing import Dict, List

import pandas as pd
import streamlit as st
from common import get_connection

# ─────────────────────────
# 작업일지 컬럼 상수
# ─────────────────────────
WL_COL_DATE = "날짜"
WL_COL_VEN  = "업체명"
WL_COL_CAT  = "분류"
WL_COL_UNIT = "단가"
WL_COL_QTY  = "수량"
WL_COL_AMT  = "합계"
WL_COL_MEMO = "비고1"


# ───────────────────────────────────────────────
# kpost_ret 레코드 수 카운트 공통 함수  ★여기에 추가
# ───────────────────────────────────────────────
def _count_kpost_ret(con, names, d_from, d_to) -> int:
    """
    kpost_ret 테이블에서 지정된 ‘수취인명’ 목록과 기간 조건에
    맞는 행 수를 반환한다.
    """
    if not names:               # 안전장치 (빈 리스트면 0 반환)
        return 0

    placeholders = ",".join("?" * len(names))  # ?,?,?... 만들기
    sql = f"""
        SELECT COUNT(*) AS c
        FROM kpost_ret
        WHERE 수취인명 IN ({placeholders})
          AND DATE(배달일자) BETWEEN DATE(?) AND DATE(?)
    """
    (cnt,) = con.execute(sql, (*names, d_from, d_to)).fetchone()
    return cnt


# -----------------------------------------------------------
# 1. 기본 출고비 (행 개수 × 900)
# -----------------------------------------------------------
def add_basic_shipping(df_items: pd.DataFrame,
                       vendor: str,
                       d_from: str,
                       d_to: str) -> pd.DataFrame:
    with get_connection() as con:
        df_raw = pd.read_sql("SELECT * FROM shipping_stats", con)
        df_raw.columns = [c.strip() for c in df_raw.columns]

        date_col = next((c for c in ["배송일","송장등록일","출고일자","기록일자","등록일자"]
                         if c in df_raw.columns), None)
        if not date_col:
            raise KeyError("shipping_stats 날짜 컬럼 없음")

        df_raw[date_col] = pd.to_datetime(df_raw[date_col], errors="coerce")
        df_raw = df_raw[(df_raw[date_col] >= pd.to_datetime(d_from)) &
                        (df_raw[date_col] <= pd.to_datetime(d_to))]

        # ───────────────────────────────────────
        # NEW ⚙️  중복 출고 행 제거
        #   • 동일 송장번호(Tracking No) 로 여러 번 업로드된 경우를 방지
        #   • 기본 키 후보: "송장번호", 없으면 "운송장번호" · "트래킹번호" 등
        # ───────────────────────────────────────
        for key_col in ("송장번호", "운송장번호", "TrackingNo", "tracking_no"):
            if key_col in df_raw.columns:
                df_raw = df_raw.drop_duplicates(subset=[key_col])
                break  # 첫 번째로 발견된 키 컬럼으로 dedup 완료

        alias = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor=? AND file_type='shipping_stats'",
            con, params=(vendor,))
        df = df_raw[df_raw["공급처"].str.strip()
                     .isin([vendor] + alias["alias"].tolist())]

    total = int(len(df))
    row   = {"항목": "기본 출고비", "수량": total, "단가": 900, "금액": total * 900}
    return pd.concat([df_items, pd.DataFrame([row])], ignore_index=True)

# -----------------------------------------------------------
# 2. 구간별 택배요금
# -----------------------------------------------------------
def add_courier_fee_by_zone(vendor: str, d_from: str, d_to: str) -> Dict[str, int]:
    with get_connection() as con:
        rate = con.execute(
            "SELECT COALESCE(rate_type,'STD') FROM vendors WHERE vendor=?",
            (vendor,)).fetchone()[0]

        alias = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor=? AND file_type='kpost_in'",
            con, params=(vendor,))
        names = [vendor] + alias["alias"].tolist()

        df_post = pd.read_sql(
            f"SELECT 부피 FROM kpost_in WHERE 발송인명 IN ({','.join('?'*len(names))}) "
            "AND 접수일자 BETWEEN ? AND ?", con, params=(*names, d_from, d_to))
        if df_post.empty:
            return {}

        df_post["부피"] = pd.to_numeric(df_post["부피"], errors="coerce").fillna(0)
        df_zone = pd.read_sql(
            "SELECT * FROM shipping_zone WHERE 요금제=?", con, params=(rate,)
        ).sort_values("len_min_cm")

    zone_cnt: Dict[str, int] = {}
    for _, z in df_zone.iterrows():
        cnt = int(df_post[(df_post["부피"] >= z["len_min_cm"]) &
                          (df_post["부피"] <= z["len_max_cm"])].shape[0])
        if cnt:
            st.session_state["items"].append(
                {"항목": f"택배요금 ({z['구간']})",
                 "수량": cnt, "단가": z["요금"], "금액": cnt * z["요금"]})
            zone_cnt[z["구간"]] = cnt
    return zone_cnt


# ─────────────────────────────────────────────
# 3. 인보이스 DB 유틸
# ─────────────────────────────────────────────
def get_invoice_id(vendor_id: int, d_from: str, d_to: str):
    with get_connection() as con:
        row = con.execute(
            "SELECT invoice_id FROM invoices "
            "WHERE vendor_id=? AND period_from=? AND period_to=?",
            (vendor_id, d_from, d_to)).fetchone()
    return row[0] if row else None


def finalize_invoice(iid: int) -> None:
    with get_connection() as con:
        con.execute(
            "UPDATE invoices SET status='확정',finalized_at=CURRENT_TIMESTAMP "
            "WHERE invoice_id=?", (iid,))


def create_and_finalize_invoice(vendor_id: int,
                                period_from: str,
                                period_to: str,
                                items: List[Dict]) -> str:
    total = sum(it["금액"] for it in items)

    with get_connection() as con:
        cur = con.cursor()

        # ── invoices 헤더 INSERT ──
        cur.execute(
            "INSERT INTO invoices "
            "(vendor_id, period_from, period_to, "
            " created_at, total_amount, status) "
            "VALUES ( ?, ?, ?, CURRENT_TIMESTAMP, ?, '확정')",
            (vendor_id, period_from, period_to, total)
        )
        iid = cur.lastrowid

        # ── invoice_items INSERT ──
        cur.executemany(
            "INSERT INTO invoice_items "
            "(invoice_id, item_name, qty, unit_price, amount, remark) "
            "VALUES ( ?, ?, ?, ?, ?, ? )",
            [
                (iid,
                 it["항목"],
                 it["수량"],
                 it["단가"],
                 it["금액"],
                 it.get("비고", ""))        # 👈 없으면 빈 문자열
                for it in items
            ]
        )
        con.commit()

    return str(iid)


# ─────────────────────────────────────────────
# 4. 단가 헬퍼
# ─────────────────────────────────────────────
def get_extra_unit(label: str) -> int:
    with get_connection() as con:
        try:
            val = pd.read_sql("SELECT 단가 FROM out_extra WHERE 항목=?",
                              con, params=(label,)).squeeze()
            if pd.notna(val):
                return int(val)
        except Exception:
            pass
    defaults = {"출고영상촬영": 200, "반품영상촬영": 400, "반품회수": 1100}
    return defaults.get(label, 0)


def get_material_unit(label: str) -> int:
    with get_connection() as con:
        try:
            val = pd.read_sql("SELECT 단가 FROM material_rates WHERE 항목=?",
                              con, params=(label,)).squeeze()
            if pd.notna(val):
                return int(val)
        except Exception:
            pass
    return 80


# ─────────────────────────────────────────────
# 5. 플래그 공통 함수 & 래퍼
# ─────────────────────────────────────────────
def add_flag_fee(items: List[dict], vendor: str,
                 flag_col: str, label: str,
                 qty_source: str, unit_func):
    with get_connection() as con:
        flag = con.execute(
            f"SELECT COALESCE({flag_col},'NO') FROM vendors WHERE vendor=?",
            (vendor,)).fetchone()[0]
    if flag != "YES":
        return

    qty = next((it["수량"] for it in items if it["항목"] == qty_source), 0)
    if qty == 0:
        return

    unit = unit_func(label)
    items.append({"항목": label, "수량": qty, "단가": unit, "금액": qty * unit})


def add_barcode_fee(items, vendor):
    add_flag_fee(items, vendor, "barcode_f", "바코드 부착",
                 "입고검수", get_extra_unit)


def add_void_fee(items, vendor):
    add_flag_fee(items, vendor, "void_f", "완충작업",
                 "기본 출고비", get_extra_unit)


def add_ppbag_fee(items, vendor):
    add_flag_fee(items, vendor, "pp_bag_f", "PP 봉투", "입고검수",
                 lambda _: get_material_unit("PP 봉투 중형"))


def add_video_out_fee(items, vendor):
    add_flag_fee(items, vendor, "video_out_f", "출고영상촬영",
                 "기본 출고비", get_extra_unit)


# ─────────────────────────────────────────────
# 6. 반품 관련 액션
# ─────────────────────────────────────────────
def add_return_pickup_fee(items, vendor, d_from, d_to):
    with get_connection() as con:
        alias = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor=? AND file_type='kpost_ret'",
            con, params=(vendor,))
        names = [vendor] + alias["alias"].tolist()
        cnt = _count_kpost_ret(con, names, d_from, d_to)   # ← 그대로 호출
    if cnt:
        unit = get_extra_unit("반품회수")
        items.append({"항목": "반품 회수비", "수량": cnt,
                      "단가": unit, "금액": cnt * unit})



def add_return_courier_fee(vendor, d_from, d_to):
    with get_connection() as con:
        rate = con.execute(
            "SELECT COALESCE(rate_type,'STD') FROM vendors WHERE vendor=?",
            (vendor,)).fetchone()[0]
        alias = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor=? AND file_type='kpost_ret'",
            con, params=(vendor,))
        names = [vendor] + alias["alias"].tolist()
        df = pd.read_sql(
            f"SELECT 우편물부피 FROM kpost_ret "
            f"WHERE 수취인명 IN ({','.join('?' * len(names))}) "
            "AND 배달일자 BETWEEN ? AND ?",
            con, params=(*names, d_from, d_to))
        if df.empty:
            return
        df["우편물부피"] = pd.to_numeric(df["우편물부피"],
                                       errors="coerce").fillna(0)
        zone = (pd.read_sql(
                    "SELECT * FROM shipping_zone WHERE 요금제=?", con,
                    params=(rate,))
                .sort_values("len_min_cm"))

    for _, z in zone.iterrows():
        cnt = df[(df["우편물부피"] >= z["len_min_cm"]) &
                 (df["우편물부피"] <= z["len_max_cm"])].shape[0]
        if cnt:
            st.session_state["items"].append(
                {"항목": f"반품 택배요금 ({z['구간']})", "수량": cnt,
                 "단가": z["요금"], "금액": cnt * z["요금"]})


def add_video_ret_fee(items, vendor, d_from, d_to):
    with get_connection() as con:
        if con.execute(
            "SELECT COALESCE(video_ret_f,'NO') FROM vendors WHERE vendor=?",
            (vendor,)).fetchone()[0] != "YES":
            return
        alias = pd.read_sql(
            "SELECT alias FROM aliases WHERE vendor=? AND file_type='kpost_ret'",
            con, params=(vendor,))
        names = [vendor] + alias["alias"].tolist()
        cnt = _count_kpost_ret(con, names, d_from, d_to)   # ← 그대로 호출
    if cnt:
        unit = get_extra_unit("반품영상촬영")
        items.append({"항목": "반품영상촬영", "수량": cnt,
                      "단가": unit, "금액": cnt * unit})

# ─────────────────────────────────────────────
# 7. 봉투/박스 자동 매칭
# ─────────────────────────────────────────────
def add_box_fee_by_zone(item_list: List[dict],
                        vendor: str,
                        zone_counts: Dict[str, int]) -> None:
    """
    • pp_bag_f = YES and custbox_f = YES
        극소·소 → 택배 봉투(소형), 중 → 택배 봉투(대형)
    • 그 외: 각 구간에 맞는 박스
    """

    # 1) 공급처 플래그
    with get_connection() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT pp_bag_f, custbox_f FROM vendors WHERE vendor=?",
            (vendor,)).fetchone()
        use_mailer = (row and row["pp_bag_f"] == "YES"
                      and row["custbox_f"] == "YES")

        # 2) 단가 테이블
        rates = (pd.read_sql(
                    "SELECT size_code, 항목, 단가 FROM material_rates",
                    con)
                 .set_index("size_code"))

    # 3) 포장재 선택
    def pick(size: str, want_mailer: bool):
        if size not in rates.index:
            return None
        df_sel = (rates.loc[[size]]
                  if isinstance(rates.loc[size], pd.Series)
                  else rates.loc[size])

        if want_mailer:
            if size in ("극소", "소"):
                df_m = df_sel[df_sel["항목"].str.contains("택배 봉투") &
                               df_sel["항목"].str.contains("소형")]
                if not df_m.empty:
                    return df_m.iloc[0]
            if size == "중":
                df_m = df_sel[df_sel["항목"].str.contains("택배 봉투") &
                               df_sel["항목"].str.contains("대형")]
                if not df_m.empty:
                    return df_m.iloc[0]

        df_b = df_sel[df_sel["항목"].str.contains("박스")]
        return df_b.iloc[0] if not df_b.empty else None

    # 4) 항목 추가
    for size, qty in zone_counts.items():
        if qty == 0:
            continue
        rec = pick(size, use_mailer)
        if rec is None:
            continue
        item_list.append({
            "항목": rec["항목"],
            "수량": int(qty),
            "단가": int(rec["단가"]),
            "금액": int(qty) * int(rec["단가"]),
        })

# ─────────────────────────────────────────────
# 8-bis. 작업일지 → 인보이스 항목
# ─────────────────────────────────────────────


def add_worklog_items(item_list, vendor, d_from, d_to):
    with get_connection() as con:
        # ① work_log 전용 별칭 가져오기
        alias_df = pd.read_sql(
            "SELECT alias FROM aliases "
            "WHERE vendor=? AND file_type IN ('work_log','all')",
            con, params=(vendor,)
        )
        names = [vendor] + alias_df["alias"].tolist()

        # ② IN (…) 구문으로 데이터 로드
        placeholders = ",".join("?" * len(names))
        df = pd.read_sql(
            f"""SELECT {WL_COL_DATE}, {WL_COL_CAT}, {WL_COL_UNIT},
                       {WL_COL_QTY},  {WL_COL_AMT}, {WL_COL_MEMO}
                FROM work_log
                WHERE {WL_COL_VEN} IN ({placeholders})
                  AND {WL_COL_DATE} BETWEEN ? AND ?""",
            con, params=(*names, d_from, d_to)
        )

    if df.empty:
        return

    # ─ 비고 NaN → '' 통일
    df[WL_COL_MEMO] = df[WL_COL_MEMO].fillna("").str.strip()

    # ─ 분류 + 단가 + 비고 동일 행 합계
    df_final = (df
                .groupby([WL_COL_CAT, WL_COL_UNIT, WL_COL_MEMO],
                         as_index=False, sort=False)
                .agg({WL_COL_QTY: "sum", WL_COL_AMT: "sum"}))

    # ─ 인보이스 항목 push
    for _, r in df_final.iterrows():
        name = (r[WL_COL_CAT] if r[WL_COL_MEMO] == ""
                else f"{r[WL_COL_CAT]} ({r[WL_COL_MEMO]})")
        item_list.append({
            "항목":  name,
            "수량":  int(r[WL_COL_QTY]),
            "단가":  int(r[WL_COL_UNIT]),
            "금액":  int(r[WL_COL_AMT]),
            "비고":  r[WL_COL_MEMO]
        })
