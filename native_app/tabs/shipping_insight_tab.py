from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableView, QLineEdit, QPushButton
)
from PySide6.QtWidgets import QHeaderView

from common import get_connection
from native_app.qt_utils import df_to_model


class ShippingInsightTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.sel_table = QComboBox(self)
        self.sel_vendor_col = QComboBox(self)
        self.sel_item_col = QComboBox(self)
        self.sel_qty_col = QComboBox(self)
        self.filter_kw = QLineEdit(self)
        self.btn_reload = QPushButton("새로고침", self)

        self.tbl_summary = QTableView(self)
        self.tbl_top = QTableView(self)
        self.tbl_kw = QTableView(self)

        top1 = QHBoxLayout()
        top1.addWidget(QLabel("테이블"))
        top1.addWidget(self.sel_table)
        top1.addStretch(1)
        top1.addWidget(self.btn_reload)

        top2 = QHBoxLayout()
        top2.addWidget(QLabel("공급처 컬럼"))
        top2.addWidget(self.sel_vendor_col)
        top2.addWidget(QLabel("아이템 컬럼"))
        top2.addWidget(self.sel_item_col)
        top2.addWidget(QLabel("수량 컬럼"))
        top2.addWidget(self.sel_qty_col)
        top2.addStretch(1)
        top2.addWidget(QLabel("키워드"))
        top2.addWidget(self.filter_kw)

        lay = QVBoxLayout(self)
        lay.addLayout(top1)
        lay.addLayout(top2)
        lay.addWidget(QLabel("📦 공급처별 수량 합계"))
        lay.addWidget(self.tbl_summary)
        lay.addWidget(QLabel("🏆 상품 Top 20 (수량)"))
        lay.addWidget(self.tbl_top)
        lay.addWidget(QLabel("🔍 키워드 검색 결과"))
        lay.addWidget(self.tbl_kw)

        self.btn_reload.clicked.connect(self.refresh)
        self.sel_table.currentIndexChanged.connect(self.refresh)
        self.sel_vendor_col.currentIndexChanged.connect(self.refresh)
        self.sel_item_col.currentIndexChanged.connect(self.refresh)
        self.sel_qty_col.currentIndexChanged.connect(self.refresh)
        self.filter_kw.setPlaceholderText("키워드를 입력하세요…")
        self.filter_kw.textChanged.connect(self.refresh)

        self._df = pd.DataFrame()
        self.load_table_list()
        self.refresh()

    def load_table_list(self) -> None:
        with get_connection() as con:
            rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        names = sorted(r[0] for r in rows)
        for n in names:
            self.sel_table.addItem(n, n)

    def refresh(self) -> None:
        tbl = self.sel_table.currentData()
        if not tbl:
            return
        with get_connection() as con:
            df = pd.read_sql(f"SELECT * FROM {tbl}", con)
        self._df = df
        cols = df.columns.tolist()
        for cb in (self.sel_vendor_col, self.sel_item_col, self.sel_qty_col):
            cur = cb.currentText()
            cb.clear()
            for c in cols:
                cb.addItem(c, c)
            if cur in cols:
                cb.setCurrentText(cur)

        vcol = self.sel_vendor_col.currentText() or ("공급처" if "공급처" in cols else cols[0])
        icol = self.sel_item_col.currentText() or ("상품명" if "상품명" in cols else cols[0])
        qcol = self.sel_qty_col.currentText() or ("수량" if "수량" in cols else cols[0])

        df_sum = (df.groupby(vcol)[qcol].sum().reset_index().rename(columns={qcol: "수량"})
                  if not df.empty and qcol in df.columns else pd.DataFrame())
        self.tbl_summary.setModel(df_to_model(df_sum))
        self.tbl_summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        if not df.empty and qcol in df.columns and icol in df.columns:
            top = (df.groupby(icol)[qcol].sum().reset_index().sort_values(qcol, ascending=False).head(20))
        else:
            top = pd.DataFrame()
        self.tbl_top.setModel(df_to_model(top))
        self.tbl_top.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        kw = self.filter_kw.text().strip()
        if kw and icol in df.columns:
            df_kw = df[df[icol].astype(str).str.contains(kw, case=False, na=False)].copy()
        else:
            df_kw = pd.DataFrame()
        self.tbl_kw.setModel(df_to_model(df_kw.head(100)))
        self.tbl_kw.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


