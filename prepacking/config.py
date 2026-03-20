"""
prepacking/config.py - 프리패킹 전용 설정
"""
from __future__ import annotations

import os
import pathlib


def _base_dir() -> pathlib.Path:
    if os.path.exists("/app"):
        d = pathlib.Path("/app/data")
    else:
        d = pathlib.Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


BASE_DIR = _base_dir()

# ── DB ──
PP_DB_PATH = pathlib.Path(os.getenv("PP_DB_PATH", str(BASE_DIR / "prepacking.db")))

# ── 업로드 ──
PP_UPLOAD_DIR = pathlib.Path(os.getenv("PP_UPLOAD_DIR", str(BASE_DIR / "prepacking_uploads")))
PP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── AI ──
PP_AI_MODEL = os.getenv("PP_AI_MODEL", "gpt-4o-mini")
PP_AI_TEMPERATURE = float(os.getenv("PP_AI_TEMPERATURE", "0.3"))
PP_AI_MAX_TOKENS = int(os.getenv("PP_AI_MAX_TOKENS", "2000"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── 예측 기본값 ──
DEFAULT_WEEKS_BACK = 8
DEFAULT_MIN_FREQUENCY = 3
DEFAULT_MIN_CONFIDENCE = 0.5
