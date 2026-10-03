"""Inbound Excel and barcode PDF exports."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Header, HTTPException

from logic.db import get_connection

from .router import router
from .utils import _get_user

# ── 입고전표 엑셀 다운로드 ────────────────────

@router.get("/batches/{batch_id}/export-xls")
def export_inbound_xls(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    입고전표 형식 엑셀 다운로드.
    파일명: {vendor_alias}_{YYYYMMDD}.xls → 중복 시 _01, _02 넘버링.
    포맷:
      A: 바코드/상품코드   B: 작업수량(실입고)  C: 요청수량(장끼)
      D: 로케이션         E: 유통기한         F: 로트번호
      G: 제조번호         H: 재고메모(품명/옵션)
    """
    import re as _re
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from fastapi.responses import StreamingResponse

    _get_user(authorization)

    with get_connection() as con:
        batch_row = con.execute(
            """SELECT vendor, vendor_canonical, inbound_date, wholesale
               FROM inbound_batches WHERE id=?""",
            (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        vendor        = batch_row[0]
        vendor_canon  = batch_row[1] or batch_row[0]
        inbound_date  = batch_row[2]          # YYYY-MM-DD
        date_str      = inbound_date.replace("-", "")  # YYYYMMDD

        # 별칭: vendor_canonical 우선, 없으면 vendor
        alias = vendor_canon or vendor
        # 파일명에 안전한 문자로 변환 (공백·슬래시 제거)
        safe_alias = _re.sub(r'[\\/:*?"<>|]', '_', alias).strip()
        base_name  = f"{safe_alias}_{date_str}"

        # 중복 넘버링: inbound_batch_exports 테이블 사용
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS inbound_batch_exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.commit()
        except Exception:
            pass

        existing = con.execute(
            "SELECT COUNT(*) FROM inbound_batch_exports WHERE batch_id=?",
            (batch_id,)
        ).fetchone()[0]

        if existing == 0:
            final_name = f"{base_name}.xls"
        else:
            final_name = f"{base_name}_{existing:02d}.xls"

        con.execute(
            "INSERT INTO inbound_batch_exports (batch_id, filename) VALUES (?, ?)",
            (batch_id, final_name)
        )
        con.commit()

        # 품목 목록 + 로케이션 조회
        items = con.execute(
            """SELECT ii.line_no, ii.item_name, ii.option_text,
                      ii.janggi_qty, ii.actual_qty, ii.missing_qty,
                      ii.matched_barcode, ii.matched_product, ii.matched_option,
                      ii.memo,
                      COALESCE(rb.로케이션, '') AS location
               FROM inbound_items ii
               LEFT JOIN repair_barcode rb ON rb.바코드 = ii.matched_barcode
               WHERE ii.batch_id = ?
               ORDER BY ii.line_no""",
            (batch_id,)
        ).fetchall()

    # ── 엑셀 생성 ──
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "입고전표"

    # 스타일
    hdr_font  = Font(name="굴림", bold=True, size=10)
    hdr_fill  = PatternFill("solid", fgColor="CCFFCC")
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_font = Font(name="굴림", size=10)
    thin      = Side(style="thin")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)

    HEADERS = [
        "상품코드/바코드(택1)", "작업수량", "요청수량",
        "로케이션", "유통기한", "로트번호", "제조번호", "재고메모",
    ]

    # 헤더 행
    for col_idx, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font      = hdr_font
        cell.fill      = hdr_fill
        cell.alignment = hdr_align
        cell.border    = border

    # 컬럼 너비
    col_widths = [22, 10, 10, 14, 12, 12, 12, 30]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 28

    # 데이터 행
    for row_idx, it in enumerate(items, 2):
        (line_no, item_name, option_text, janggi_qty, actual_qty,
         missing_qty, matched_barcode, matched_product, matched_option,
         memo, location) = it

        barcode  = matched_barcode or ""
        memo_val = ""
        if item_name:
            memo_val = item_name
        if option_text:
            memo_val += f" [{option_text}]" if memo_val else option_text
        if memo:
            memo_val += f" / {memo}" if memo_val else memo

        row_data = [
            barcode,
            actual_qty or 0,
            janggi_qty or 0,
            location,
            "",   # 유통기한
            "",   # 로트번호
            "",   # 제조번호
            memo_val,
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font   = cell_font
            cell.border = border
            if col_idx in (2, 3):
                cell.alignment = Alignment(horizontal="center")

    # 스트리밍 응답
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    encoded = quote(final_name, safe="")

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )

# ── 바코드 라벨 PDF ────────────────────

@router.post("/batches/{batch_id}/barcode-pdf")
def generate_barcode_pdf(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    실입고 확정 품목의 바코드 라벨 PDF 생성.
    품목별 actual_qty 수량만큼 라벨 생성.
    """
    from fastapi.responses import StreamingResponse as SR
    import io

    user = _get_user(authorization)

    with get_connection() as con:
        batch_row = con.execute(
            "SELECT vendor, inbound_date, wholesale FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        items = con.execute("""
            SELECT id, line_no, item_name, option_text, actual_qty,
                   matched_barcode, matched_vendor, matched_product, matched_option
            FROM inbound_items
            WHERE batch_id=? AND actual_qty > 0 AND matched_barcode IS NOT NULL
            ORDER BY line_no
        """, (batch_id,)).fetchall()

    if not items:
        raise HTTPException(status_code=400, detail="실입고 확정 및 바코드 매칭된 품목이 없습니다.")

    vendor = batch_row[0]
    inbound_date = batch_row[1]
    wholesale = batch_row[2] or ""

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.graphics.barcode import code128
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab 라이브러리가 없습니다. pip install reportlab")

    # 라벨 크기: 62mm × 38mm (열 4개 × 페이지)
    LABEL_W = 62 * mm
    LABEL_H = 38 * mm
    COLS = 3
    PAGE_W, PAGE_H = A4

    buf = io.BytesIO()

    from reportlab.pdfgen import canvas as rl_canvas
    c = rl_canvas.Canvas(buf, pagesize=A4)

    # 폰트 (한글 지원 - Noto Sans CJK 없으면 기본 폰트 사용)
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os as _os
        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        font_loaded = False
        for fp in font_paths:
            if _os.path.exists(fp):
                pdfmetrics.registerFont(TTFont("NotoKR", fp))
                FONT = "NotoKR"
                font_loaded = True
                break
        if not font_loaded:
            FONT = "Helvetica"
    except Exception:
        FONT = "Helvetica"

    margin_x = 10 * mm
    margin_y = 10 * mm
    col_gap = 3 * mm
    row_gap = 3 * mm

    label_list = []
    for item in items:
        item_id, line_no, item_name, option_text, actual_qty, barcode, m_vendor, m_product, m_option = item
        for _ in range(actual_qty):
            label_list.append({
                "barcode": barcode or "",
                "product": m_product or item_name or "",
                "option": m_option or option_text or "",
                "vendor": m_vendor or vendor,
                "wholesale": wholesale,
            })

    idx = 0
    total_labels = len(label_list)
    while idx < total_labels:
        # 페이지당 몇 행 들어가는지 계산
        rows_per_page = int((PAGE_H - 2 * margin_y) / (LABEL_H + row_gap))
        labels_per_page = COLS * rows_per_page

        for row_i in range(rows_per_page):
            for col_i in range(COLS):
                if idx >= total_labels:
                    break
                lbl = label_list[idx]
                idx += 1

                x = margin_x + col_i * (LABEL_W + col_gap)
                y = PAGE_H - margin_y - (row_i + 1) * (LABEL_H + row_gap) + row_gap

                # 라벨 테두리
                c.setStrokeColorRGB(0.8, 0.8, 0.8)
                c.setLineWidth(0.5)
                c.rect(x, y, LABEL_W, LABEL_H)

                # 바코드
                if lbl["barcode"]:
                    try:
                        bc = code128.Code128(lbl["barcode"], barHeight=12 * mm, barWidth=0.6)
                        bc_w = bc.width
                        bc_x = x + (LABEL_W - bc_w) / 2
                        bc_y = y + LABEL_H - 14 * mm
                        bc.drawOn(c, bc_x, bc_y)
                        # 바코드 텍스트
                        c.setFont(FONT, 7)
                        c.drawCentredString(x + LABEL_W / 2, y + LABEL_H - 15.5 * mm, lbl["barcode"])
                    except Exception:
                        pass

                # 상품명
                c.setFont(FONT, 8)
                product_text = lbl["product"][:20]
                c.drawCentredString(x + LABEL_W / 2, y + 7 * mm, product_text)

                # 옵션
                if lbl["option"]:
                    c.setFont(FONT, 7)
                    c.setFillColorRGB(0.4, 0.4, 0.4)
                    c.drawCentredString(x + LABEL_W / 2, y + 4.5 * mm, lbl["option"][:20])
                    c.setFillColorRGB(0, 0, 0)

                # 업체명 (좌하단)
                c.setFont(FONT, 6)
                c.setFillColorRGB(0.5, 0.5, 0.5)
                c.drawString(x + 1.5 * mm, y + 2 * mm, lbl["vendor"][:15])
                c.setFillColorRGB(0, 0, 0)

            if idx >= total_labels:
                break

        if idx < total_labels:
            c.showPage()

    c.showPage()
    c.save()
    buf.seek(0)

    # 출력 이력 저장
    now = datetime.utcnow().isoformat()
    job_id = uuid.uuid4().hex
    with get_connection() as con:
        con.execute(
            "INSERT INTO barcode_print_jobs (id, batch_id, qty, printed_by, printed_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, batch_id, total_labels, user["nickname"], now)
        )
        con.commit()

    filename = f"barcode_{vendor}_{inbound_date}.pdf"
    return SR(
        content=buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
    )
