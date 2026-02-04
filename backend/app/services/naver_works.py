"""
네이버 웍스 Bot API 클라이언트
───────────────────────────────────────
JWT 인증 방식으로 네이버 웍스 API와 통신합니다.
"""

import os
import time
import json
import jwt
import httpx
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class NaverWorksClient:
    """네이버 웍스 Bot API 클라이언트"""
    
    # API 엔드포인트
    AUTH_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
    API_BASE = "https://www.worksapis.com/v1.0"
    
    def __init__(self):
        # 환경 변수에서 설정 로드
        self.domain_id = os.getenv("NAVER_WORKS_DOMAIN_ID")
        self.bot_id = os.getenv("NAVER_WORKS_BOT_ID")
        self.bot_secret = os.getenv("NAVER_WORKS_BOT_SECRET")
        self.client_id = os.getenv("NAVER_WORKS_CLIENT_ID")
        self.client_secret = os.getenv("NAVER_WORKS_CLIENT_SECRET")
        self.service_account = os.getenv("NAVER_WORKS_SERVICE_ACCOUNT")
        
        # Private Key 로드 (환경변수 우선, 없으면 파일에서)
        self.private_key = self._load_private_key()
        
        # 액세스 토큰 캐시
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    def _load_private_key(self) -> str:
        """Private Key 로드 (환경변수 우선, 파일 fallback)"""
        # 1. 환경변수에서 직접 읽기 (Railway/Vercel 배포용)
        private_key_env = os.getenv("NAVER_WORKS_PRIVATE_KEY")
        if private_key_env:
            # 다양한 형식의 줄바꿈 처리
            key = private_key_env
            
            # 이스케이프된 줄바꿈 처리 (\n 문자열 -> 실제 줄바꿈)
            key = key.replace("\\n", "\n")
            
            # \\n이 아닌 리터럴 \n 처리 (일부 환경에서)
            if "\\n" in key:
                key = key.replace("\\n", "\n")
            
            # 앞뒤 공백 제거
            key = key.strip()
            
            # 헤더/푸터 확인 및 수정
            if not key.startswith("-----BEGIN"):
                key = "-----BEGIN PRIVATE KEY-----\n" + key
            if not key.endswith("-----"):
                key = key + "\n-----END PRIVATE KEY-----"
            
            # 줄바꿈이 없는 경우 64자마다 줄바꿈 추가
            lines = key.split("\n")
            if len(lines) <= 3:  # 헤더, 내용, 푸터만 있는 경우
                # 헤더와 푸터 분리
                header = "-----BEGIN PRIVATE KEY-----"
                footer = "-----END PRIVATE KEY-----"
                content = key.replace(header, "").replace(footer, "").replace("\n", "").strip()
                
                # 64자마다 줄바꿈
                formatted_content = "\n".join([content[i:i+64] for i in range(0, len(content), 64)])
                key = f"{header}\n{formatted_content}\n{footer}"
            
            print(f"[NaverWorks] Private key loaded from env, length: {len(key)}")
            return key
        
        # 2. 파일에서 읽기 (로컬 개발용)
        private_key_path = os.getenv("NAVER_WORKS_PRIVATE_KEY_PATH", "private_key.key")
        
        # 절대 경로가 아니면 프로젝트 루트에서 찾기
        if not os.path.isabs(private_key_path):
            # 프로젝트 루트 경로 계산
            current_dir = Path(__file__).parent.parent.parent.parent
            private_key_path = current_dir / private_key_path
        
        try:
            with open(private_key_path, 'r') as f:
                key = f.read()
                print(f"[NaverWorks] Private key loaded from file, length: {len(key)}")
                return key
        except FileNotFoundError:
            print(f"Warning: Private key not found. Set NAVER_WORKS_PRIVATE_KEY env var or provide file at {private_key_path}")
            return ""
    
    def _generate_jwt(self) -> str:
        """JWT 토큰 생성"""
        current_time = int(time.time())
        
        payload = {
            "iss": self.client_id,
            "sub": self.service_account,
            "iat": current_time,
            "exp": current_time + 3600,  # 1시간 유효
        }
        
        return jwt.encode(payload, self.private_key, algorithm="RS256")
    
    async def _get_access_token(self) -> str:
        """액세스 토큰 발급 (캐시 사용)"""
        current_time = time.time()
        
        # 토큰이 유효하면 캐시된 토큰 반환
        if self._access_token and current_time < self._token_expires_at - 60:
            return self._access_token
        
        # 새 토큰 발급
        jwt_token = self._generate_jwt()
        
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "bot bot.message bot.read user.read",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.AUTH_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                raise Exception(f"Token request failed: {response.text}")
            
            result = response.json()
            self._access_token = result["access_token"]
            # 토큰 만료 시간 설정 (기본 24시간)
            expires_in = result.get("expires_in", 86400)
            # 문자열로 올 수 있으므로 int 변환
            if isinstance(expires_in, str):
                expires_in = int(expires_in)
            self._token_expires_at = current_time + expires_in
            
            return self._access_token
    
    async def send_message(
        self,
        channel_id: str,
        content: Dict[str, Any],
        channel_type: str = "group"
    ) -> Dict[str, Any]:
        """
        봇 메시지 전송
        
        Args:
            channel_id: 채널 ID (채팅방 ID)
            content: 메시지 내용
            channel_type: "user" (1:1) 또는 "group" (그룹)
        """
        token = await self._get_access_token()
        
        # 채널 타입에 따른 엔드포인트
        if channel_type == "user":
            url = f"{self.API_BASE}/bots/{self.bot_id}/users/{channel_id}/messages"
        else:
            url = f"{self.API_BASE}/bots/{self.bot_id}/channels/{channel_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=content, headers=headers)
            
            if response.status_code not in [200, 201]:
                print(f"Send message failed: {response.status_code} - {response.text}")
                return {"error": response.text}
            
            return response.json() if response.text else {"success": True}
    
    async def send_text_message(
        self,
        channel_id: str,
        text: str,
        channel_type: str = "group"
    ) -> Dict[str, Any]:
        """
        텍스트 메시지 전송
        
        Args:
            channel_id: 채널 ID
            text: 메시지 텍스트
            channel_type: "user" 또는 "group"
        """
        content = {
            "content": {
                "type": "text",
                "text": text
            }
        }
        return await self.send_message(channel_id, content, channel_type)
    
    async def send_confirm_message(
        self,
        channel_id: str,
        text: str,
        confirm_data: Dict[str, Any],
        channel_type: str = "group"
    ) -> Dict[str, Any]:
        """
        확인 버튼이 있는 메시지 전송 (버튼 템플릿)
        
        Args:
            channel_id: 채널 ID
            text: 메시지 텍스트
            confirm_data: 확인 시 전송할 데이터
            channel_type: "user" 또는 "group"
        """
        content = {
            "content": {
                "type": "button_template",
                "contentText": text,
                "actions": [
                    {
                        "type": "message",
                        "label": "확인",
                        "postback": json.dumps({"action": "confirm", "data": confirm_data})
                    },
                    {
                        "type": "message",
                        "label": "취소",
                        "postback": json.dumps({"action": "cancel"})
                    }
                ]
            }
        }
        return await self.send_message(channel_id, content, channel_type)
    
    def verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Webhook 요청의 서명 검증
        
        Args:
            body: 요청 본문 (bytes)
            signature: X-WORKS-Signature 헤더 값
        """
        import hmac
        import hashlib
        import base64
        
        expected = base64.b64encode(
            hmac.new(
                self.bot_secret.encode('utf-8'),
                body,
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        return hmac.compare_digest(expected, signature)


# 싱글톤 인스턴스
_client: Optional[NaverWorksClient] = None


def get_naver_works_client() -> NaverWorksClient:
    """네이버 웍스 클라이언트 싱글톤 반환"""
    global _client
    if _client is None:
        _client = NaverWorksClient()
    return _client
