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
    CORS_ORIGINS: str = "*"
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: str = "*"
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
    # IP 지역 조회 API 설정
    # ─────────────────────────────────────
    IPINFO_TOKEN: str = ""
    IP2LOCATION_KEY: str = ""

    # ─────────────────────────────────────
    # OpenAI API 설정
    # ─────────────────────────────────────
    OPENAI_API_KEY: str = ""

    # ─────────────────────────────────────
    # 우체국 계약소포 (Infront 회수신청)
    # ─────────────────────────────────────
    EPOST_API_KEY: str = ""
    EPOST_SECURITY_KEY: str = ""
    EPOST_CUSTOMER_ID: str = ""
    EPOST_APPROVAL_NO: str = ""
    EPOST_OFFICE_SER: str = "260940699"
    INFRONT_CENTER_ORD_NM: str = "인프론트"
    INFRONT_CENTER_NAME: str = "인프론트"
    INFRONT_CENTER_ZIPCODE: str = "41142"
    INFRONT_CENTER_ADDR1: str = "대구광역시 동구 동촌로 1"
    INFRONT_CENTER_ADDR2: str = "동대구우체국 2층 소포실"
    INFRONT_CENTER_PHONE: str = ""
    
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

