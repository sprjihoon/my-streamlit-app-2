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
from PySide6.QtGui import QAction, QPalette, QColor

from common import get_connection
from .models import DataFrameModel
from .tabs.upload_tab import UploadTab
from .tabs.rate_manager_tab import RateManagerTab
from .tabs.mapping_manager_tab import MappingManagerTab
from .tabs.mapped_suppliers_tab import MappedSuppliersTab
from .tabs.shipping_insight_tab import ShippingInsightTab
from .tabs.invoice_all_tab import InvoiceAllTab


class InvoiceListWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame = pd.DataFrame()

        self.table = QTableView(self)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        self.info = QLabel("Ready", self)
        self.btn_refresh = QPushButton("새로고침", self)
        self.btn_refresh.clicked.connect(self.load_data)

        top = QHBoxLayout()
        top.addWidget(QLabel("📜 Invoices"))
        top.addStretch(1)
        top.addWidget(self.btn_refresh)

        lay = QVBoxLayout(self)
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
        self.setWindowTitle("통합 정산 관리 – 네이티브")
        self.resize(1200, 800)

        tabs = QTabWidget(self)
        tabs.addTab(UploadTab(self), "Upload Manager")
        tabs.addTab(MappingManagerTab(self), "Mapping Manager")
        tabs.addTab(MappedSuppliersTab(self), "Mapped Suppliers")
        tabs.addTab(RateManagerTab(self), "Rate Manager")
        tabs.addTab(InvoiceListWidget(self), "Invoice List")
        tabs.addTab(InvoiceAllTab(self), "Invoice All")
        tabs.addTab(ShippingInsightTab(self), "Shipping Insight")

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
        if enabled:
            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(53, 53, 53))
            pal.setColor(QPalette.WindowText, QColor(220, 220, 220))
            pal.setColor(QPalette.Base, QColor(35, 35, 35))
            pal.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            pal.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
            pal.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
            pal.setColor(QPalette.Text, QColor(220, 220, 220))
            pal.setColor(QPalette.Button, QColor(53, 53, 53))
            pal.setColor(QPalette.ButtonText, QColor(220, 220, 220))
            pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
            pal.setColor(QPalette.Highlight, QColor(42, 130, 218))
            pal.setColor(QPalette.HighlightedText, QColor(35, 35, 35))
            app.setPalette(pal)
        else:
            app.setPalette(QPalette())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self._settings.setValue("window/geometry", self.saveGeometry())
        except Exception:
            pass
        return super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


