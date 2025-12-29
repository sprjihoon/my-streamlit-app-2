"""
backend/app/api/upload.py - 파일 업로드 API 엔드포인트
───────────────────────────────────────────────────────
logic/ 모듈의 업로드 함수를 호출하는 얇은 API 레이어.
"""

from typing import Literal, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import io

# logic 모듈에서 업로드 함수 import
from logic import ingest, list_uploads, delete_upload
from logic.db import get_connection

from backend.app.models import UploadResponse, UploadListResponse
from backend.app.api.logs import add_log

router = APIRouter(prefix="/upload", tags=["Upload"])

# 허용된 테이블 타입
TableType = Literal["inbound_slip", "shipping_stats", "kpost_in", "kpost_ret", "work_log"]


def check_admin(token: Optional[str]) -> tuple:
    """관리자 권한 확인, (is_admin, nickname) 반환"""
    if not token:
        return False, None
    with get_connection() as con:
        result = con.execute(
            "SELECT u.is_admin, u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,)
        ).fetchone()
        if result:
            return bool(result[0]), result[1]
    return False, None


@router.post("", response_model=UploadResponse)
@router.post("/", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="업로드할 Excel 파일"),
    table: TableType = Form(..., description="대상 테이블"),
    token: Optional[str] = Form(None, description="인증 토큰")
) -> UploadResponse:
    """
    Excel 파일 업로드 (관리자만).
    
    logic.ingest() 호출.
    """
    # 관리자 권한 체크
    is_admin, nickname = check_admin(token)
    if not is_admin:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    try:
        # UploadFile → BytesIO 변환
        contents = await file.read()
        file_like = io.BytesIO(contents)
        file_like.name = file.filename or "upload.xlsx"
        
        success, message = ingest(file_like, table, file.filename or "")
        
        if success:
            # 로그 기록
            add_log(
                action_type="데이터 업로드",
                target_type=table,
                target_id=None,
                target_name=file.filename,
                user_nickname=nickname,
                details=f"테이블: {table}, 파일: {file.filename}"
            )
        
        return UploadResponse(
            success=success,
            message=message,
            filename=file.filename
        )
        
    except ValueError as e:
        # 중복 파일 등 비즈니스 에러
        return UploadResponse(
            success=False,
            message=str(e),
            filename=file.filename
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=UploadListResponse)
async def get_upload_list() -> UploadListResponse:
    """
    업로드 이력 조회.
    
    logic.list_uploads() 호출.
    """
    try:
        df = list_uploads()
        uploads = df.to_dict(orient="records")
        
        return UploadListResponse(
            success=True,
            uploads=uploads
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{upload_id}")
async def remove_upload(upload_id: int, token: Optional[str] = None) -> UploadResponse:
    """
    업로드 기록 삭제 (관리자만).
    
    logic.delete_upload() 호출.
    """
    # 관리자 권한 체크
    is_admin, nickname = check_admin(token)
    if not is_admin:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    try:
        success, message = delete_upload(upload_id)
        
        if success:
            # 로그 기록
            add_log(
                action_type="업로드 삭제",
                target_type="upload",
                target_id=str(upload_id),
                target_name=None,
                user_nickname=nickname,
                details=f"업로드 ID {upload_id} 삭제"
            )
        
        return UploadResponse(
            success=success,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
