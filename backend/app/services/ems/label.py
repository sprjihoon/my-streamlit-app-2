"""해외배송 출력서류.

eship 계약 OpenAPI에는 라벨 PDF가 없다.
접수 저장본으로 우체국 A4 양식(주소기표지 1장, 세관신고서 2장)을 만든다.
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

_PREMIUM = {"EMS": "31", "EMS_PREMIUM": "32", "KPACKET": "14"}

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
    snap = snapshot or {}
    em_gubun = str(snap.get("EM_gubun") or "").split(";")[0].strip()
    contents_type = str(row.get("contents_type") or "").strip() or (
        "document" if (em_gubun.lower() == "document" or snap.get("em_ee") == "ee") else "parcel"
    )
    if not em_gubun:
        em_gubun = "Document" if contents_type == "document" else "Merchandise"
    contents_label = "서류" if contents_type == "document" else "화물"
    try:
        fee = int(float(fee_raw)) if fee_raw else None
    except ValueError:
        fee = None
    from backend.app.services.ems.dimension_limits import volumetric_weight_g
    from backend.app.services.ems.fields import hs_code_for_epost

    is_doc = contents_type == "document"
    hs_parts = str(snap.get("hs_code") or "").split(";") if snap.get("hs_code") else []
    wt_parts = str(snap.get("weight") or "").split(";") if snap.get("weight") else []
    for index, item in enumerate(items):
        posted = hs_parts[index].strip() if index < len(hs_parts) else ""
        item["print_hs"] = posted or hs_code_for_epost(item["hs_code"], document=is_doc)
        if index < len(wt_parts) and wt_parts[index].strip():
            item["net_weight_g"] = wt_parts[index].strip()
        elif len(items) == 1 and int(row.get("totweight") or 0):
            item["net_weight_g"] = str(int(row.get("totweight") or 0))
        else:
            item["net_weight_g"] = ""
    length = int(row.get("boxlength") or 0)
    width = int(row.get("boxwidth") or 0)
    height = int(row.get("boxheight") or 0)
    volume = None if is_doc else volumetric_weight_g(
        _PREMIUM.get(method, "31"), length, width, height
    )
    created = str(row.get("created_at") or "")
    stamp = created.replace("T", " ")
    date_bits = stamp[:10].split("-") if len(stamp) >= 10 else ["", "", ""]
    clock = stamp[11:16] if len(stamp) >= 16 else ""
    hour, minute = (clock.split(":") + ["", ""])[:2]
    return {
        "source": "internal",
        "id": row.get("id"),
        "order_no": order_no,
        "shipping_method": method,
        "service_label": SERVICE_LABEL.get(method, method),
        "contents_type": contents_type,
        "contents_label": contents_label,
        "contents_gubun": em_gubun,
        "regino": tracking or order_no,
        "ems_applied": bool(tracking) and not bool(row.get("is_test")),
        "is_test": bool(row.get("is_test")),
        "status": str(row.get("status") or ""),
        "ems_fee": fee,
        "ems_req_no": str(row.get("req_no") or "") or None,
        "ems_receive_seq": str(row.get("receive_seq") or "") or None,
        "post_office": str(row.get("post_office") or ""),
        "post_office_code": str(snap.get("treatporegipocd") or ""),
        "totweight": int(row.get("totweight") or 0),
        "volume_weight": volume,
        "boxlength": length,
        "boxwidth": width,
        "boxheight": height,
        "created_at": created,
        "posted_year": date_bits[0] if len(date_bits) == 3 else "",
        "posted_month": date_bits[1] if len(date_bits) == 3 else "",
        "posted_day": date_bits[2] if len(date_bits) == 3 else "",
        "posted_hour": hour,
        "posted_min": minute,
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


def _money(value: Any) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def _spaced_digits(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return " ".join(digits)


def _recipient_address(recipient: dict[str, Any]) -> str:
    parts = [recipient.get("addr3"), recipient.get("addr2"), recipient.get("addr1")]
    return ", ".join(str(part).strip() for part in parts if str(part or "").strip())


def _item_rows(items: list[dict[str, Any]]) -> str:
    rows = []
    shown = list(items[:4])
    while len(shown) < 3:
        shown.append({})
    for item in shown:
        name = item.get("name_en") or ""
        qty = item.get("quantity") or ""
        weight = item.get("net_weight_g") or ""
        price = _money(item["unit_price_usd"]) if item.get("unit_price_usd") not in (None, "") and name else ""
        hs = item.get("print_hs") or item.get("hs_code") or ""
        origin = item.get("origin_country") or ""
        rows.append(
            "<tr>"
            f"<td class='desc'>{_esc(name)}</td>"
            f"<td>{_esc(qty)}</td>"
            f"<td>{_esc(weight)}</td>"
            f"<td>{_esc(price)}</td>"
            f"<td>{_esc(hs)}</td>"
            f"<td>{_esc(origin)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _waybill(data: dict[str, Any], *, copy_title: str, with_guide: bool) -> str:
    sender = data["sender"]
    recipient = data["recipient"]
    fee = data.get("ems_fee")
    fee_text = f"{int(fee):,} 원" if fee is not None else ""
    volume = data.get("volume_weight")
    volume_text = f"{int(volume)} g" if volume else ""
    dims = ""
    if data.get("contents_type") != "document" and data.get("boxlength") and data.get("boxwidth") and data.get("boxheight"):
        dims = f"{int(data['boxlength'])} * {int(data['boxwidth'])} * {int(data['boxheight'])}"
    country = str(recipient.get("country") or "")
    code_boxes = "".join(f"<b class='cc'>{_esc(ch)}</b>" for ch in country[:2])
    goods = "v" if data.get("contents_type") != "document" else ""
    guide = ""
    if with_guide:
        guide = """
    <section class="guide">
      <h2>EMS 주소기표지 작성 요령</h2>
      <p>주소기표지가 정확히 작성되지 않으면 도착국가 통관이 지연될 수 있습니다. 서류·인쇄물은 EE, ED로 시작하고 상품·선물은 EM, EG로 시작합니다.</p>
      <p>1) 보내는 사람 / 받는 사람: 주소와 성명은 영문이고, 전화번호는 반드시 적습니다.</p>
      <p>2) 세관신고서(CN23): 내용품명(영문)과 가격을 정확히 적습니다. 상품송장은 우편물 외부 비닐봉투에 붙이거나 안에서 바로 보이게 둡니다.</p>
      <p>3) 손해배상은 서류 60,360원, 상품은 80,480원에 1kg당 9,054원을 더한 범위의 실손해액과 납부한 국제특급요금이 한도입니다. 보험에 가입해야 실제손해액을 배상받습니다. (보험한도액 8,048,000원)</p>
      <p class="warn">주의 : 보험에 가입하셔야 실제손해액을 배상받습니다. (보험한도액: 8,048,000원)</p>
    </section>"""
    title = f"<div class='copy-title'>{_esc(copy_title)}</div>" if copy_title else "<div class='copy-title'></div>"
    return f"""
  <article class="sheet">
    {title}
    <header class="top">
      <div class="brand">
        <div class="post">우체국<br><span>전화 1588-1300<br>KOREA POST</span></div>
        <div>
          <div class="itemno">Item No. 우편물 번호</div>
          <div class="regino">{_esc(data.get('regino') or '')}</div>
          <img src="{_esc(data.get('barcode_url') or '')}" alt="{_esc(data.get('regino') or '')}" />
        </div>
      </div>
      <div class="ems-head">
        <div class="ems-logo">EMS <span>우체국 국제특송</span></div>
        <table class="when">
          <tr><th colspan="4">Date &amp; Time Posted 접수년월일시</th><th>Post office code<br>우편용국기호</th></tr>
          <tr><td>Year</td><td>Month</td><td>Day</td><td>Hour Min</td><td rowspan="2">{_esc(data.get('post_office') or '')}</td></tr>
          <tr>
            <td>{_esc(data.get('posted_year') or '')}</td>
            <td>{_esc(data.get('posted_month') or '')}</td>
            <td>{_esc(data.get('posted_day') or '')}</td>
            <td>{_esc(data.get('posted_hour') or '')}:{_esc(data.get('posted_min') or '')}</td>
          </tr>
        </table>
      </div>
    </header>
    <table class="parties">
      <tr>
        <th rowspan="4" class="side">From<br>보내는<br>사람</th>
        <td class="half">Tel. No. {_esc(sender.get('tel') or '')}</td>
        <th rowspan="4" class="side">To<br>받는<br>사람</th>
        <td class="half">Tel. No. {_esc(recipient.get('phone') or '')}</td>
      </tr>
      <tr>
        <td>Name <b>{_esc(sender.get('name') or '')}</b></td>
        <td>Name <b>{_esc(recipient.get('name') or '')}</b></td>
      </tr>
      <tr>
        <td class="addr">Address<br>{_esc(sender.get('address') or '')}</td>
        <td class="addr">Address<br>{_esc(_recipient_address(recipient))}</td>
      </tr>
      <tr>
        <td>e-mail<br><span class="zip">{_esc(_spaced_digits(sender.get('zip') or ''))} &nbsp; Rep. of KOREA</span></td>
        <td>e-mail {_esc(recipient.get('email') or '')}<br>
          <span class="zip">Postal code {_esc(recipient.get('zip') or '')} &nbsp; Country {_esc(recipient.get('country_name') or country)}</span>
        </td>
      </tr>
    </table>
    <div class="customs-wrap">
      <table class="customs">
        <tr><th colspan="6">Customs Declaration 세관신고서 CN23</th></tr>
        <tr>
          <th>Contents 내용품명</th>
          <th>Quantity<br>개수</th>
          <th>Net Weight<br>순중량</th>
          <th>Value<br>가격 US$</th>
          <th>HS Tariff<br>Number</th>
          <th>Country of<br>Origin</th>
        </tr>
        {_item_rows(data.get('items') or [])}
      </table>
      <table class="sidebox">
        <tr><th>Actual Weight 실제중량</th><td class="num">{int(data.get('totweight') or 0)} g</td></tr>
        <tr><th>Postage 우편요금</th><td class="num">{_esc(fee_text)}</td></tr>
        <tr><th>Volume Weight 부피중량</th><td class="num">{_esc(volume_text)}</td></tr>
        <tr><th>가로*세로*높이(cm)</th><td class="num">{_esc(dims)}</td></tr>
        <tr><th>Country code 도착국명 약호</th><td class="codes">{code_boxes}</td></tr>
      </table>
    </div>
    <table class="checks">
      <tr>
        <td>Sample 상품견본 ☐ &nbsp; Gift 선물 ☐ &nbsp; Merchandise 상품 {'☑' if goods else '☐'} &nbsp; 수출면장건 ☐</td>
        <td>요금납부방법 및 기타<br>현금수납 ☐ &nbsp; 요금후납 ☑</td>
        <td>Signature 담당자서명<br><b>{_esc(data.get('post_office') or '')}</b></td>
      </tr>
      <tr>
        <td>Signature 발송인 서명<br><b>{_esc(sender.get('name') or '')}</b></td>
        <td>보험이용여부 (Shipping insurance)<br>YES ☐ &nbsp; NO ☑</td>
        <td>보험가액(Insurance value)</td>
      </tr>
    </table>
    <p class="note">세관신고서와 보험이용여부, 받는 사람 전화번호는 빠짐없이 기재해야 합니다. 행방조회 http://www.epost.kr</p>
    {guide}
  </article>"""


def render_label_html(data: dict[str, Any]) -> str:
    warn = ""
    if data.get("status") == "canceled":
        warn = '<span class="badge">취소된 접수</span>'
    elif data.get("is_test") or not data.get("ems_applied"):
        warn = '<span class="badge">테스트/임시 출력 — 우체국 실접수가 아닙니다</span>'
    pages = _waybill(data, copy_title="", with_guide=True)
    pages += _waybill(data, copy_title="1. CUSTOMS DECLARATION - 세관신고서(뜯지 말것)", with_guide=False)
    pages += _waybill(data, copy_title="2. CUSTOMS DECLARATION - 세관신고서(뜯지 말것)", with_guide=False)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>{_esc(data.get('order_no') or '')} 출력서류</title>
  <style>
    @page {{ size: A4; margin: 8mm; }}
    @media print {{ body {{ margin: 0; background: #fff; }} .no-print {{ display: none !important; }} .sheet {{ box-shadow: none; margin: 0; }} }}
    body {{ margin: 0; background: #e5e7eb; color: #111; font-family: Arial, "Malgun Gothic", sans-serif; font-size: 9pt; }}
    .no-print {{ background: #111827; color: #fff; padding: 12px 20px; display: flex; gap: 12px; align-items: center; }}
    .no-print button {{ background: #2563eb; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 700; }}
    .badge {{ color: #fbbf24; font-size: 12px; }}
    .sheet {{ width: 194mm; min-height: 277mm; margin: 12px auto; background: #fff; padding: 6mm; box-shadow: 0 4px 18px rgba(0,0,0,.08); page-break-after: always; }}
    .copy-title {{ font-weight: 700; min-height: 16px; }}
    .top {{ display: flex; justify-content: space-between; gap: 8px; border-bottom: 2px solid #111; padding-bottom: 6px; }}
    .brand {{ display: flex; gap: 8px; align-items: flex-start; }}
    .post {{ border: 1px solid #111; padding: 4px 6px; font-weight: 800; line-height: 1.2; }}
    .post span {{ font-weight: 500; font-size: 7.5pt; }}
    .itemno {{ font-size: 7.5pt; color: #444; }}
    .regino {{ font-size: 14pt; font-weight: 800; letter-spacing: 1px; }}
    .brand img {{ height: 42px; }}
    .ems-logo {{ font-size: 22pt; font-weight: 900; color: #f59e0b; letter-spacing: 1px; }}
    .ems-logo span {{ color: #1d4ed8; font-size: 13pt; }}
    table {{ width: 100%; border-collapse: collapse; }}
    .when, .parties, .customs, .checks, .sidebox {{ margin-top: 6px; }}
    .customs-wrap {{ display: flex; gap: 6px; align-items: flex-start; }}
    .customs-wrap .customs {{ flex: 1; }}
    .sidebox {{ width: 42mm; }}
    .when td, .when th, .parties td, .parties th, .customs td, .customs th, .checks td {{ border: 1px solid #111; padding: 3px 4px; vertical-align: top; font-size: 8pt; }}
    .side {{ width: 28px; text-align: center; font-weight: 800; }}
    .addr {{ height: 42px; }}
    .zip {{ font-weight: 700; }}
    .customs td {{ height: 18px; text-align: center; }}
    .customs .desc {{ text-align: left; font-weight: 700; }}
    .num {{ font-weight: 800; text-align: center; }}
    .cc {{ display: inline-block; border: 1px solid #111; min-width: 18px; text-align: center; margin-right: 4px; font-size: 14pt; }}
    .note {{ font-size: 7.5pt; margin: 6px 0; }}
    .guide {{ border-top: 1px dashed #111; padding-top: 6px; font-size: 7.5pt; line-height: 1.35; }}
    .guide h2 {{ text-align: center; font-size: 11pt; margin: 4px 0; }}
    .warn {{ text-align: center; font-weight: 800; }}
  </style>
</head>
<body>
  <div class="no-print">
    <span style="flex:1;font-weight:700">{_esc(data.get('order_no') or '')} · {_esc(data.get('service_label') or '')} · 1장 주소기표지(부착) · 2·3장 세관신고서</span>
    {warn}
    <button type="button" onclick="window.print()">인쇄</button>
  </div>
  {pages}
</body>
</html>"""
