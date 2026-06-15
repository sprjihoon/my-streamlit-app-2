import pandas as pd
import sys
sys.path.insert(0, '.')
from logic.upload import _parse_date_column, _normalize_worklog_date_col, UNIQUE_KEY, DATE_COL
from logic.db import get_connection

FILE = r'C:\Users\one\Downloads\작업일지(26년도) (2).xlsx'

# 1. 파일 읽기
df = pd.read_excel(FILE, dtype={'송장번호': 'string', '등기번호': 'string'})
df.columns = (
    df.columns.astype(str)
    .str.strip()
    .str.replace(r'[\n\r\t\xa0]', '', regex=True)
    .str.replace(r'\s+', ' ', regex=True)
    .str.strip()
)
print(f"읽은 행 수: {len(df)}")
print(f"컬럼: {df.columns.tolist()}")
vc = df['업체명'].value_counts(dropna=False).head(10)
print(f"업체명 분포:\n{vc}")

# 2. 날짜 파싱
date_col = '날짜'
df[date_col] = _parse_date_column(df[date_col])
print(f"\n날짜 dtype: {df[date_col].dtype}, 샘플: {df[date_col].head(3).tolist()}")

# 3. 중복 제거
key_cols = UNIQUE_KEY['work_log']  # ["날짜","업체명","분류","수량","단가"]
print(f"\nkey_cols: {key_cols}")

with get_connection() as con:
    try:
        existed = pd.read_sql(
            f"SELECT {', '.join(['['+c+']' for c in key_cols])} FROM work_log", con
        )
    except Exception as e:
        print(f"existed 읽기 오류: {e}")
        existed = pd.DataFrame(columns=key_cols)

print(f"existed 행 수: {len(existed)}")
print(f"existed 업체명 샘플: {existed['업체명'].head(5).tolist()}")

for kc in key_cols:
    if kc in df.columns and kc in existed.columns:
        same = df[kc].dtype == existed[kc].dtype
        print(f"  dtype {kc}: df={df[kc].dtype}, existed={existed[kc].dtype}, 같음={same}")

# 날짜를 문자열로 변환 (코드와 동일하게)
if date_col in key_cols:
    if pd.api.types.is_datetime64_any_dtype(df[date_col]):
        df[date_col] = df[date_col].dt.strftime('%Y-%m-%d')
    existed[date_col] = pd.to_datetime(existed[date_col], errors='coerce').dt.strftime('%Y-%m-%d')

# dtype 통일
for kc in key_cols:
    if kc in df.columns and kc in existed.columns:
        if df[kc].dtype != existed[kc].dtype:
            print(f"  -> {kc} dtype 변환 중")
            df[kc] = df[kc].astype(str).replace('nan', pd.NA)
            existed[kc] = existed[kc].astype(str).replace('nan', pd.NA)

# 머지
df_merged = (
    df.merge(existed, on=key_cols, how="left", indicator=True)
    .query("_merge == 'left_only'")
    .drop(columns="_merge")
)
print(f"\n머지 후 행 수: {len(df_merged)}")
print(f"머지 후 업체명 분포:")
print(df_merged['업체명'].value_counts(dropna=False).head(10))
print(f"\n업체명 NULL 수: {df_merged['업체명'].isna().sum()}")
