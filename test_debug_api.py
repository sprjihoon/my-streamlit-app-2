# -*- coding: utf-8 -*-
"""Railway 디버그 API 테스트"""
import requests
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

API_URL = "https://my-streamlit-app-2-production.up.railway.app"

print("=== kpost_in 도서행 디버그 ===\n")

# 투에버 테스트 (도서행=Y 가 203건 있어야 함)
try:
    resp = requests.get(
        f"{API_URL}/calculate/debug/kpost-doseo",
        params={"vendor": "투에버", "d_from": "2025-12-01", "d_to": "2025-12-31"},
        timeout=30
    )
    print(f"상태: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"오류: {resp.text[:500]}")
except Exception as e:
    print(f"예외: {e}")

