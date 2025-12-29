"""
backend/app/api/upload.py - 파일 업로드 API 엔드포인트
───────────────────────────────────────────────────────
logic/ 모듈의 업로드 함수를 호출하는 얇은 API 레이어.
"""

from typing import Literal
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import io

# logic 모듈에서 업로드 함수 import
from logic import ingest, list_uploads, delete_upload

from backend.app.models import UploadResponse, UploadListResponse

router = APIRouter(prefix="/upload", tags=["Upload"])

# 허용된 테이블 타입
TableType = Literal["inbound_slip", "shipping_stats", "kpost_in", "kpost_ret", "work_log"]


@router.post("", response_model=UploadResponse)
@router.post("/", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="업로드할 Excel 파일"),
    table: TableType = Form(..., description="대상 테이블")
) -> UploadResponse:
    """
    Excel 파일 업로드.
    
    logic.ingest() 호출.
    """
    try:
        # UploadFile → BytesIO 변환
        contents = await file.read()
        file_like = io.BytesIO(contents)
        file_like.name = file.filename or "upload.xlsx"
        
        success, message = ingest(file_like, table, file.filename or "")
        
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
async def remove_upload(upload_id: int) -> UploadResponse:
    """
    업로드 기록 삭제.
    
    logic.delete_upload() 호출.
    """
    try:
        success, message = delete_upload(upload_id)
        
        return UploadResponse(
            success=success,
            message=message
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

