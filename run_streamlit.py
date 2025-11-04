#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UTF-8 환경을 강제하는 Streamlit 시작 스크립트
Windows cp949 인코딩 문제 해결
"""
import sys
import os
import locale

# UTF-8 강제 설정
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'

# sys.stdout/stderr UTF-8로 재설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# locale 설정 시도
try:
    locale.setlocale(locale.LC_ALL, '')
except:
    pass

if __name__ == '__main__':
    # Streamlit 실행
    import streamlit.web.cli as stcli
    import sys
    
    sys.argv = ["streamlit", "run", "main.py", "--server.headless", "true"]
    sys.exit(stcli.main())

