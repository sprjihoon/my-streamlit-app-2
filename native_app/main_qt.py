from __future__ import annotations

import sys
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QTabWidget,
    QMessageBox,
)
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QPalette, QColor, QFont

from common import get_connection
from .models import DataFrameModel
from .qt_utils import configure_table
from .tabs.upload_tab import UploadTab
from .tabs.rate_manager_tab import RateManagerTab
from .tabs.mapping_manager_tab import MappingManagerTab
from .tabs.mapped_suppliers_tab import MappedSuppliersTab
from .tabs.shipping_insight_tab import ShippingInsightTab
from .tabs.invoice_all_tab import InvoiceAllTab
from .tabs.estimate_tab import EstimateTab

# ─────────────────────────────────────────────────────────────────
#  글로벌 QSS 테마 (라이트 모드)
# ─────────────────────────────────────────────────────────────────
LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #F0F2F8;
}
QWidget {
    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #1E1E2E;
}

/* ── 탭 위젯 ── */
QTabWidget::pane {
    border: none;
    background: #FFFFFF;
    border-radius: 10px;
    margin-top: -1px;
}
QTabBar {
    background: transparent;
    qproperty-drawBase: 0;
}
QTabBar::tab {
    background: #E4E7F2;
    color: #6B7280;
    padding: 10px 22px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    min-width: 100px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #3B5BDB;
    font-weight: 700;
    border-top: 2px solid #3B5BDB;
}
QTabBar::tab:hover:!selected {
    background: #D4D9EE;
    color: #3B5BDB;
}

