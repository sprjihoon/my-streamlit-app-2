from __future__ import annotations

from datetime import date, datetime
from typing import List, Tuple

import pandas as pd
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit, QPushButton, QTableView, QMessageBox, QListWidget, QListWidgetItem, QAbstractItemView, QProgressDialog
)
from PySide6.QtWidgets import QHeaderView

from common import get_connection
from native_app.qt_utils import df_to_model

# 전체 비용 항목 반영
from core.utils_shipping import shipping_stats
from utils.utils_courier import add_courier_fee_by_zone
from utils.utils_combined import add_combined_pack_fee
from utils.utils_inbound import add_inbound_inspection_fee
from utils.utils_remote import add_remote_area_fee
from actions.invoice_actions import (
    add_basic_shipping,
    add_box_fee_by_zone,
    add_barcode_fee,
    add_void_fee,
    add_ppbag_fee,
    add_video_out_fee,
    add_return_pickup_fee,
    add_return_courier_fee,
    add_video_ret_fee,
    add_worklog_items,
    create_and_finalize_invoice,
)


class InvoiceAllTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.dt_from = QDateEdit(self); self.dt_from.setCalendarPopup(True)
        self.dt_to = QDateEdit(self); self.dt_to.setCalendarPopup(True)
        today = QDate.currentDate()
        self.dt_from.setDate(QDate(today.year(), today.month(), 1))
        self.dt_to.setDate(today)

        self.btn_load_vendors = QPushButton("공급처 불러오기", self)
        self.btn_run = QPushButton("인보이스 일괄 생성", self)
        self.lst_vendors = QListWidget(self); self.lst_vendors.setSelectionMode(QAbstractItemView.MultiSelection)
        self.tbl_log = QTableView(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("시작일")); top.addWidget(self.dt_from)
        top.addWidget(QLabel("종료일")); top.addWidget(self.dt_to)
        top.addStretch(1); top.addWidget(self.btn_load_vendors); top.addWidget(self.btn_run)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(QLabel("공급처 (다중선택 가능)"))
        lay.addWidget(self.lst_vendors)
        lay.addWidget(QLabel("결과 로그"))
        lay.addWidget(self.tbl_log)

        self.btn_load_vendors.clicked.connect(self.load_vendors)
        self.btn_run.clicked.connect(self.run_all)

        self.load_vendors()

    def load_vendors(self) -> None:
        self.lst_vendors.clear()
        with get_connection() as con:
            try:
                df = pd.read_sql("SELECT vendor_id, vendor FROM vendors ORDER BY vendor", con)
            except Exception:
                df = pd.DataFrame(columns=["vendor_id","vendor"])
        for _, r in df.iterrows():
            it = QListWidgetItem(str(r["vendor"]))
            it.setData(32, int(r["vendor_id"]))
            it.setSelected(True)
            self.lst_vendors.addItem(it)

    def run_all(self) -> None:
        d_from = self.dt_from.date().toString("yyyy-MM-dd")
        d_to = self.dt_to.date().toString("yyyy-MM-dd")
        items: List[Tuple[str, str]] = []
        # vendor_id 맵
        with get_connection() as con:
            try:
                df_v = pd.read_sql("SELECT vendor_id, vendor FROM vendors", con)
            except Exception:
                QMessageBox.information(self, "알림", "공급처가 없습니다.")
                return
        vmap = dict(zip(df_v.vendor, df_v.vendor_id))

        logs = []
        prog = QProgressDialog("인보이스 생성 중…", "취소", 0, self.lst_vendors.count(), self)
        prog.setWindowTitle("진행 상황")
        prog.setMinimumDuration(0)
        prog.setValue(0)
        for i in range(self.lst_vendors.count()):
            it = self.lst_vendors.item(i)
            if not it.isSelected():
                continue
            ven = it.text()
            try:
                # 1) 출고 통계 (dedup 포함)
                df_ship = shipping_stats(ven, d_from, d_to)

                # 2) 항목 구성 리스트
                items: list[dict] = []

                # 기본 출고비
                df_basic = add_basic_shipping(pd.DataFrame(), ven, d_from, d_to)
                items.extend(df_basic.to_dict("records"))

                # 구간별 택배요금 + 박스/봉투
                zone_counts = add_courier_fee_by_zone(ven, d_from, d_to, items)
                add_box_fee_by_zone(items, ven, zone_counts)

                # 합포장 / 도서산간 / 입고검수
                add_combined_pack_fee(df_ship, items)
                add_remote_area_fee(ven, d_from, d_to, items)
                add_inbound_inspection_fee(ven, d_from, d_to, items)

                # 플래그 기반 추가 항목
                add_barcode_fee(items, ven)
                add_void_fee(items, ven)
                add_ppbag_fee(items, ven)
                add_video_out_fee(items, ven)

                # 반품 관련
                add_return_pickup_fee(items, ven, d_from, d_to)
                add_return_courier_fee(ven, d_from, d_to, items)
                add_video_ret_fee(items, ven, d_from, d_to)

                # 작업일지 항목
                add_worklog_items(items, ven, d_from, d_to)

                iid = create_and_finalize_invoice(
                    vendor_id=int(vmap.get(ven)),
                    period_from=d_from,
                    period_to=d_to,
                    items=items,
                )
                logs.append({"공급처": ven, "결과": f"✅ #{iid}"})
            except Exception as e:
                logs.append({"공급처": ven, "결과": f"❌ 실패: {e}"})
            prog.setValue(i + 1)
            if prog.wasCanceled():
                break

        self.tbl_log.setModel(df_to_model(pd.DataFrame(logs)))
        self.tbl_log.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        QMessageBox.information(self, "완료", "인보이스 일괄 생성 완료")


