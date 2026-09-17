'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  createOverseasShipping,
  getOverseasShippingMeta,
  listOverseasNations,
  previewOverseasShipping,
  type OverseasInvoiceItem,
  type OverseasShippingPayload,
} from '@/lib/api';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
};

function parseApiError(err: unknown): string {
  if (err instanceof Error) {
    const msg = err.message;
    try {
      const parsed = JSON.parse(msg);
      if (typeof parsed?.detail === 'string') return parsed.detail;
    } catch {
      /* ignore */
    }
    return msg;
  }
  return String(err);
}

function newItem(): OverseasInvoiceItem {
  return { name_en: 'Clothing', quantity: 1, unit_price_usd: 20, hs_code: '', origin_country: 'KR' };
}

function emptyForm(): OverseasShippingPayload {
  return {
    shipping_method: 'EMS',
    countrycd: 'JP',
    receivename: '',
    receivetelno: '',
    receivemail: '',
    receivezipcode: '',
    receiveaddr1: '',
    receiveaddr2: '',
    receiveaddr3: '',
    totweight: 500,
    boxlength: 30,
    boxwidth: 25,
    boxheight: 15,
    items: [newItem()],
    notes: '',
    test_mode: false,
  };
}

const METHOD_PREMIUM: Record<OverseasShippingPayload['shipping_method'], string> = {
  EMS: '31',
  EMS_PREMIUM: '32',
  KPACKET: '14',
};

