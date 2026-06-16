from __future__ import annotations

import io
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import QTableView, QHeaderView, QAbstractItemView


def df_to_model(df: pd.DataFrame) -> QStandardItemModel:
    model = QStandardItemModel()
    model.setColumnCount(df.shape[1])
    model.setHorizontalHeaderLabels([str(c) for c in df.columns])
    for r in range(len(df)):
        row_items = []
        for c in df.columns:
            val = df.iat[r, df.columns.get_loc(c)]
            item = QStandardItem("" if pd.isna(val) else str(val))
            item.setEditable(True)
            row_items.append(item)
        model.appendRow(row_items)
    return model


def configure_table(
    table: QTableView,
    row_height: int = 36,
    resize_mode: QHeaderView.ResizeMode = QHeaderView.Stretch,
    sortable: bool = True,
) -> None:
    """테이블 공통 스타일 설정 헬퍼."""
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(sortable)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setFocusPolicy(Qt.StrongFocus)

    vh = table.verticalHeader()
    vh.setVisible(False)
    vh.setDefaultSectionSize(row_height)

    hh = table.horizontalHeader()
    hh.setHighlightSections(False)
    hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    hh.setSectionResizeMode(resize_mode)
    hh.setStretchLastSection(True)


def model_to_df(model: QStandardItemModel) -> pd.DataFrame:
    cols = [model.headerData(i, 1) for i in range(model.columnCount())]
    rows = []
    for r in range(model.rowCount()):
        rows.append([model.item(r, c).text() if model.item(r, c) else "" for c in range(model.columnCount())])
    return pd.DataFrame(rows, columns=cols)


def df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    return buf.getvalue()


