from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
	QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTableView, QMessageBox
)
from PySide6.QtWidgets import QHeaderView

from common import get_connection
from native_app.qt_utils import df_to_model, model_to_df


TABLES = {
	"out_basic": "출고비 (SKU 구간)",
	"out_extra": "추가 작업 단가",
	"shipping_zone": "배송 요금 구간",
	"material_rates": "부자재 요금표",
}

DEFAULT_DATA = {
	"out_basic": pd.DataFrame({
		"sku_group": ["≤100", "≤300", "≤500", "≤1,000", "≤2,000", ">2,000"],
		"단가": [900, 950, 1000, 1100, 1200, 1300],
	}),
	"out_extra": pd.DataFrame({
		"항목": ["입고검수", "바코드 부착", "합포장", "완충작업", "출고영상촬영", "반품영상촬영"],
		"단가": [100, 150, 100, 100, 200, 400],
	}),
	"shipping_zone": pd.DataFrame({
		"요금제": ["표준"] * 6 + ["A"] * 6,
		"구간": ["극소", "소", "중", "대", "특대", "특특대"] * 2,
		"len_min_cm": [0, 51, 71, 101, 121, 141] * 2,
		"len_max_cm": [50, 70, 100, 120, 140, 160] * 2,
		"요금": [2100, 2400, 2900, 3800, 7400, 10400, 1900, 2100, 2500, 3300, 7200, 10200],
	}),
	"material_rates": pd.DataFrame({
		"size_code": ["극소", "소", "중", "대"],
		"항목": ["택배 봉투 소형", "택배 봉투 대형", "박스 중형", "박스 대형"],
		"단가": [80, 120, 500, 800],
	}),
}


class RateManagerTab(QWidget):
	def __init__(self, parent=None) -> None:
		super().__init__(parent)

		self.sel = QComboBox(self)
		for k, v in TABLES.items():
			self.sel.addItem(v, k)

		self.btn_load = QPushButton("불러오기", self)
		self.btn_save = QPushButton("저장", self)
		self.table = QTableView(self)

		top = QHBoxLayout()
		top.addWidget(QLabel("요금 테이블"))
		top.addWidget(self.sel)
		top.addStretch(1)
		top.addWidget(self.btn_load)
		top.addWidget(self.btn_save)

		lay = QVBoxLayout(self)
		lay.addLayout(top)
		lay.addWidget(self.table)

		self.btn_load.clicked.connect(self.refresh)
		self.btn_save.clicked.connect(self.save)
		self.sel.currentIndexChanged.connect(self.refresh)
		self.refresh()

	def refresh(self) -> None:
		tbl = str(self.sel.currentData())
		with get_connection() as con:
			if tbl == "shipping_zone":
				con.execute(
					"""CREATE TABLE IF NOT EXISTS shipping_zone(
						요금제 TEXT,
						구간   TEXT,
						len_min_cm INTEGER,
						len_max_cm INTEGER,
						요금   INTEGER,
						PRIMARY KEY (요금제, 구간)
					)"""
				)
			else:
				# 첫 번째 컬럼을 키로 삼아 기본 PK 보장
				df_def = DEFAULT_DATA.get(tbl, pd.DataFrame())
				if not df_def.empty:
					cols_sql = ", ".join(f"[{c}] TEXT" for c in df_def.columns)
					pk = df_def.columns[0]
					con.execute(f"CREATE TABLE IF NOT EXISTS {tbl}({cols_sql}, PRIMARY KEY([{pk}]))")

			try:
				df = pd.read_sql(f"SELECT * FROM {tbl}", con)
			except Exception:
				df = DEFAULT_DATA.get(tbl, pd.DataFrame())
				if not df.empty:
					df.to_sql(tbl, con, index=False, if_exists="append")

		model = df_to_model(df)
		self.table.setModel(model)
		hdr = self.table.horizontalHeader()
		hdr.setSectionResizeMode(QHeaderView.Stretch)

	def save(self) -> None:
		tbl = str(self.sel.currentData())
		model = self.table.model()
		if model is None:
			QMessageBox.information(self, "알림", "저장할 데이터가 없습니다.")
			return
		df = model_to_df(model)
		with get_connection() as con:
			try:
				con.execute(f"DELETE FROM {tbl}")
			except Exception:
				pass
			df.to_sql(tbl, con, index=False, if_exists="append")
		QMessageBox.information(self, "완료", "저장 완료")
