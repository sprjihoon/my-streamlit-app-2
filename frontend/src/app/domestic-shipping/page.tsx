'use client';

import { useEffect, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  createDomesticShipping,
  getDomesticMeta,
  listDomesticVendors,
  previewDomesticShipping,
  type DomesticBoxSize,
  type DomesticPreview,
  type DomesticSubmitPayload,
  type DomesticVendor,
} from '@/lib/api';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: 8,
  fontFamily: 'inherit',
};

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

function emptyForm(): DomesticSubmitPayload {
  return {
    vendor_id: 0,
    print_sender_name: '',
    print_sender_phone: '',
    print_sender_zip: '',
    print_sender_addr1: '',
    print_sender_addr2: '',
    recipient_name: '',
    recipient_phone: '',
    recipient_zip: '',
    recipient_addr1: '',
    recipient_addr2: '',
    goods_name: '의류',
    box_size: 'SMALL',
    notes: '',
    test_mode: false,
  };
}

export default function DomesticShippingPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveReady, setLiveReady] = useState(false);
  const [vendors, setVendors] = useState<DomesticVendor[]>([]);
  const [boxSizes, setBoxSizes] = useState<DomesticBoxSize[]>([]);
  const [form, setForm] = useState<DomesticSubmitPayload>(emptyForm());
  const [preview, setPreview] = useState<DomesticPreview | null>(null);

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
        const [meta, vendorRes] = await Promise.all([
          getDomesticMeta(stored),
          listDomesticVendors(stored),
        ]);
        setLiveReady(meta.live_ready);
        setBoxSizes(meta.box_sizes || []);
        setVendors(vendorRes.items || []);
        setForm((prev) => ({ ...prev, test_mode: !meta.live_ready }));
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function applyVendor(id: number) {
    const vendor = vendors.find((item) => item.id === id);
    setPreview(null);
    setForm((prev) => ({
      ...prev,
      vendor_id: id,
      print_sender_name: vendor?.sender_name || '',
      print_sender_phone: vendor?.sender_phone || '',
      print_sender_zip: vendor?.sender_zip || '',
      print_sender_addr1: vendor?.sender_addr1 || '',
      print_sender_addr2: vendor?.sender_addr2 || '',
    }));
  }

  function setField(key: keyof DomesticSubmitPayload, value: string) {
    setPreview(null);
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handlePreview() {
    setSaving(true);
    setError(null);
    try {
      const res = await previewDomesticShipping(token, form);
      setPreview(res.preview);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    if (!preview) return;
    const ask = form.test_mode || !liveReady
      ? '테스트로 1건 접수할까요? 우체국에는 보내지 않습니다.'
      : `우체국에 ${preview.api_sender.name} / 공급지 ${preview.office_ser} 로 접수할까요?\n송장에는 ${preview.print_sender.name} 이 찍힙니다.`;
    if (!window.confirm(ask)) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createDomesticShipping(token, form);
      window.location.href = `/domestic-print/${created.id}`;
    } catch (err) {
      setError(parseApiError(err));
      setSaving(false);
    }
  }

  if (loading) return <Loading text="출고 접수를 준비하는 중..." />;

  return (
    <div>
      <PageHeader
        title="국내 출고 접수"
        subtitle={liveReady ? '실접수 가능. 계약은 하나이고 박스 1개당 송장 1장입니다.' : '우체국 키가 없어 테스트 접수로 저장됩니다.'}
      />
      {error && <Alert type="error">{error}</Alert>}
      <Card title="업체와 송장에 찍을 보내는 사람">
        <label>업체
          <select style={inputStyle} value={form.vendor_id || ''} onChange={(e) => applyVendor(Number(e.target.value))}>
            <option value="">선택</option>
            {vendors.map((vendor) => (
              <option key={vendor.id} value={vendor.id}>{vendor.name} · {vendor.office_ser}</option>
            ))}
          </select>
        </label>
        <p className="text-muted" style={{ marginTop: 8 }}>고친 보내는 사람은 송장에만 찍히고, 우체국에는 업체에 저장된 값이 갑니다.</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <label>송장 보내는 사람<input style={inputStyle} value={form.print_sender_name} onChange={(e) => setField('print_sender_name', e.target.value)} /></label>
          <label>전화<input style={inputStyle} value={form.print_sender_phone} onChange={(e) => setField('print_sender_phone', e.target.value)} /></label>
          <label>우편번호<input style={inputStyle} value={form.print_sender_zip} onChange={(e) => setField('print_sender_zip', e.target.value)} /></label>
          <label>상세<input style={inputStyle} value={form.print_sender_addr2} onChange={(e) => setField('print_sender_addr2', e.target.value)} /></label>
        </div>
        <label style={{ display: 'block', marginTop: 12 }}>주소
          <input style={inputStyle} value={form.print_sender_addr1} onChange={(e) => setField('print_sender_addr1', e.target.value)} />
        </label>
      </Card>
      <Card title="받는 사람 · 상품">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label>이름<input style={inputStyle} value={form.recipient_name} onChange={(e) => setField('recipient_name', e.target.value)} /></label>
          <label>전화<input style={inputStyle} value={form.recipient_phone} onChange={(e) => setField('recipient_phone', e.target.value)} /></label>
          <label>우편번호<input style={inputStyle} value={form.recipient_zip} onChange={(e) => setField('recipient_zip', e.target.value)} /></label>
          <label>상세<input style={inputStyle} value={form.recipient_addr2} onChange={(e) => setField('recipient_addr2', e.target.value)} /></label>
          <label>상품명<input style={inputStyle} value={form.goods_name} onChange={(e) => setField('goods_name', e.target.value)} /></label>
          <label>박스
            <select style={inputStyle} value={form.box_size} onChange={(e) => setField('box_size', e.target.value)}>
              {boxSizes.map((size) => <option key={size.code} value={size.code}>{size.label} · {size.desc}</option>)}
            </select>
          </label>
        </div>
        <label style={{ display: 'block', marginTop: 12 }}>주소
          <input style={inputStyle} value={form.recipient_addr1} onChange={(e) => setField('recipient_addr1', e.target.value)} />
        </label>
        <label style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <input type="checkbox" checked={form.test_mode} onChange={(e) => setForm((prev) => ({ ...prev, test_mode: e.target.checked }))} />
          테스트 접수
        </label>
        <div style={{ marginTop: 12 }}>
          <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => void handlePreview()}>확인</button>
          <button type="button" className="btn btn-primary" style={{ marginLeft: 8 }} disabled={saving || !preview} onClick={() => void handleSubmit()}>
            {saving ? '접수 중...' : '접수'}
          </button>
        </div>
        {preview && (
          <div style={{ marginTop: 16, fontSize: '0.92rem', lineHeight: 1.6 }}>
            <div>우체국 보내는 사람: {preview.api_sender.name} · {preview.api_sender.phone} · {preview.api_sender.addr1}</div>
            <div>송장 보내는 사람: {preview.print_sender.name} · {preview.print_sender.phone} · {preview.print_sender.addr1}</div>
            <div>공급지 {preview.office_ser} · {preview.box_label} · {preview.goods_name}</div>
          </div>
        )}
      </Card>
    </div>
  );
}
