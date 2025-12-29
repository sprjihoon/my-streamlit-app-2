from __future__ import annotations

from typing import List
import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QMessageBox, QComboBox, QTableView
)

from common import get_connection
from native_app.qt_utils import df_to_model


SKU_OPTS = ["≤100","≤300","≤500","≤1,000","≤2,000",">2,000"]
FLAG_COLS = ["barcode_f","custbox_f","void_f","pp_bag_f","video_out_f","video_ret_f"]
FILE_TYPES = ["inbound_slip","shipping_stats","kpost_in","kpost_ret","work_log"]


class MappingManagerTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # inputs
        self.ed_vendor = QLineEdit(self)
        self.cb_rate = QComboBox(self); self.cb_rate.addItems(["A","STD"])
        self.cb_sku = QComboBox(self); self.cb_sku.addItems(SKU_OPTS)
        self.flag_boxes = {c: QComboBox(self) for c in FLAG_COLS}
        for cb in self.flag_boxes.values():
            cb.addItems(["YES","NO"])

        self.txt_alias = {ft: QTextEdit(self) for ft in FILE_TYPES}
        for ft, w in self.txt_alias.items():
            w.setPlaceholderText(f"{ft} 별칭을 콤마(,)로 구분하여 입력")

        self.btn_save = QPushButton("공급처 저장/업데이트", self)
        self.btn_refresh_unmatched = QPushButton("미매칭 검사", self)
        self.tbl_unmatched = QTableView(self)

        # layout
        lay = QVBoxLayout(self)
        top1 = QHBoxLayout(); lay.addLayout(top1)
        top1.addWidget(QLabel("공급처명")); top1.addWidget(self.ed_vendor)
        top1.addWidget(QLabel("요금타입")); top1.addWidget(self.cb_rate)
        top1.addWidget(QLabel("SKU 구간")); top1.addWidget(self.cb_sku)

        top2 = QHBoxLayout(); lay.addLayout(top2)
        for k in FLAG_COLS:
            top2.addWidget(QLabel(k)); top2.addWidget(self.flag_boxes[k])

        for ft in FILE_TYPES:
            lay.addWidget(QLabel(f"{ft} 별칭(콤마 구분)"))
            lay.addWidget(self.txt_alias[ft])

        btns = QHBoxLayout(); lay.addLayout(btns)
        btns.addStretch(1)
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_refresh_unmatched)

        lay.addWidget(QLabel("📁 실제 데이터 기준 미매칭 Alias"))
        lay.addWidget(self.tbl_unmatched)

        self.btn_save.clicked.connect(self.save_vendor)
        self.btn_refresh_unmatched.clicked.connect(self.refresh_unmatched)

        self.ensure_tables()
        self.refresh_unmatched()

    def ensure_tables(self) -> None:
        with get_connection() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS vendors(
                    vendor TEXT PRIMARY KEY,
                    name   TEXT,
                    rate_type TEXT,
                    sku_group TEXT
                )"""
            )
            for col in ("name","rate_type","sku_group", *FLAG_COLS):
                cols = [c[1] for c in con.execute("PRAGMA table_info(vendors);")]
                if col not in cols:
                    con.execute(f"ALTER TABLE vendors ADD COLUMN {col} TEXT")
            con.execute(
                """CREATE TABLE IF NOT EXISTS aliases(
                    alias TEXT,
                    vendor TEXT,
                    file_type TEXT,
                    PRIMARY KEY(alias, file_type)
                )"""
            )

    def save_vendor(self) -> None:
        vendor = self.ed_vendor.text().strip()
        if not vendor:
            QMessageBox.information(self, "알림", "공급처명을 입력하세요.")
            return
        rate = self.cb_rate.currentText()
        sku = self.cb_sku.currentText()
        flags = {k: self.flag_boxes[k].currentText() for k in FLAG_COLS}
        aliases = {ft: self._split_alias(self.txt_alias[ft].toPlainText()) for ft in FILE_TYPES}
        try:
            with get_connection() as con:
                con.execute(
                    """
                    INSERT INTO vendors(vendor,name,rate_type,sku_group,
                        barcode_f,custbox_f,void_f,pp_bag_f,video_out_f,video_ret_f)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(vendor) DO UPDATE SET
                        name=excluded.name, rate_type=excluded.rate_type,
                        sku_group=excluded.sku_group,
                        barcode_f=excluded.barcode_f, custbox_f=excluded.custbox_f,
                        void_f=excluded.void_f, pp_bag_f=excluded.pp_bag_f,
                        video_out_f=excluded.video_out_f, video_ret_f=excluded.video_ret_f
                    """,
                    (
                        vendor, vendor, rate, sku,
                        flags["barcode_f"], flags["custbox_f"], flags["void_f"], flags["pp_bag_f"],
                        flags["video_out_f"], flags["video_ret_f"],
                    ),
                )
                con.execute("DELETE FROM aliases WHERE vendor=?", (vendor,))
                for ft, lst in aliases.items():
                    for a in lst:
                        con.execute("INSERT OR IGNORE INTO aliases VALUES (?,?,?)", (a, vendor, ft))
            QMessageBox.information(self, "완료", "저장 완료")
            self.refresh_unmatched()
        except Exception as e:
            QMessageBox.critical(self, "실패", str(e))

    def _split_alias(self, txt: str) -> List[str]:
        return [v.strip() for v in txt.split(',') if v.strip()]

    def refresh_unmatched(self) -> None:
        with get_connection() as con:
            con.executescript(
                """
                DROP TABLE IF EXISTS alias_vendor_cache;
                CREATE TABLE alias_vendor_cache AS
                SELECT alias, file_type, vendor FROM aliases;
                """
            )
            parts = []
            src = [
                ("inbound_slip","공급처","inbound_slip"),
                ("shipping_stats","공급처","shipping_stats"),
                ("kpost_in","발송인명","kpost_in"),
                ("kpost_ret","수취인명","kpost_ret"),
                ("work_log","업체명","work_log"),
            ]
            for tbl, col, ft in src:
                exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone()
                if not exists:
                    continue
                cols = [c[1] for c in con.execute(f"PRAGMA table_info({tbl});")]
                if col not in cols:
                    continue
                parts.append(
                    f"SELECT DISTINCT {col} AS alias, '{ft}' AS file_type FROM {tbl} "
                    f"LEFT JOIN alias_vendor_cache c ON {col}=c.alias AND c.file_type='{ft}' "
                    "WHERE c.alias IS NULL"
                )
            if parts:
                df = pd.read_sql(" UNION ALL ".join(parts) + " ORDER BY file_type, alias", con)
            else:
                df = pd.DataFrame(columns=["alias","file_type"])
        self.tbl_unmatched.setModel(df_to_model(df))


