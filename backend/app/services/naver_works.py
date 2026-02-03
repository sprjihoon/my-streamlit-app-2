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
        
        # Private Key 로드
        private_key_path = os.getenv("NAVER_WORKS_PRIVATE_KEY_PATH", "private_key.key")
        self.private_key = self._load_private_key(private_key_path)
        
        # 액세스 토큰 캐시
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    def _load_private_key(self, path: str) -> str:
        """Private Key 파일 로드"""
        # 절대 경로가 아니면 프로젝트 루트에서 찾기
        if not os.path.isabs(path):
            # 프로젝트 루트 경로 계산
            current_dir = Path(__file__).parent.parent.parent.parent
            path = current_dir / path
        
        try:
            with open(path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Warning: Private key file not found at {path}")
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
