"""
native_app/tabs/estimate_tab.py - 견적서 관리 탭
───────────────────────────────────────────────────
견적서 목록 조회, 세부내역 확인, PDF 다운로드 기능 제공
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional, List, Dict, Any

import pandas as pd
from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QMessageBox, QDateEdit, QComboBox, QSplitter,
    QGroupBox, QFormLayout, QLineEdit, QAbstractItemView,
    QCheckBox, QFileDialog,
)

from common import get_connection
from native_app.qt_utils import df_to_model, configure_table


class EstimateTab(QWidget):
    """견적서 관리 탭 - 목록 조회 및 세부내역 확인"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_estimate_id: Optional[int] = None
        self._setup_ui()
        self._connect_signals()
        self.load_estimates()

    def _setup_ui(self) -> None:
        """UI 구성"""
        main_layout = QVBoxLayout(self)

        # 상단: 필터 영역
        filter_group = QGroupBox("검색 조건")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("시작일"))
        self.dt_from = QDateEdit(self)
        self.dt_from.setCalendarPopup(True)
        today = QDate.currentDate()
        self.dt_from.setDate(QDate(today.year(), today.month(), 1))
        filter_layout.addWidget(self.dt_from)

        filter_layout.addWidget(QLabel("종료일"))
        self.dt_to = QDateEdit(self)
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDate(today)
        filter_layout.addWidget(self.dt_to)

        filter_layout.addWidget(QLabel("페이지 크기"))
        self.cmb_page_size = QComboBox(self)
        self.cmb_page_size.addItems(["10", "30", "50"])
        self.cmb_page_size.setCurrentIndex(0)
        filter_layout.addWidget(self.cmb_page_size)

        filter_layout.addStretch(1)

        self.btn_search = QPushButton("🔍  검색", self)
        filter_layout.addWidget(self.btn_search)

        self.btn_refresh = QPushButton("새로고침", self)
        self.btn_refresh.setProperty("secondary", "true")
        filter_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(filter_group)

        # 중앙: 스플리터 (목록 + 상세)
        splitter = QSplitter(Qt.Horizontal)

        # 왼쪽: 견적서 목록
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("📋 견적서 목록"))
        self.lbl_total = QLabel("총 0건")
        list_header.addStretch(1)
        list_header.addWidget(self.lbl_total)
        list_layout.addLayout(list_header)

        # 다중 선택 모드 체크박스
        select_layout = QHBoxLayout()
        self.chk_multi_select = QCheckBox("다중 선택 모드", self)
        select_layout.addWidget(self.chk_multi_select)
        select_layout.addStretch(1)

        # 삭제 버튼들
        self.btn_delete_selected = QPushButton("선택 삭제", self)
        self.btn_delete_selected.setEnabled(False)
        self.btn_delete_selected.setProperty("danger", "true")
        select_layout.addWidget(self.btn_delete_selected)

        self.btn_delete_current = QPushButton("현재 견적서 삭제", self)
        self.btn_delete_current.setEnabled(False)
        self.btn_delete_current.setProperty("danger", "true")
        select_layout.addWidget(self.btn_delete_current)

        list_layout.addLayout(select_layout)

        self.tbl_list = QTableView(self)
        configure_table(self.tbl_list)
        self.tbl_list.setSelectionMode(QAbstractItemView.SingleSelection)
        list_layout.addWidget(self.tbl_list)

        # 페이지네이션
        page_layout = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 이전", self)
        self.lbl_page = QLabel("1 / 1")
        self.btn_next = QPushButton("다음 ▶", self)
        page_layout.addStretch(1)
        page_layout.addWidget(self.btn_prev)
        page_layout.addWidget(self.lbl_page)
        page_layout.addWidget(self.btn_next)
        page_layout.addStretch(1)
        list_layout.addLayout(page_layout)

        splitter.addWidget(list_widget)

        # 오른쪽: 견적서 상세
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # 상세 헤더
        detail_header = QHBoxLayout()
        detail_header.addWidget(QLabel("📄 견적서 상세"))
        self.btn_export_pdf = QPushButton("⬇  PDF 다운로드", self)
        self.btn_export_pdf.setEnabled(False)
        detail_header.addStretch(1)
        detail_header.addWidget(self.btn_export_pdf)
        detail_layout.addLayout(detail_header)

        # 견적서 기본 정보
        info_group = QGroupBox("기본 정보")
        info_form = QFormLayout(info_group)

        self.txt_id = QLineEdit(self)
        self.txt_id.setReadOnly(True)
        info_form.addRow("견적번호:", self.txt_id)

        self.txt_company = QLineEdit(self)
        self.txt_company.setReadOnly(True)
        info_form.addRow("업체명:", self.txt_company)

        self.txt_contact = QLineEdit(self)
        self.txt_contact.setReadOnly(True)
        info_form.addRow("연락처:", self.txt_contact)

        self.txt_email = QLineEdit(self)
        self.txt_email.setReadOnly(True)
        info_form.addRow("이메일:", self.txt_email)

        self.txt_brand_type = QLineEdit(self)
        self.txt_brand_type.setReadOnly(True)
        info_form.addRow("브랜드유형:", self.txt_brand_type)

        self.txt_total = QLineEdit(self)
        self.txt_total.setReadOnly(True)
        info_form.addRow("총 금액:", self.txt_total)

        self.txt_created = QLineEdit(self)
        self.txt_created.setReadOnly(True)
        info_form.addRow("생성일:", self.txt_created)

        detail_layout.addWidget(info_group)

        # 견적 항목 테이블
        items_lbl = QLabel("📦  견적 항목")
        items_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #4A4E69; margin-top: 4px;")
        detail_layout.addWidget(items_lbl)
        self.tbl_items = QTableView(self)
        configure_table(self.tbl_items, sortable=False)
        detail_layout.addWidget(self.tbl_items)

        splitter.addWidget(detail_widget)
        splitter.setSizes([400, 600])

        main_layout.addWidget(splitter)

        # 페이지 상태
        self._current_page = 1
        self._total_pages = 1
        self._total_count = 0

    def _connect_signals(self) -> None:
        """시그널 연결"""
        self.btn_search.clicked.connect(self._on_search)
        self.btn_refresh.clicked.connect(self.load_estimates)
        self.btn_prev.clicked.connect(self._on_prev_page)
        self.btn_next.clicked.connect(self._on_next_page)
        self.tbl_list.clicked.connect(self._on_list_clicked)
        self.tbl_list.doubleClicked.connect(self._on_list_double_clicked)
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)
        self.cmb_page_size.currentIndexChanged.connect(self._on_page_size_changed)
        self.chk_multi_select.toggled.connect(self._on_multi_select_toggled)
        self.btn_delete_selected.clicked.connect(self._on_delete_selected)
        self.btn_delete_current.clicked.connect(self._on_delete_current)

    def _on_search(self) -> None:
        """검색 버튼 클릭"""
        self._current_page = 1
        self.load_estimates()

    def _on_page_size_changed(self) -> None:
        """페이지 크기 변경"""
        self._current_page = 1
        self.load_estimates()

    def _on_multi_select_toggled(self, checked: bool) -> None:
        """다중 선택 모드 토글"""
        if checked:
            self.tbl_list.setSelectionMode(QAbstractItemView.MultiSelection)
            self.btn_delete_selected.setEnabled(True)
        else:
            self.tbl_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.btn_delete_selected.setEnabled(False)
            self.tbl_list.clearSelection()

    def _get_selected_ids(self) -> List[int]:
        """선택된 견적서 ID 목록 반환"""
        model = self.tbl_list.model()
        if not model:
            return []

        selected_ids = []
        selection = self.tbl_list.selectionModel()
        if not selection:
            return []

        for index in selection.selectedRows(0):
            id_item = model.item(index.row(), 0)
            if id_item:
                try:
                    selected_ids.append(int(id_item.text()))
                except ValueError:
                    pass

        return selected_ids

    def _on_delete_selected(self) -> None:
        """선택된 견적서들 삭제"""
        selected_ids = self._get_selected_ids()
        if not selected_ids:
            QMessageBox.information(self, "알림", "삭제할 견적서를 선택하세요.")
            return

        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"선택한 {len(selected_ids)}개의 견적서를 삭제하시겠습니까?\n\n"
            f"삭제 대상 ID: {', '.join(map(str, selected_ids))}\n\n"
            "이 작업은 되돌릴 수 없습니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            with get_connection() as con:
                placeholders = ",".join("?" * len(selected_ids))
                con.execute(
                    f"DELETE FROM estimates WHERE id IN ({placeholders})",
                    selected_ids
                )
                con.commit()

            QMessageBox.information(
                self, "완료", f"{len(selected_ids)}개의 견적서가 삭제되었습니다."
            )

            # 현재 선택된 견적서가 삭제된 경우 상세 정보 초기화
            if self._current_estimate_id in selected_ids:
                self._clear_detail()

            self.load_estimates()

        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패: {e}")

    def _on_delete_current(self) -> None:
        """현재 보고 있는 견적서 삭제"""
        if self._current_estimate_id is None:
            QMessageBox.information(self, "알림", "삭제할 견적서를 먼저 선택하세요.")
            return

        company_name = self.txt_company.text() or "(업체명 없음)"
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"견적서 #{self._current_estimate_id} ({company_name})을(를) 삭제하시겠습니까?\n\n"
            "이 작업은 되돌릴 수 없습니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            with get_connection() as con:
                con.execute(
                    "DELETE FROM estimates WHERE id = ?",
                    (self._current_estimate_id,)
                )
                con.commit()

            QMessageBox.information(
                self, "완료", f"견적서 #{self._current_estimate_id}이(가) 삭제되었습니다."
            )

            self._clear_detail()
            self.load_estimates()

        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패: {e}")

    def _clear_detail(self) -> None:
        """상세 정보 초기화"""
        self._current_estimate_id = None
        self.txt_id.clear()
        self.txt_company.clear()
        self.txt_contact.clear()
        self.txt_email.clear()
        self.txt_brand_type.clear()
        self.txt_total.clear()
        self.txt_created.clear()
        self.btn_export_pdf.setEnabled(False)
        self.btn_delete_current.setEnabled(False)
        self._display_items([])

    def _on_prev_page(self) -> None:
        """이전 페이지"""
        if self._current_page > 1:
            self._current_page -= 1
            self.load_estimates()

    def _on_next_page(self) -> None:
        """다음 페이지"""
        if self._current_page < self._total_pages:
            self._current_page += 1
            self.load_estimates()

    def load_estimates(self) -> None:
        """견적서 목록 로드"""
        date_from = self.dt_from.date().toString("yyyy-MM-dd")
        date_to = self.dt_to.date().toString("yyyy-MM-dd")
        page_size = int(self.cmb_page_size.currentText())

        try:
            with get_connection() as con:
                # 테이블 존재 확인
                tables = [row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='estimates'"
                ).fetchall()]
                if not tables:
                    self._show_empty_list()
                    return

                # 총 개수 조회
                where = "date(created_at) >= ? AND date(created_at) <= ?"
                params = [date_from, date_to]
                count_row = con.execute(
                    f"SELECT COUNT(*) FROM estimates WHERE {where}", params
                ).fetchone()
                self._total_count = count_row[0] if count_row else 0

                # 페이지 계산
                self._total_pages = max(1, (self._total_count + page_size - 1) // page_size)
                if self._current_page > self._total_pages:
                    self._current_page = self._total_pages

                # 목록 조회
                offset = (self._current_page - 1) * page_size
                rows = con.execute(
                    f"""
                    SELECT id, company_name, contact, email, total_amount, brand_type, created_at
                    FROM estimates WHERE {where}
                    ORDER BY id DESC LIMIT ? OFFSET ?
                    """,
                    params + [page_size, offset],
                ).fetchall()

                # DataFrame 생성
                df = pd.DataFrame(rows, columns=[
                    "ID", "업체명", "연락처", "이메일", "총금액", "브랜드유형", "생성일"
                ])

                # 금액 포맷
                if not df.empty and "총금액" in df.columns:
                    df["총금액"] = df["총금액"].apply(lambda x: f"{int(x):,}원" if x else "0원")

                self.tbl_list.setModel(df_to_model(df))

                # 상태 업데이트
                self.lbl_total.setText(f"총 {self._total_count:,}건")
                self.lbl_page.setText(f"{self._current_page} / {self._total_pages}")
                self.btn_prev.setEnabled(self._current_page > 1)
                self.btn_next.setEnabled(self._current_page < self._total_pages)

        except Exception as e:
            QMessageBox.critical(self, "오류", f"견적서 목록 로드 실패: {e}")

    def _show_empty_list(self) -> None:
        """빈 목록 표시"""
        df = pd.DataFrame(columns=["ID", "업체명", "연락처", "이메일", "총금액", "브랜드유형", "생성일"])
        self.tbl_list.setModel(df_to_model(df))
        self.lbl_total.setText("총 0건")
        self.lbl_page.setText("1 / 1")
        self._total_count = 0
        self._total_pages = 1
        self._current_page = 1
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)

    def _on_list_clicked(self, index) -> None:
        """목록 클릭 - 상세 정보 로드"""
        model = self.tbl_list.model()
        if not model:
            return

        row = index.row()
        id_item = model.item(row, 0)
        if not id_item:
            return

        try:
            estimate_id = int(id_item.text())
            self._load_estimate_detail(estimate_id)
        except ValueError:
            pass

    def _on_list_double_clicked(self, index) -> None:
        """목록 더블클릭 - 상세 정보 로드 (동일 동작)"""
        self._on_list_clicked(index)

    def _load_estimate_detail(self, estimate_id: int) -> None:
        """견적서 상세 정보 로드"""
        try:
            with get_connection() as con:
                row = con.execute(
                    """
                    SELECT id, company_name, contact, email, total_amount, brand_type, items_json, created_at
                    FROM estimates WHERE id = ?
                    """,
                    (estimate_id,),
                ).fetchone()

                if not row:
                    QMessageBox.warning(self, "알림", f"견적서 #{estimate_id}를 찾을 수 없습니다.")
                    return

                # 기본 정보 표시
                self._current_estimate_id = row[0]
                self.txt_id.setText(str(row[0]))
                self.txt_company.setText(row[1] or "")
                self.txt_contact.setText(row[2] or "")
                self.txt_email.setText(row[3] or "")
                total_amount = int(row[4]) if row[4] else 0
                self.txt_total.setText(f"{total_amount:,}원")

                brand_type = row[5] or "fashion"
                brand_type_display = {
                    "fashion": "패션",
                    "beauty": "뷰티",
                    "etc": "기타"
                }.get(brand_type, brand_type)
                self.txt_brand_type.setText(brand_type_display)

                created_at = row[7]
                if hasattr(created_at, "strftime"):
                    self.txt_created.setText(created_at.strftime("%Y-%m-%d %H:%M"))
                else:
                    self.txt_created.setText(str(created_at or ""))

                # 항목 파싱 및 표시
                items_json = row[6] or "[]"
                try:
                    items = json.loads(items_json)
                except json.JSONDecodeError:
                    items = []

                self._display_items(items)
                self.btn_export_pdf.setEnabled(True)
                self.btn_delete_current.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "오류", f"견적서 상세 로드 실패: {e}")

    def _display_items(self, items: List[Dict[str, Any]]) -> None:
        """견적 항목 테이블에 표시"""
        if not items:
            df = pd.DataFrame(columns=["항목", "수량", "단가", "금액", "비고"])
        else:
            rows = []
            for item in items:
                rows.append({
                    "항목": item.get("항목", ""),
                    "수량": f"{int(item.get('수량', 0)):,}",
                    "단가": f"{int(item.get('단가', 0)):,}원",
                    "금액": f"{int(item.get('금액', 0)):,}원",
                    "비고": item.get("비고", ""),
                })
            df = pd.DataFrame(rows)

        self.tbl_items.setModel(df_to_model(df))

    def _on_export_pdf(self) -> None:
        """PDF 다운로드"""
        if self._current_estimate_id is None:
            QMessageBox.information(self, "알림", "먼저 견적서를 선택하세요.")
            return

        try:
            with get_connection() as con:
                row = con.execute(
                    """
                    SELECT company_name, contact, email, items_json, total_amount, brand_type
                    FROM estimates WHERE id = ?
                    """,
                    (self._current_estimate_id,),
                ).fetchone()

                if not row:
                    QMessageBox.warning(self, "알림", "견적서를 찾을 수 없습니다.")
                    return

                company_name = row[0] or ""
                contact = row[1] or ""
                email = row[2] or ""
                items_json = row[3] or "[]"
                total_amount = int(row[4]) if row[4] else 0
                brand_type = row[5] or "fashion"

                try:
                    items = json.loads(items_json)
                except json.JSONDecodeError:
                    items = []

            # PDF 생성
            from logic.estimate_pdf import create_estimate_pdf
            from datetime import datetime

            # 회사 설정 조회
            with get_connection() as con:
                company_row = con.execute("""
                    SELECT company_name, business_number, address, business_type, business_item, representative
                    FROM company_settings WHERE id = 1
                """).fetchone()

            if company_row:
                supplier_info = {
                    "사업자번호": company_row[1] or "",
                    "상호": company_row[0] or "",
                    "소재지": company_row[2] or "",
                    "업태": company_row[3] or "",
                    "종목": company_row[4] or "",
                }
                representative = company_row[5] or ""
                company_display_name = company_row[0] or ""
            else:
                supplier_info = {"사업자번호": "", "상호": "", "소재지": "", "업태": "", "종목": ""}
                representative = ""
                company_display_name = ""

            estimate_date = datetime.now().strftime("%Y-%m-%d")
            recipient_name = company_name.strip() or "(업체명)"
            if recipient_name != "(업체명)" and not recipient_name.endswith(" 귀하"):
                recipient_name = f"{recipient_name} 귀하"

            manager = "장성령" if brand_type == "fashion" else "장명찬"

            items_for_pdf = [
                {"항목": it.get("항목", ""), "수량": it.get("수량", 0), "단가": it.get("단가", 0), "금액": it.get("금액", 0), "비고": it.get("비고", "")}
                for it in items
            ]

            pdf_bytes = create_estimate_pdf(
                estimate_date=estimate_date,
                recipient_name=recipient_name,
                title="물류대행 서비스 견적",
                supplier_info=supplier_info,
                items=items_for_pdf,
                stamp_holder=representative,
                manager=manager,
                company_name=company_display_name,
                recipient_contact=contact,
                recipient_email=email,
                validity_days=15,
            )

            # 파일 저장 다이얼로그
            filename = f"견적서_{company_name or 'estimate'}_{estimate_date}.pdf"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "PDF 저장", filename, "PDF Files (*.pdf)"
            )

            if file_path:
                with open(file_path, "wb") as f:
                    f.write(pdf_bytes)
                QMessageBox.information(self, "완료", f"PDF가 저장되었습니다:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 생성 실패: {e}")
