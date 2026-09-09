with open('backend/app/api/inbound.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# 깨진 이전 추가분 제거 (여러 패턴 대응)
for bad in ['\n# ���� OCR', '\n# \ufffd\ufffd\ufffd\ufffd OCR', '\n# ── OCR 미리보기']:
    if bad in content:
        content = content[:content.index(bad)]
        break

new_endpoint = '''

# ── OCR 미리보기 (DB 저장 없이 GPT 결과만 반환) ─────────────────

@router.post("/ocr-preview")
async def ocr_preview(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """장끼 이미지를 GPT-4o로 분석해 품목 목록을 반환. DB에 저장하지 않음."""
    _get_user(authorization)

    suffix = Path(file.filename or "img.jpg").suffix or ".jpg"
    tmp_path = UPLOAD_DIR / ("preview_" + uuid.uuid4().hex + suffix)
    try:
        tmp_path.write_bytes(await file.read())
        result = await _run_ocr(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="GPT OCR를 실행할 수 없습니다. OPENAI_API_KEY를 확인하세요.",
        )

    return {
        "ok": True,
        "receipt": result.get("receipt", {}),
        "items": result.get("items", []),
        "raw": result,
    }
'''

content = content.rstrip() + new_endpoint
with open('backend/app/api/inbound.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done - lines:', content.count('\n'))
