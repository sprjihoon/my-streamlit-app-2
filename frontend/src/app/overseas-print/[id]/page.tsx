'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  getOverseasShippingLabel,
  overseasLabelHtmlUrl,
  type OverseasLabelData,
} from '@/lib/api';

function parseApiError(err: unknown): string {
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message);
      if (typeof parsed?.detail === 'string') return parsed.detail;
    } catch {
      /* ignore */
    }
    return err.message;
  }
  return String(err);
}

export default function OverseasPrintPage() {
  const { id } = useParams<{ id: string }>();
  const [label, setLabel] = useState<OverseasLabelData | null>(null);
  const [htmlUrl, setHtmlUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    const shipmentId = Number(id);
    if (!token) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    if (!shipmentId) {
      setError('접수 번호가 없습니다.');
      setLoading(false);
      return;
    }
    setHtmlUrl(overseasLabelHtmlUrl(token, shipmentId));
    (async () => {
      try {
        const res = await getOverseasShippingLabel(token, shipmentId);
        setLabel(res.label);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const handlePrint = useCallback(() => window.print(), []);

  if (loading) {
    return <p style={{ padding: '2rem', textAlign: 'center' }}>출력서류를 불러오는 중...</p>;
  }
  if (error || !label) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p style={{ color: '#b91c1c' }}>{error || '출력서류를 찾을 수 없습니다.'}</p>
        <a href="/overseas-shipping-list">← 접수목록</a>
      </div>
    );
  }

  const { sender, recipient, items } = label;
  const totalQty = items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  const warn = label.status === 'canceled'
    ? '취소된 접수'
    : label.is_test || !label.ems_applied
      ? '테스트/임시 출력 — 우체국 실접수가 아닙니다'
      : '';

  return (
    <>
      <div className="no-print" style={{
        background: '#111827', color: '#fff', padding: '12px 20px',
        display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', position: 'sticky', top: 0, zIndex: 20,
      }}>
        <a href="/overseas-shipping-list" style={{ color: '#d1d5db', fontSize: 14 }}>← 접수목록</a>
        <span style={{ flex: 1, fontWeight: 600, fontSize: 14 }}>{label.order_no} · {label.service_label} 출력서류</span>
        {warn && <span style={{ color: '#fbbf24', fontSize: 12 }}>{warn}</span>}
        {htmlUrl && (
          <a href={htmlUrl} target="_blank" rel="noreferrer" style={{ color: '#d1d5db', fontSize: 13 }}>
            HTML 새 창
          </a>
        )}
        <button type="button" className="btn btn-primary" onClick={handlePrint}>인쇄</button>
      </div>

      <div style={{ background: '#f3f4f6', minHeight: '100vh', padding: 24 }} className="no-print-bg">
        <div style={{
          width: '210mm', minHeight: '297mm', margin: '0 auto', background: '#fff',
          fontFamily: 'Arial, sans-serif', fontSize: '11pt', boxShadow: '0 4px 24px rgba(0,0,0,.08)',
        }}>
          <div style={{ borderBottom: '3px solid #000', padding: '10px 14px', display: 'flex', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '22pt', fontWeight: 900, letterSpacing: 2 }}>{label.service_label}</div>
              <div style={{ fontSize: '9pt', color: '#555', marginTop: 2 }}>국제특급우편 / Priority Airmail</div>
            </div>
            <div style={{ textAlign: 'right', fontSize: '9pt', color: '#333' }}>
              <div>접수일: {(label.created_at || '').replace('T', ' ').slice(0, 10)}</div>
              <div>주문번호: {label.order_no}</div>
            </div>
          </div>

          <div style={{ padding: '10px 14px', textAlign: 'center', borderBottom: '1px solid #ddd' }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={label.barcode_url} alt={label.regino} style={{ height: 55, maxWidth: '100%' }} />
            <div style={{ fontSize: '13pt', fontWeight: 700, letterSpacing: 3, marginTop: 4, fontFamily: 'monospace' }}>
              {label.regino}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '2px solid #000' }}>
            <div style={{ padding: '10px 14px', borderRight: '1px solid #ccc' }}>
              <div style={{ fontSize: '9pt', fontWeight: 700, color: '#555', marginBottom: 5, borderBottom: '1px solid #ddd', paddingBottom: 3 }}>
                발송인 / From
              </div>
              <div style={{ fontSize: '10pt', fontWeight: 700 }}>{sender.name}</div>
              <div style={{ fontSize: '9pt', marginTop: 3, lineHeight: 1.5 }}>{sender.address}</div>
              <div style={{ fontSize: '9pt', marginTop: 3 }}>ZIP: {sender.zip}</div>
              <div style={{ fontSize: '9pt' }}>TEL: {sender.tel}</div>
              <div style={{ fontSize: '9pt' }}>KOREA ({sender.country})</div>
            </div>
            <div style={{ padding: '10px 14px' }}>
              <div style={{ fontSize: '9pt', fontWeight: 700, color: '#555', marginBottom: 5, borderBottom: '1px solid #ddd', paddingBottom: 3 }}>
                수취인 / To
              </div>
              <div style={{ fontSize: '12pt', fontWeight: 900 }}>{recipient.name}</div>
              <div style={{ fontSize: '9pt', marginTop: 4, lineHeight: 1.5 }}>
                {[recipient.addr3, recipient.addr2, recipient.addr1].filter(Boolean).join(', ')}
              </div>
              {recipient.zip && <div style={{ fontSize: '9pt', marginTop: 3 }}>ZIP: {recipient.zip}</div>}
              {recipient.phone && <div style={{ fontSize: '9pt' }}>TEL: {recipient.phone}</div>}
              {recipient.email && <div style={{ fontSize: '9pt' }}>EMAIL: {recipient.email}</div>}
              <div style={{ fontSize: '10pt', fontWeight: 700, marginTop: 6 }}>
                {recipient.country_name || recipient.country} ({recipient.country})
              </div>
            </div>
          </div>

          <div style={{ padding: '10px 14px 4px' }}>
            <div style={{ fontSize: '10pt', fontWeight: 700, borderBottom: '2px solid #000', paddingBottom: 4, marginBottom: 6 }}>
              세관신고서 / Customs Declaration (CN22)
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '9pt' }}>
              <thead>
                <tr style={{ background: '#f5f5f5' }}>
                  <th style={{ border: '1px solid #ccc', padding: '4px 6px', textAlign: 'left' }}>품목명 / Description</th>
                  <th style={{ border: '1px solid #ccc', padding: '4px 6px' }}>수량</th>
                  <th style={{ border: '1px solid #ccc', padding: '4px 6px' }}>단가 (USD)</th>
                  <th style={{ border: '1px solid #ccc', padding: '4px 6px' }}>총액 (USD)</th>
                  <th style={{ border: '1px solid #ccc', padding: '4px 6px' }}>HS Code</th>
                  <th style={{ border: '1px solid #ccc', padding: '4px 6px' }}>Origin</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={i}>
                    <td style={{ border: '1px solid #ccc', padding: '4px 6px' }}>{item.name_en}</td>
                    <td style={{ border: '1px solid #ccc', padding: '4px 6px', textAlign: 'center' }}>{item.quantity}</td>
                    <td style={{ border: '1px solid #ccc', padding: '4px 6px', textAlign: 'center' }}>{Number(item.unit_price_usd).toFixed(2)}</td>
                    <td style={{ border: '1px solid #ccc', padding: '4px 6px', textAlign: 'center' }}>
                      {(Number(item.unit_price_usd) * Number(item.quantity)).toFixed(2)}
                    </td>
                    <td style={{ border: '1px solid #ccc', padding: '4px 6px', textAlign: 'center' }}>{item.hs_code || '-'}</td>
                    <td style={{ border: '1px solid #ccc', padding: '4px 6px', textAlign: 'center' }}>{item.origin_country || 'KR'}</td>
                  </tr>
                ))}
                <tr style={{ background: '#f9f9f9', fontWeight: 700 }}>
                  <td style={{ border: '1px solid #ccc', padding: '5px 6px' }}>합계 / Total</td>
                  <td style={{ border: '1px solid #ccc', padding: '5px 6px', textAlign: 'center' }}>{totalQty}</td>
                  <td style={{ border: '1px solid #ccc', padding: '5px 6px' }} />
                  <td style={{ border: '1px solid #ccc', padding: '5px 6px', textAlign: 'center' }}>
                    USD {Number(label.customs_value_usd).toFixed(2)}
                  </td>
                  <td colSpan={2} style={{ border: '1px solid #ccc' }} />
                </tr>
              </tbody>
            </table>
          </div>

          <div style={{ margin: '10px 14px 0', borderTop: '1px solid #ddd', paddingTop: 10, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div style={{ fontSize: '9pt', color: '#555', marginBottom: 22 }}>발송인 서명 / Sender&apos;s Signature</div>
              <div style={{ borderBottom: '1px solid #000', height: 1 }} />
            </div>
            <div style={{ fontSize: '9pt', color: '#555' }}>
              <div>{label.ems_fee != null ? `예상 우편요금: ₩${Number(label.ems_fee).toLocaleString()}` : '우편요금 / Postage'}</div>
              <div style={{ marginTop: 4 }}>우편물 종류: {label.service_label}</div>
              <div style={{ marginTop: 4 }}>중량: {label.totweight}g · {label.boxlength}×{label.boxwidth}×{label.boxheight}cm</div>
              <div style={{ marginTop: 4 }}>내용품유형: Merchandise</div>
            </div>
          </div>
          <div style={{ margin: '10px 14px 14px', fontSize: '7.5pt', color: '#888', lineHeight: 1.4, borderTop: '1px solid #eee', paddingTop: 8 }}>
            이 우편물은 세관검사를 받을 수 있습니다. 발송인은 신고내용이 정확하고 사실임을 확인합니다.
            <br />
            This parcel may be opened by customs. The sender certifies that the particulars stated are correct and complete.
          </div>
        </div>
      </div>

      <style>{`
        @media print {
          .no-print { display: none !important; }
          .no-print-bg { background: none !important; padding: 0 !important; }
          .sidebar, .layout > aside, .main-content { margin: 0 !important; padding: 0 !important; }
          body { margin: 0; }
          @page { size: A4; margin: 8mm; }
        }
      `}</style>
    </>
  );
}
