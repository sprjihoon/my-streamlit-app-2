"""
backend/app/config.py - 환경 설정
───────────────────────────────────
환경변수 기반 설정 관리.

.env 파일 또는 시스템 환경변수에서 값을 읽습니다.
"""

import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정."""
    
    # ─────────────────────────────────────
    # 앱 정보
    # ─────────────────────────────────────
    APP_NAME: str = "Billing API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # ─────────────────────────────────────
    # 서버 설정
    # ─────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # ─────────────────────────────────────
    # 데이터베이스
    # ─────────────────────────────────────
    DATABASE_PATH: str = "/app/data/billing.db" if os.path.exists("/app/data") else "billing.db"
    
    # ─────────────────────────────────────
    # CORS 설정
    # ─────────────────────────────────────
    # 쉼표로 구분된 Origin 목록 (예: "http://localhost:3000,https://app.example.com")
    CORS_ORIGINS: str = "http://localhost:3000,https://my-streamlit-app-2.vercel.app"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "*"
    
    # ─────────────────────────────────────
    # 파일 업로드
    # ─────────────────────────────────────
    UPLOAD_DIR: str = "/app/data/uploads" if os.path.exists("/app/data") else "data/uploads"
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    
    # ─────────────────────────────────────
    # 보안
    # ─────────────────────────────────────
    SECRET_KEY: str = "change-this-in-production"
    
    # ─────────────────────────────────────
    # 프론트엔드 설정
    # ─────────────────────────────────────
    NEXT_PUBLIC_API_URL: str = "http://localhost:8000"
    
    # ─────────────────────────────────────
    # 네이버 웍스 Bot 설정
    # ─────────────────────────────────────
    NAVER_WORKS_DOMAIN_ID: str = ""
    NAVER_WORKS_BOT_ID: str = ""
    NAVER_WORKS_BOT_SECRET: str = ""
    NAVER_WORKS_CLIENT_ID: str = ""
    NAVER_WORKS_CLIENT_SECRET: str = ""
    NAVER_WORKS_SERVICE_ACCOUNT: str = ""
    NAVER_WORKS_PRIVATE_KEY_PATH: str = "private_key.key"
    
    # ─────────────────────────────────────
    # OpenAI API 설정
    # ─────────────────────────────────────
    OPENAI_API_KEY: str = ""
    
    @property
    def cors_origins_list(self) -> List[str]:
        """CORS Origins를 리스트로 반환."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def cors_methods_list(self) -> List[str]:
        """CORS Methods를 리스트로 반환."""
        if self.CORS_ALLOW_METHODS == "*":
            return ["*"]
        return [method.strip() for method in self.CORS_ALLOW_METHODS.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 싱글톤 인스턴스
settings = Settings()

