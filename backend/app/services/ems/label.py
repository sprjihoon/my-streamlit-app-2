"""해외배송 출력서류(CN22 라벨).

eship 계약 OpenAPI에는 라벨 PDF 전용 API가 없다.
접수 저장본 + apply_snapshot 으로 CN22 HTML/JSON 을 만든다.
Infront apps/admin/lib/ems/label.ts 와 동일 계약.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from backend.app.services.ems.fields import FALLBACK_NATIONS, format_sender_tel, resolve_sender

SERVICE_LABEL = {
    "EMS": "EMS",
    "EMS_PREMIUM": "EMS PREMIUM",
    "KPACKET": "K-PACKET",
}

NATION_FN = {n["nationcd"]: n["nationfn"] for n in FALLBACK_NATIONS}


def barcode_url(text: str) -> str:
    value = (text or "").strip() or "NO-TRACKING"
    return (
        "https://quickchart.io/barcode"
        f"?type=code128&text={quote(value)}"
        "&height=60&width=300&includetext=true&textxalign=center"
    )


def _esc(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _fmt_date(iso: str) -> str:
    raw = (iso or "").replace("T", " ")
    return raw[:10] if len(raw) >= 10 else raw


def _sender_from_snapshot(snapshot: dict[str, Any] | None, fallback_name: str) -> dict[str, str]:
    snap = snapshot or {}
    default = resolve_sender()
    tel = {
        "tel1": str(snap.get("sendertelno1") or default["tel1"]),
        "tel2": str(snap.get("sendertelno2") or default["tel2"]),
        "tel3": str(snap.get("sendertelno3") or default["tel3"]),
        "tel4": str(snap.get("sendertelno4") or default["tel4"]),
    }
    addr_parts = [
        str(snap.get("senderaddr1") or default["addr1"]).strip(),
        str(snap.get("senderaddr2") or default["addr2"]).strip(),
        str(snap.get("senderaddr3") or default["addr3"]).strip(),
    ]
    return {
        "name": str(snap.get("sender") or fallback_name or default["name"]).strip(),
        "address": ", ".join(p for p in addr_parts if p),
        "zip": str(snap.get("senderzipcode") or default["zipcode"]).strip(),
        "tel": format_sender_tel(tel) or f"+{tel['tel1']}-{tel['tel2']}-{tel['tel3']}-{tel['tel4']}",
        "country": "KR",
    }


def _label_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        qty = int(row.get("quantity") or 1)
        price = float(row.get("unit_price_usd") or 0)
        items.append(
            {
                "name_en": str(row.get("name_en") or "").strip(),
                "quantity": qty,
                "unit_price_usd": price,
                "hs_code": str(row.get("hs_code") or "").strip(),
                "origin_country": str(row.get("origin_country") or "KR").strip() or "KR",
            }
        )
    return items


def build_shipment_label(
    row: dict[str, Any],
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    method = str(row.get("shipping_method") or "EMS")
    items = _label_items(row.get("items") or [])
    customs = round(sum(i["unit_price_usd"] * i["quantity"] for i in items), 2)
    tracking = str(row.get("tracking_no") or "").strip()
    order_no = str(row.get("order_no") or "")
    countrycd = str(row.get("countrycd") or "").upper()
    fee_raw = str(row.get("ems_fee") or "").strip()
    try:
        fee = int(float(fee_raw)) if fee_raw else None
    except ValueError:
        fee = None
    return {
        "source": "internal",
        "id": row.get("id"),
        "order_no": order_no,
        "shipping_method": method,
        "service_label": SERVICE_LABEL.get(method, method),
        "regino": tracking or order_no,
        "ems_applied": bool(tracking) and not bool(row.get("is_test")),
        "is_test": bool(row.get("is_test")),
        "status": str(row.get("status") or ""),
        "ems_fee": fee,
        "ems_req_no": str(row.get("req_no") or "") or None,
        "ems_receive_seq": str(row.get("receive_seq") or "") or None,
        "post_office": str(row.get("post_office") or ""),
        "totweight": int(row.get("totweight") or 0),
        "boxlength": int(row.get("boxlength") or 0),
        "boxwidth": int(row.get("boxwidth") or 0),
        "boxheight": int(row.get("boxheight") or 0),
        "created_at": str(row.get("created_at") or ""),
        "sender": _sender_from_snapshot(snapshot, str(row.get("sender_name") or "")),
        "recipient": {
            "name": str(row.get("recipient_name") or ""),
            "addr1": str(row.get("recipient_addr1") or ""),
            "addr2": str(row.get("recipient_addr2") or ""),
            "addr3": str(row.get("recipient_addr3") or ""),
            "zip": str(row.get("recipient_zip") or ""),
            "phone": str(row.get("recipient_phone") or ""),
            "email": str(row.get("recipient_email") or ""),
            "country": countrycd,
            "country_name": NATION_FN.get(countrycd, countrycd),
        },
        "items": items,
        "customs_value_usd": customs,
        "barcode_url": barcode_url(tracking or order_no),
    }


def render_label_html(data: dict[str, Any]) -> str:
    sender = data["sender"]
    recipient = data["recipient"]
    items = data["items"]
    total_qty = sum(int(i["quantity"]) for i in items)
    item_rows = "".join(
        f"""
      <tr>
        <td style="border:1px solid #ccc;padding:4px 6px">{_esc(item['name_en'])}</td>
        <td style="border:1px solid #ccc;padding:4px 6px;text-align:center">{int(item['quantity'])}</td>
        <td style="border:1px solid #ccc;padding:4px 6px;text-align:center">{float(item['unit_price_usd']):.2f}</td>
        <td style="border:1px solid #ccc;padding:4px 6px;text-align:center">{float(item['unit_price_usd']) * int(item['quantity']):.2f}</td>
        <td style="border:1px solid #ccc;padding:4px 6px;text-align:center;font-size:8pt">{_esc(item.get('hs_code') or '-')}</td>
        <td style="border:1px solid #ccc;padding:4px 6px;text-align:center">{_esc(item.get('origin_country') or 'KR')}</td>
      </tr>"""
        for item in items
    )
    addr_parts = [recipient.get("addr3"), recipient.get("addr2"), recipient.get("addr1")]
    recipient_addr = "<br />".join(_esc(p) for p in addr_parts if p)
    warn = ""
    if data.get("status") == "canceled":
        warn = '<span style="color:#fca5a5;font-size:12px">취소된 접수</span>'
    elif data.get("is_test") or not data.get("ems_applied"):
        warn = '<span style="color:#fbbf24;font-size:12px">테스트/임시 출력 — 우체국 실접수가 아닙니다</span>'
    fee = data.get("ems_fee")
    fee_html = f"예상 우편요금: ₩{int(fee):,}" if fee is not None else "우편요금 / Postage"
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>{_esc(data['order_no'])} 출력서류</title>
  <style>
    @page {{ size: A4; margin: 8mm; }}
    @media print {{ body {{ margin: 0; }} .no-print {{ display: none !important; }} }}
    body {{ font-family: Arial, sans-serif; font-size: 11pt; margin: 0; background: #f3f4f6; }}
    .sheet {{ width: 210mm; min-height: 297mm; margin: 16px auto; background: #fff; box-shadow: 0 4px 24px rgba(0,0,0,.08); }}
  </style>
</head>
<body>
  <div class="no-print" style="background:#111827;color:#fff;padding:12px 20px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
    <span style="flex:1;font-weight:600">{_esc(data['order_no'])} · {_esc(data['service_label'])} 출력서류</span>
    {warn}
    <button onclick="window.print()" style="background:#2563eb;color:#fff;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:600">인쇄</button>
  </div>
  <div class="sheet">
    <div style="border-bottom:3px solid #000;padding:10px 14px;display:flex;justify-content:space-between;align-items:center">
      <div>
        <div style="font-size:22pt;font-weight:900;letter-spacing:2px">{_esc(data['service_label'])}</div>
        <div style="font-size:9pt;color:#555;margin-top:2px">국제특급우편 / Priority Airmail</div>
      </div>
      <div style="text-align:right;font-size:9pt;color:#333">
        <div>접수일: {_esc(_fmt_date(data.get('created_at') or ''))}</div>
        <div>주문번호: {_esc(data['order_no'])}</div>
      </div>
    </div>
    <div style="padding:10px 14px;text-align:center;border-bottom:1px solid #ddd">
      <img src="{_esc(data['barcode_url'])}" alt="{_esc(data['regino'])}" style="height:55px;max-width:100%" />
      <div style="font-size:13pt;font-weight:700;letter-spacing:3px;margin-top:4px;font-family:monospace">{_esc(data['regino'])}</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:2px solid #000">
      <div style="padding:10px 14px;border-right:1px solid #ccc">
        <div style="font-size:9pt;font-weight:700;color:#555;margin-bottom:5px;text-transform:uppercase;border-bottom:1px solid #ddd;padding-bottom:3px">발송인 / From</div>
        <div style="font-size:10pt;font-weight:700">{_esc(sender['name'])}</div>
        <div style="font-size:9pt;margin-top:3px;line-height:1.5;color:#333">{_esc(sender['address'])}</div>
        <div style="font-size:9pt;margin-top:3px;color:#333">ZIP: {_esc(sender['zip'])}</div>
        <div style="font-size:9pt;color:#333">TEL: {_esc(sender['tel'])}</div>
        <div style="font-size:9pt;color:#333">KOREA ({_esc(sender['country'])})</div>
      </div>
      <div style="padding:10px 14px">
        <div style="font-size:9pt;font-weight:700;color:#555;margin-bottom:5px;text-transform:uppercase;border-bottom:1px solid #ddd;padding-bottom:3px">수취인 / To</div>
        <div style="font-size:12pt;font-weight:900">{_esc(recipient['name'])}</div>
        <div style="font-size:9pt;margin-top:4px;line-height:1.5;color:#000">{recipient_addr}</div>
        {f'<div style="font-size:9pt;margin-top:3px;color:#333">ZIP: {_esc(recipient["zip"])}</div>' if recipient.get("zip") else ""}
        {f'<div style="font-size:9pt;color:#333">TEL: {_esc(recipient["phone"])}</div>' if recipient.get("phone") else ""}
        {f'<div style="font-size:9pt;color:#333">EMAIL: {_esc(recipient["email"])}</div>' if recipient.get("email") else ""}
        <div style="font-size:10pt;font-weight:700;margin-top:6px;color:#000">{_esc(recipient.get("country_name") or recipient["country"])} ({_esc(recipient["country"])})</div>
      </div>
    </div>
    <div style="padding:10px 14px 4px">
      <div style="font-size:10pt;font-weight:700;border-bottom:2px solid #000;padding-bottom:4px;margin-bottom:6px;text-transform:uppercase">
        세관신고서 / Customs Declaration (CN22)
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:9pt">
        <thead>
          <tr style="background:#f5f5f5">
            <th style="border:1px solid #ccc;padding:4px 6px;text-align:left;width:35%">품목명 / Description</th>
            <th style="border:1px solid #ccc;padding:4px 6px;text-align:center;width:10%">수량</th>
            <th style="border:1px solid #ccc;padding:4px 6px;text-align:center;width:15%">단가 (USD)</th>
            <th style="border:1px solid #ccc;padding:4px 6px;text-align:center;width:15%">총액 (USD)</th>
            <th style="border:1px solid #ccc;padding:4px 6px;text-align:center;width:13%">HS Code</th>
            <th style="border:1px solid #ccc;padding:4px 6px;text-align:center;width:12%">Origin</th>
          </tr>
        </thead>
        <tbody>
          {item_rows}
          <tr style="background:#f9f9f9;font-weight:700">
            <td style="border:1px solid #ccc;padding:5px 6px">합계 / Total</td>
            <td style="border:1px solid #ccc;padding:5px 6px;text-align:center">{total_qty}</td>
            <td style="border:1px solid #ccc;padding:5px 6px"></td>
            <td style="border:1px solid #ccc;padding:5px 6px;text-align:center">USD {float(data['customs_value_usd']):.2f}</td>
            <td colspan="2" style="border:1px solid #ccc"></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div style="margin:10px 14px 0;border-top:1px solid #ddd;padding-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div>
        <div style="font-size:9pt;color:#555;margin-bottom:22px">발송인 서명 / Sender's Signature</div>
        <div style="border-bottom:1px solid #000;height:1px"></div>
      </div>
      <div style="font-size:9pt;color:#555">
        <div>{_esc(fee_html)}</div>
        <div style="margin-top:4px">우편물 종류: {_esc(data['service_label'])}</div>
        <div style="margin-top:4px">중량: {int(data.get('totweight') or 0)}g · {int(data.get('boxlength') or 0)}×{int(data.get('boxwidth') or 0)}×{int(data.get('boxheight') or 0)}cm</div>
        <div style="margin-top:4px">내용품유형: Merchandise</div>
      </div>
    </div>
    <div style="margin:10px 14px 14px;font-size:7.5pt;color:#888;line-height:1.4;border-top:1px solid #eee;padding-top:8px">
      이 우편물은 세관검사를 받을 수 있습니다. 발송인은 신고내용이 정확하고 사실임을 확인합니다.<br />
      This parcel may be opened by customs. The sender certifies that the particulars stated are correct and complete.
    </div>
  </div>
</body>
</html>"""