export default function OverseasShippingPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [liveReady, setLiveReady] = useState(false);
  const [senderLabel, setSenderLabel] = useState('스프링풀필먼트');
  const [methods, setMethods] = useState<Array<{ code: string; name: string; desc: string }>>([]);
  const [nations, setNations] = useState<Array<{ nationcd: string; nationnm: string; nationfn: string }>>([]);
  const [form, setForm] = useState<OverseasShippingPayload>(emptyForm());

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const meta = await getOverseasShippingMeta(stored);
        setLiveReady(meta.live_ready);
        setMethods(meta.methods || []);
        setSenderLabel(`${meta.sender.name} · ${meta.sender.addr}`);
        const nationRes = await listOverseasNations(stored, '31');
        setNations(nationRes.items || []);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function changeMethod(code: OverseasShippingPayload['shipping_method']) {
    setForm((prev) => ({ ...prev, shipping_method: code }));
    if (!token) return;
    try {
      const nationRes = await listOverseasNations(token, METHOD_PREMIUM[code]);
      setNations(nationRes.items || []);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  function updateItem(index: number, patch: Partial<OverseasInvoiceItem>) {
    setForm((prev) => ({
      ...prev,
      items: prev.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    }));
  }

  async function handleSubmit() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const previewRes = await previewOverseasShipping(token, form);
      const p = previewRes.preview;
      const feeText = p.expected_fee != null ? `${p.expected_fee.toLocaleString()}원` : '조회 실패(접수는 가능)';
      const mode = liveReady && !form.test_mode ? '실접수' : '테스트 접수';
      const ok = window.confirm(
        `${mode} 할까요?\n\n` +
          `배송: ${p.shipping_method_name} / ${p.countrycd}\n` +
          `수취인: ${p.recipient_name}\n` +
          `주소: ${p.recipient_addr}\n` +
          `무게: ${p.totweight}g · ${p.boxlength}×${p.boxwidth}×${p.boxheight}cm\n` +
          `예상요금: ${feeText}\n\n결제 없이 우체국에 바로 접수됩니다.`,
      );
      if (!ok) return;
      const result = await createOverseasShipping(token, form);
      if (result.duplicate_guard) {
        setSuccess(`오늘 같은 수취인으로 이미 접수된 건이 있습니다. 등기번호 ${result.tracking_no}`);
      } else {
        const label = result.is_test ? '테스트 접수' : '우체국 접수';
        setSuccess(`${label} 완료. 등기번호 ${result.tracking_no}${result.ems_fee ? ` · 요금 ${Number(result.ems_fee).toLocaleString()}원` : ''}`);
        setForm(emptyForm());
      }
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading text="해외배송 접수 로딩 중..." />;

  return (
    <div>
      <PageHeader
        title="해외배송 접수"
        subtitle="창고에서 EMS / EMS 프리미엄 / K-Packet를 결제 없이 바로 접수합니다."
      />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title="접수 정보">
        <p className="text-muted" style={{ marginBottom: '1rem' }}>
          {liveReady
            ? `실접수 가능 · 발송인 ${senderLabel}`
            : `EMS 키가 없어 테스트 접수로 저장됩니다. 발송인 ${senderLabel}`}
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <label>
            배송방법
            <select
              style={inputStyle}
              value={form.shipping_method}
              onChange={(e) => changeMethod(e.target.value as OverseasShippingPayload['shipping_method'])}
            >
              {(methods.length ? methods : [
                { code: 'EMS', name: 'EMS', desc: '' },
                { code: 'EMS_PREMIUM', name: 'EMS 프리미엄', desc: '' },
                { code: 'KPACKET', name: 'K-Packet', desc: '' },
              ]).map((m) => (
                <option key={m.code} value={m.code}>
                  {m.name}{m.desc ? ` · ${m.desc}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label>
            국가
            <select
              style={inputStyle}
              value={form.countrycd}
              onChange={(e) => setForm((p) => ({ ...p, countrycd: e.target.value }))}
            >
              {nations.map((n) => (
                <option key={n.nationcd} value={n.nationcd}>
                  {n.nationnm || n.nationfn || n.nationcd} ({n.nationcd})
                </option>
              ))}
            </select>
          </label>
          <label>
            수취인 이름 (영문)
            <input
              style={inputStyle}
              value={form.receivename}
              placeholder="Hong Gildong"
              onChange={(e) => setForm((p) => ({ ...p, receivename: e.target.value }))}
            />
          </label>
          <label>
            연락처
            <input
              style={inputStyle}
              value={form.receivetelno}
              placeholder="+819012345678"
              onChange={(e) => setForm((p) => ({ ...p, receivetelno: e.target.value }))}
            />
          </label>
          <label>
            이메일
            <input
              style={inputStyle}
              value={form.receivemail}
              onChange={(e) => setForm((p) => ({ ...p, receivemail: e.target.value }))}
            />
          </label>
          <label>
            우편번호
            <input
              style={inputStyle}
              value={form.receivezipcode}
              onChange={(e) => setForm((p) => ({ ...p, receivezipcode: e.target.value }))}
            />
          </label>
          <label>
            주/도 (영문)
            <input
              style={inputStyle}
              value={form.receiveaddr1}
              placeholder="Tokyo"
              onChange={(e) => setForm((p) => ({ ...p, receiveaddr1: e.target.value }))}
            />
          </label>
          <label>
            시/군 (영문)
            <input
              style={inputStyle}
              value={form.receiveaddr2}
              placeholder="Shibuya-ku"
              onChange={(e) => setForm((p) => ({ ...p, receiveaddr2: e.target.value }))}
            />
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            상세주소 (영문)
            <input
              style={inputStyle}
              value={form.receiveaddr3}
              placeholder="1-2-3 Example Street Apt 101"
              onChange={(e) => setForm((p) => ({ ...p, receiveaddr3: e.target.value }))}
            />
          </label>
          <label>
            총중량 (g)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.totweight}
              onChange={(e) => setForm((p) => ({ ...p, totweight: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
          <label>
            가로 (cm)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.boxlength}
              onChange={(e) => setForm((p) => ({ ...p, boxlength: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
          <label>
            세로 (cm)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.boxwidth}
              onChange={(e) => setForm((p) => ({ ...p, boxwidth: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
          <label>
            높이 (cm)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.boxheight}
              onChange={(e) => setForm((p) => ({ ...p, boxheight: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            메모
            <input
              style={inputStyle}
              value={form.notes}
              onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
            />
          </label>
        </div>
      </Card>

      <Card title="세관 인보이스">
        {form.items.map((item, i) => (
          <div
            key={i}
            style={{ display: 'grid', gridTemplateColumns: '2fr 80px 110px 120px 80px auto', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'end' }}
          >
            <label>
              품명 (영문)
              <input style={inputStyle} value={item.name_en} onChange={(e) => updateItem(i, { name_en: e.target.value })} />
            </label>
            <label>
              수량
              <input
                type="number"
                min={1}
                style={inputStyle}
                value={item.quantity}
                onChange={(e) => updateItem(i, { quantity: parseInt(e.target.value, 10) || 1 })}
              />
            </label>
            <label>
              단가 USD
              <input
                type="number"
                min={0.01}
                step="0.01"
                style={inputStyle}
                value={item.unit_price_usd}
                onChange={(e) => updateItem(i, { unit_price_usd: parseFloat(e.target.value) || 0 })}
              />
            </label>
            <label>
              HS코드
              <input style={inputStyle} value={item.hs_code || ''} onChange={(e) => updateItem(i, { hs_code: e.target.value })} />
            </label>
            <label>
              원산지
              <input style={inputStyle} value={item.origin_country || 'KR'} onChange={(e) => updateItem(i, { origin_country: e.target.value })} />
            </label>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={form.items.length <= 1}
              onClick={() => setForm((p) => ({ ...p, items: p.items.filter((_, idx) => idx !== i) }))}
            >
              삭제
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-secondary" onClick={() => setForm((p) => ({ ...p, items: [...p.items, newItem()] }))}>
          품목 추가
        </button>
      </Card>

      <Card title="접수">
        {liveReady && (
          <label style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={!!form.test_mode}
              onChange={(e) => setForm((p) => ({ ...p, test_mode: e.target.checked }))}
            />
            테스트 접수 (우체국에 실제 신청하지 않음)
          </label>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
            {saving ? '접수 중...' : liveReady && !form.test_mode ? '해외배송 접수' : '테스트 접수'}
          </button>
          <a href="/overseas-shipping-list" className="btn btn-secondary">접수목록</a>
        </div>
      </Card>
    </div>
  );
}
