from __future__ import annotations

import sqlite3
from datetime import date
from typing import Dict, Optional

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableView, QComboBox, QMessageBox
)
from PySide6.QtWidgets import QHeaderView

from common import get_connection
from native_app.qt_utils import df_to_model, model_to_df, df_to_xlsx_bytes


TARGETS: Dict[str, Dict[str, str]] = {
    "inbound_slip":   {"label": "입고전표",   "key": "공급처"},
    "shipping_stats": {"label": "배송통계",   "key": "공급처"},
    "kpost_in":       {"label": "우체국접수", "key": "발송인명"},
    "kpost_ret":      {"label": "우체국반품", "key": "수취인명"},
    "work_log":       {"label": "작업일지",   "key": "업체명"},
}


class UploadTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.tbl_select = QComboBox(self)
        for k, meta in TARGETS.items():
            self.tbl_select.addItem(meta["label"], k)

        self.btn_pick = QPushButton("엑셀 선택…", self)
        self.btn_save = QPushButton("신규 데이터 저장", self)
        self.btn_export = QPushButton("현재 데이터 다운로드", self)
        self.btn_delete = QPushButton("테이블 삭제(백업)", self)

        self.table = QTableView(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("대상 테이블"))
        top.addWidget(self.tbl_select)
        top.addStretch(1)
        top.addWidget(self.btn_pick)
        top.addWidget(self.btn_save)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_delete)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)

        self._current_df: Optional[pd.DataFrame] = None
        self._current_path: Optional[str] = None

        self.btn_pick.clicked.connect(self.pick_excel)
        self.btn_save.clicked.connect(self.save_current)
        self.btn_export.clicked.connect(self.export_current_table)
        self.btn_delete.clicked.connect(self.delete_with_backup)
        self.tbl_select.currentIndexChanged.connect(self.refresh_view)

        self.refresh_view()

    def current_table(self) -> str:
        return str(self.tbl_select.currentData())

    def pick_excel(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "엑셀 파일 선택", filter="Excel Files (*.xlsx)")
        if not file:
            return
        try:
            df = pd.read_excel(file)
        except Exception as e:
            QMessageBox.critical(self, "읽기 실패", str(e))
            return
        if df.empty:
            QMessageBox.information(self, "알림", "빈 파일입니다.")
            return
        self._current_df = df
        self._current_path = file
        self.table.setModel(df_to_model(df.head(100)))

    def save_current(self) -> None:
        if self._current_df is None:
            QMessageBox.information(self, "알림", "먼저 엑셀을 선택하세요.")
            return
        tbl = self.current_table()
        try:
            with get_connection() as con:
                try:
                    df_exist = pd.read_sql(f"SELECT * FROM {tbl}", con)
                except Exception:
                    df_exist = pd.DataFrame()

                if not df_exist.empty:
                    df_merge = pd.concat([df_exist, self._current_df]).drop_duplicates()
                else:
                    df_merge = self._current_df

                df_merge.to_sql(tbl, con, if_exists="replace", index=False)
            QMessageBox.information(self, "완료", f"{TARGETS[tbl]['label']} 저장 완료 (총 {len(df_merge):,}건)")
            self.refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))

    def export_current_table(self) -> None:
        tbl = self.current_table()
        with get_connection() as con:
            try:
                df = pd.read_sql(f"SELECT * FROM {tbl}", con)
            except Exception:
                df = pd.DataFrame()
        if df.empty:
            QMessageBox.information(self, "알림", "데이터가 없습니다.")
            return
        data = df_to_xlsx_bytes(df, sheet_name=tbl)
        file, _ = QFileDialog.getSaveFileName(self, "엑셀 저장", f"{tbl}_{date.today()}.xlsx", "Excel Files (*.xlsx)")
        if not file:
            return
        try:
            with open(file, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "완료", "다운로드 완료")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))

    def delete_with_backup(self) -> None:
        tbl = self.current_table()
        if QMessageBox.question(self, "확인", f"{TARGETS[tbl]['label']} 테이블을 백업 후 삭제할까요?") != QMessageBox.Yes:
            return
        try:
            with get_connection() as con:
                con.execute(f"DROP TABLE IF EXISTS {tbl}_backup")
                con.execute(f"CREATE TABLE {tbl}_backup AS SELECT * FROM {tbl}")
                con.execute(f"DROP TABLE IF EXISTS {tbl}")
            QMessageBox.information(self, "완료", "백업 후 삭제했습니다.")
            self.refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "삭제 실패", str(e))

    def refresh_view(self) -> None:
        tbl = self.current_table()
        with get_connection() as con:
            try:
                df = pd.read_sql(f"SELECT * FROM {tbl}", con)
            except Exception:
                df = pd.DataFrame()
        self.table.setModel(df_to_model(df))
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)


