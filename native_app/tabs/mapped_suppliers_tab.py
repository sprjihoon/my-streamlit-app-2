from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QTextEdit, QPushButton, QTableView, QMessageBox
)
from PySide6.QtWidgets import QHeaderView

from common import get_connection
from native_app.qt_utils import df_to_model


SKU_OPTS  = ["≤100", "≤300", "≤500", "≤1,000", "≤2,000", ">2,000"]
FLAG_COLS = [
    "barcode_f", "custbox_f", "void_f", "pp_bag_f",
    "video_out_f", "video_ret_f",
]
FILE_TYPES = ["inbound_slip", "shipping_stats", "kpost_in", "kpost_ret", "work_log"]


class MappedSuppliersTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.tbl_main = QTableView(self)
        self.ed_search = QLineEdit(self)
        self.cb_vendor = QComboBox(self)
        self.cb_rate = QComboBox(self); self.cb_rate.addItems(["A","STD"])
        self.cb_sku = QComboBox(self); self.cb_sku.addItems(SKU_OPTS)
        self.flag_boxes = {c: QComboBox(self) for c in FLAG_COLS}
        for cb in self.flag_boxes.values():
            cb.addItems(["YES","NO"])
        self.txt_alias = {ft: QTextEdit(self) for ft in FILE_TYPES}

        self.btn_save = QPushButton("변경 사항 저장", self)
        self.btn_delete = QPushButton("공급처 삭제", self)

        lay = QVBoxLayout(self)
        top = QHBoxLayout(); lay.addLayout(top)
        top.addWidget(QLabel("검색")); top.addWidget(self.ed_search)
        lay.addWidget(self.tbl_main)

        form1 = QHBoxLayout(); lay.addLayout(form1)
        form1.addWidget(QLabel("공급처")); form1.addWidget(self.cb_vendor)
        form1.addWidget(QLabel("요금타입")); form1.addWidget(self.cb_rate)
        form1.addWidget(QLabel("SKU")); form1.addWidget(self.cb_sku)
        form2 = QHBoxLayout(); lay.addLayout(form2)
        for k in FLAG_COLS:
            form2.addWidget(QLabel(k)); form2.addWidget(self.flag_boxes[k])
        for ft in FILE_TYPES:
            lay.addWidget(QLabel(f"{ft} 별칭(콤마 구분)"))
            lay.addWidget(self.txt_alias[ft])
        btns = QHBoxLayout(); lay.addLayout(btns)
        btns.addStretch(1); btns.addWidget(self.btn_save); btns.addWidget(self.btn_delete)

        self.ed_search.setPlaceholderText("공급처 또는 별칭 검색…")
        self.ed_search.textChanged.connect(self.refresh_main)
        self.cb_vendor.currentIndexChanged.connect(self.load_detail)
        self.btn_save.clicked.connect(self.save_detail)
        self.btn_delete.clicked.connect(self.delete_vendor)

        self.refresh_main()

    def refresh_main(self) -> None:
        kw = self.ed_search.text().strip().lower()
        with get_connection() as con:
            df_v = pd.read_sql("SELECT * FROM vendors ORDER BY vendor", con)
        if kw:
            df = df_v[df_v["vendor"].astype(str).str.lower().str.contains(kw)]
        else:
            df = df_v
        main_cols = ["vendor", "rate_type", "sku_group", *FLAG_COLS]
        for c in main_cols:
            if c not in df.columns:
                df[c] = ""
        self.tbl_main.setModel(df_to_model(df[main_cols]))
        self.tbl_main.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cb_vendor.blockSignals(True)
        cur = self.cb_vendor.currentText()
        self.cb_vendor.clear()
        for v in df_v["vendor"].astype(str).tolist():
            self.cb_vendor.addItem(v, v)
        if cur in df_v["vendor"].values:
            self.cb_vendor.setCurrentText(cur)
        self.cb_vendor.blockSignals(False)
        self.load_detail()

    def load_detail(self) -> None:
        ven = self.cb_vendor.currentText()
        if not ven:
            return
        with get_connection() as con:
            df_v = pd.read_sql("SELECT * FROM vendors WHERE vendor=?", con, params=(ven,))
            df_a = pd.read_sql("SELECT * FROM aliases WHERE vendor=?", con, params=(ven,))
        if not df_v.empty:
            r = df_v.iloc[0]
            self.cb_rate.setCurrentText(str(r.get("rate_type", "A") or "A"))
            self.cb_sku.setCurrentText(str(r.get("sku_group", SKU_OPTS[0]) or SKU_OPTS[0]))
            for k in FLAG_COLS:
                self.flag_boxes[k].setCurrentText(str(r.get(k, "NO") or "NO"))
        alias_map = {ft: ", ".join(df_a[df_a.file_type == ft].alias.astype(str)) for ft in FILE_TYPES}
        for ft in FILE_TYPES:
            self.txt_alias[ft].setPlainText(alias_map.get(ft, ""))

    def save_detail(self) -> None:
        ven = self.cb_vendor.currentText()
        if not ven:
            return
        rate = self.cb_rate.currentText(); sku = self.cb_sku.currentText()
        flags = {k: self.flag_boxes[k].currentText() for k in FLAG_COLS}
        def split(txt: str): return [v.strip() for v in txt.split(',') if v.strip()]
        aliases = {ft: split(self.txt_alias[ft].toPlainText()) for ft in FILE_TYPES}
        try:
            with get_connection() as con:
                con.execute(
                    "UPDATE vendors SET rate_type=?, sku_group=?, "
                    + ",".join(f"{k}=?" for k in FLAG_COLS)
                    + " WHERE vendor=?",
                    (
                        rate, sku,
                        *[flags[k] for k in FLAG_COLS],
                        ven,
                    ),
                )
                con.execute("DELETE FROM aliases WHERE vendor=?", (ven,))
                for ft, lst in aliases.items():
                    for a in lst:
                        con.execute("INSERT OR IGNORE INTO aliases VALUES (?,?,?)", (a, ven, ft))
            QMessageBox.information(self, "완료", "저장 완료")
        except Exception as e:
            QMessageBox.critical(self, "실패", str(e))

    def delete_vendor(self) -> None:
        ven = self.cb_vendor.currentText()
        if not ven:
            return
        try:
            with get_connection() as con:
                con.execute("DELETE FROM vendors WHERE vendor=?", (ven,))
                con.execute("DELETE FROM aliases WHERE vendor=?", (ven,))
            QMessageBox.information(self, "완료", "삭제 완료")
            self.refresh_main()
        except Exception as e:
            QMessageBox.critical(self, "실패", str(e))