/* ── 버튼 기본 (파란색) ── */
QPushButton {
    background-color: #3B5BDB;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 13px;
    font-weight: 600;
    min-height: 30px;
}
QPushButton:hover    { background-color: #2F4AC0; }
QPushButton:pressed  { background-color: #253DA3; }
QPushButton:disabled { background-color: #C5CAE0; color: #8A8FA8; }

/* ── 위험(삭제) 버튼 ── */
QPushButton[danger="true"] {
    background-color: #E03131;
}
QPushButton[danger="true"]:hover   { background-color: #C42C2C; }
QPushButton[danger="true"]:pressed { background-color: #A82424; }
QPushButton[danger="true"]:disabled { background-color: #C5CAE0; color: #8A8FA8; }

/* ── 보조 버튼 ── */
QPushButton[secondary="true"] {
    background-color: #FFFFFF;
    color: #3B5BDB;
    border: 1.5px solid #3B5BDB;
}
QPushButton[secondary="true"]:hover   { background-color: #EEF2FF; }
QPushButton[secondary="true"]:pressed { background-color: #DBE4FF; }

/* ── 테이블 ── */
QTableView {
    background: #FFFFFF;
    border: 1px solid #E2E6F0;
    border-radius: 8px;
    gridline-color: #F0F2F8;
    selection-background-color: #DBE4FF;
    selection-color: #1E1E2E;
    alternate-background-color: #F7F8FC;
    outline: none;
}
QTableView::item {
    padding: 4px 8px;
    border: none;
}
QTableView::item:selected {
    background-color: #DBE4FF;
    color: #1E1E2E;
}
QHeaderView::section {
    background-color: #EEF0F8;
    color: #4A4E69;
    padding: 9px 12px;
    border: none;
    border-right: 1px solid #DDE0EE;
    border-bottom: 1px solid #D1D5E8;
    font-weight: 700;
    font-size: 12px;
}
QHeaderView::section:last {
    border-right: none;
}

/* ── 입력 필드 ── */
QLineEdit, QDateEdit {
    background: #FFFFFF;
    border: 1.5px solid #D1D5E8;
    border-radius: 6px;
    padding: 6px 10px;
    color: #1E1E2E;
    min-height: 28px;
}
QLineEdit:focus, QDateEdit:focus {
    border: 1.5px solid #3B5BDB;
    background: #FAFBFF;
}
QLineEdit[readOnly="true"] {
    background: #F3F4F8;
    color: #6B7280;
    border-color: #E2E6F0;
}

/* ── 콤보박스 ── */
QComboBox {
    background: #FFFFFF;
    border: 1.5px solid #D1D5E8;
    border-radius: 6px;
    padding: 6px 10px;
    color: #1E1E2E;
    min-height: 28px;
    min-width: 80px;
}
QComboBox:focus { border: 1.5px solid #3B5BDB; }
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #D1D5E8;
    border-radius: 6px;
    selection-background-color: #DBE4FF;
    selection-color: #1E1E2E;
}

/* ── 그룹박스 ── */
QGroupBox {
    border: 1.5px solid #E2E6F0;
    border-radius: 10px;
    margin-top: 18px;
    padding: 16px 10px 10px 10px;
    background: #FFFFFF;
    font-weight: 700;
    color: #4A4E69;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    top: -10px;
    background: #FFFFFF;
    padding: 0 8px;
    color: #3B5BDB;
    font-size: 12px;
}

/* ── 체크박스 ── */
QCheckBox {
    spacing: 6px;
    font-size: 13px;
    color: #4A4E69;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1.5px solid #D1D5E8;
    border-radius: 4px;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    background: #3B5BDB;
    border-color: #3B5BDB;
}

/* ── 스크롤바 ── */
QScrollBar:vertical {
    width: 8px;
    background: #F0F2F8;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #C5CAE0;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #9DA5C9; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    height: 8px;
    background: #F0F2F8;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #C5CAE0;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #9DA5C9; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── 메뉴바 / 메뉴 ── */
QMenuBar {
    background: #FFFFFF;
    color: #4A4E69;
    border-bottom: 1px solid #E2E6F0;
    padding: 2px;
}
QMenuBar::item:selected { background: #EEF2FF; color: #3B5BDB; border-radius: 4px; }
QMenu {
    background: #FFFFFF;
    border: 1px solid #E2E6F0;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 8px 24px; border-radius: 4px; }
QMenu::item:selected { background: #EEF2FF; color: #3B5BDB; }

/* ── 상태바 ── */
QStatusBar {
    background: #EAECF5;
    color: #6B7280;
    font-size: 12px;
    border-top: 1px solid #D1D5E8;
}

/* ── 스플리터 ── */
QSplitter::handle {
    background: #E2E6F0;
    width: 1px;
    height: 1px;
}

/* ── 툴팁 ── */
QToolTip {
    background: #1E1E2E;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ── 레이블 ── */
QLabel {
    color: #1E1E2E;
    background: transparent;
}
"""

DARK_QSS = """
QMainWindow, QDialog {
    background-color: #1A1B2E;
}
QWidget {
    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #E0E0F0;
    background-color: #1A1B2E;
}
QTabWidget::pane {
    border: none;
    background: #252640;
    border-radius: 10px;
    margin-top: -1px;
}
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab {
    background: #2A2B45;
    color: #8B8FA8;
    padding: 10px 22px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 500;
    min-width: 100px;
}
QTabBar::tab:selected {
    background: #252640;
    color: #7B9EFF;
    font-weight: 700;
    border-top: 2px solid #7B9EFF;
}
QTabBar::tab:hover:!selected { background: #333460; color: #7B9EFF; }
QPushButton {
    background-color: #4C6EF5;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 600;
    min-height: 30px;
}
QPushButton:hover    { background-color: #3B5BDB; }
QPushButton:pressed  { background-color: #2F4AC0; }
QPushButton:disabled { background-color: #3A3B55; color: #6B7280; }
QPushButton[danger="true"] { background-color: #C92A2A; }
QPushButton[danger="true"]:hover { background-color: #A61E1E; }
QPushButton[danger="true"]:disabled { background-color: #3A3B55; color: #6B7280; }
QPushButton[secondary="true"] {
    background-color: transparent;
    color: #7B9EFF;
    border: 1.5px solid #4C6EF5;
}
QPushButton[secondary="true"]:hover { background-color: #2A2B45; }
QTableView {
    background: #252640;
    border: 1px solid #3A3B58;
    border-radius: 8px;
    gridline-color: #2E2F4A;
    selection-background-color: #3B4A80;
    selection-color: #E0E0F0;
    alternate-background-color: #2B2C46;
    outline: none;
    color: #E0E0F0;
}
QTableView::item { padding: 4px 8px; border: none; }
QHeaderView::section {
    background-color: #2A2B45;
    color: #9DA5C9;
    padding: 9px 12px;
    border: none;
    border-right: 1px solid #3A3B58;
    border-bottom: 1px solid #3A3B58;
    font-weight: 700;
    font-size: 12px;
}
QLineEdit, QDateEdit {
    background: #2A2B45;
    border: 1.5px solid #3A3B58;
    border-radius: 6px;
    padding: 6px 10px;
    color: #E0E0F0;
    min-height: 28px;
}
QLineEdit:focus, QDateEdit:focus { border: 1.5px solid #4C6EF5; }
QLineEdit[readOnly="true"] { background: #222335; color: #8B8FA8; border-color: #3A3B58; }
QComboBox {
    background: #2A2B45;
    border: 1.5px solid #3A3B58;
    border-radius: 6px;
    padding: 6px 10px;
    color: #E0E0F0;
    min-height: 28px;
    min-width: 80px;
}
QComboBox:focus { border: 1.5px solid #4C6EF5; }
QComboBox QAbstractItemView {
    background: #2A2B45;
    border: 1px solid #3A3B58;
    selection-background-color: #3B4A80;
    color: #E0E0F0;
}
QGroupBox {
    border: 1.5px solid #3A3B58;
    border-radius: 10px;
    margin-top: 18px;
    padding: 16px 10px 10px 10px;
    background: #252640;
    font-weight: 700;
    color: #9DA5C9;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    top: -10px;
    background: #252640;
    padding: 0 8px;
    color: #7B9EFF;
    font-size: 12px;
}
QCheckBox { spacing: 6px; font-size: 13px; color: #9DA5C9; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1.5px solid #3A3B58;
    border-radius: 4px;
    background: #2A2B45;
}
QCheckBox::indicator:checked { background: #4C6EF5; border-color: #4C6EF5; }
QScrollBar:vertical { width: 8px; background: #2A2B45; border-radius: 4px; }
QScrollBar::handle:vertical { background: #4A4B65; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #6B7280; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 8px; background: #2A2B45; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #4A4B65; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenuBar { background: #1E1F35; color: #9DA5C9; border-bottom: 1px solid #3A3B58; padding: 2px; }
QMenuBar::item:selected { background: #2A2B45; color: #7B9EFF; border-radius: 4px; }
QMenu { background: #252640; border: 1px solid #3A3B58; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 8px 24px; border-radius: 4px; color: #E0E0F0; }
QMenu::item:selected { background: #3B4A80; color: #7B9EFF; }
QStatusBar { background: #1E1F35; color: #6B7280; font-size: 12px; border-top: 1px solid #3A3B58; }
QSplitter::handle { background: #3A3B58; width: 1px; height: 1px; }
QToolTip { background: #252640; color: #E0E0F0; border: 1px solid #3A3B58; border-radius: 4px; padding: 4px 8px; }
QLabel { color: #E0E0F0; background: transparent; }
"""


class InvoiceListWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame = pd.DataFrame()

        self.table = QTableView(self)
        configure_table(self.table)

        self.info = QLabel("Ready", self)
        self.info.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.btn_refresh = QPushButton("새로고침", self)
        self.btn_refresh.setProperty("secondary", "true")
        self.btn_refresh.clicked.connect(self.load_data)

        top = QHBoxLayout()
        lbl = QLabel("📜  인보이스 목록")
        lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #1E1E2E;")
        top.addWidget(lbl)
        top.addStretch(1)
        top.addWidget(self.btn_refresh)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addWidget(self.info)

        self.load_data()

    def load_data(self) -> None:
        try:
            with get_connection() as con:
                # 최근 생성순으로 기본 컬럼 조회 + 업체명 조인 시도
                has_vendors = bool(
                    con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vendors'").fetchone()
                )
                if has_vendors:
                    sql = (
                        "SELECT i.invoice_id, IFNULL(v.name, v.vendor) AS 업체, i.vendor_id, "
                        "i.period_from, i.period_to, i.created_at, IFNULL(i.status,'미확정') AS status, i.total_amount "
                        "FROM invoices i LEFT JOIN vendors v ON i.vendor_id=v.vendor_id "
                        "ORDER BY i.invoice_id DESC"
                    )
                else:
                    sql = (
                        "SELECT invoice_id, vendor_id AS 업체, vendor_id, period_from, period_to, created_at, "
                        "IFNULL(status,'미확정') AS status, total_amount "
                        "FROM invoices ORDER BY invoice_id DESC"
                    )
                df = pd.read_sql(sql, con)

            # 타입 후처리(숫자 컬럼 캐스팅)
            for col in ("total_amount",):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            self._df = df
            model = DataFrameModel(self._df)
            self.table.setModel(model)
            self.info.setText(f"{len(self._df):,}건 로드 완료")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"인보이스 로드 실패: {e}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("통합 정산 관리")
        self.resize(1280, 860)
        self.setMinimumSize(900, 600)

        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)
        tabs.addTab(UploadTab(self),           "📁  업로드")
        tabs.addTab(MappingManagerTab(self),   "🗂  매핑")
        tabs.addTab(MappedSuppliersTab(self),  "🏷  공급처")
        tabs.addTab(RateManagerTab(self),      "💰  요율")
        tabs.addTab(InvoiceListWidget(self),   "📜  인보이스")
        tabs.addTab(InvoiceAllTab(self),       "📊  전체 정산")
        tabs.addTab(EstimateTab(self),         "📄  견적서")
        tabs.addTab(ShippingInsightTab(self),  "🚚  배송 분석")

        self.setCentralWidget(tabs)

        # Menu: View → Dark Mode toggle
        menubar = self.menuBar()
        view_menu = menubar.addMenu("보기")
        act_dark = QAction("다크 모드", self, checkable=True)
        act_dark.toggled.connect(self.toggle_dark_mode)
        view_menu.addAction(act_dark)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Restore window state
        self._settings = QSettings("MyCompany", "BillingNativeApp")
        if (geo := self._settings.value("window/geometry")):
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass
        if (idx := self._settings.value("window/tab_index")) is not None:
            try:
                tabs.setCurrentIndex(int(idx))
            except Exception:
                pass
        tabs.currentChanged.connect(lambda i: self._settings.setValue("window/tab_index", i))

    def toggle_dark_mode(self, enabled: bool) -> None:
        app = QApplication.instance()
        if not app:
            return
        app.setStyleSheet(DARK_QSS if enabled else LIGHT_QSS)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self._settings.setValue("window/geometry", self.saveGeometry())
        except Exception:
            pass
        return super().closeEvent(event)


def main() -> int:
    # HiDPI / Retina 대응
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 기본 폰트 설정
    font = QFont("Malgun Gothic", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # 라이트 테마 초기 적용
    app.setStyleSheet(LIGHT_QSS)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


