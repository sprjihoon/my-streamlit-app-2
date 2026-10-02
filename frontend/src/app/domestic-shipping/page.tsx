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
    goods_qty: 1,
    box_size: 'SMALL',
    label_count: 1,
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

  function setCount(key: 'goods_qty' | 'label_count', raw: string) {
    const count = Math.max(1, Math.min(99, parseInt(raw, 10) || 1));
    setPreview(null);
    setForm((prev) => ({ ...prev, [key]: count }));
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
    const sheets = preview.label_count || 1;
    const qty = preview.goods_qty || 1;
    const ask = form.test_mode || !liveReady
      ? `테스트로 ${sheets}장 접수할까요? 우체국에는 보내지 않습니다.`
      : `우체국에 ${preview.api_sender.name} / 공급지 ${preview.office_ser} 로 ${sheets}장 접수할까요?\n상품 ${preview.goods_name} ${qty}개가 각 접수에 전달됩니다. 송장에는 ${preview.print_sender.name} 이 찍힙니다.`;
    if (!window.confirm(ask)) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createDomesticShipping(token, form);
      const ids = created.ids?.length ? created.ids : [created.id];
      window.location.href = ids.length > 1
        ? `/domestic-print/batch?ids=${ids.join(',')}`
        : `/domestic-print/${ids[0]}`;
    } catch (err) {
      setError(parseApiError(err));
      setSaving(false);
    }
  }

  if (loading) return <Loading text="출고 접수를 준비하는 중..." />;

  return (
    <div className="domestic-form">
      <PageHeader title="국내 출고" />
      {error && <Alert type="error">{error}</Alert>}
      {!error && !liveReady && <p className="text-muted">우체국 연결이 없어 테스트로 저장됩니다.</p>}
      <Card>
        <div className="domestic-row">
          <label className="domestic-field w-vendor">
            업체
            <select value={form.vendor_id || ''} onChange={(e) => applyVendor(Number(e.target.value))}>
              <option value="">선택</option>
              {vendors.map((vendor) => (
                <option key={vendor.id} value={vendor.id}>{vendor.name}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="domestic-section">송장 보내는 사람</p>
        <div className="domestic-row">
          <label className="domestic-field w-name">이름<input value={form.print_sender_name} onChange={(e) => setField('print_sender_name', e.target.value)} /></label>
          <label className="domestic-field w-phone">전화<input value={form.print_sender_phone} onChange={(e) => setField('print_sender_phone', e.target.value)} /></label>
          <label className="domestic-field w-zip">우편번호<input value={form.print_sender_zip} onChange={(e) => setField('print_sender_zip', e.target.value)} /></label>
        </div>
        <div className="domestic-row">
          <label className="domestic-field w-addr">주소<input value={form.print_sender_addr1} onChange={(e) => setField('print_sender_addr1', e.target.value)} /></label>
          <label className="domestic-field w-detail">상세<input value={form.print_sender_addr2} onChange={(e) => setField('print_sender_addr2', e.target.value)} /></label>
        </div>
        <p className="domestic-section">받는 사람</p>
        <div className="domestic-row">
          <label className="domestic-field w-name">이름<input value={form.recipient_name} onChange={(e) => setField('recipient_name', e.target.value)} /></label>
          <label className="domestic-field w-phone">전화<input value={form.recipient_phone} onChange={(e) => setField('recipient_phone', e.target.value)} /></label>
          <label className="domestic-field w-zip">우편번호<input value={form.recipient_zip} onChange={(e) => setField('recipient_zip', e.target.value)} /></label>
        </div>
        <div className="domestic-row">
          <label className="domestic-field w-addr">주소<input value={form.recipient_addr1} onChange={(e) => setField('recipient_addr1', e.target.value)} /></label>
          <label className="domestic-field w-detail">상세<input value={form.recipient_addr2} onChange={(e) => setField('recipient_addr2', e.target.value)} /></label>
        </div>
        <div className="domestic-row">
          <label className="domestic-field w-goods">상품<input value={form.goods_name} onChange={(e) => setField('goods_name', e.target.value)} /></label>
          <label className="domestic-field w-qty">상품수량<input type="number" min={1} max={99} value={form.goods_qty || 1} onChange={(e) => setCount('goods_qty', e.target.value)} /></label>
          <label className="domestic-field w-box">
            박스
            <select value={form.box_size} onChange={(e) => setField('box_size', e.target.value)}>
              {boxSizes.map((size) => <option key={size.code} value={size.code}>{size.label}</option>)}
            </select>
          </label>
          <label className="domestic-field w-qty">송장 갯수<input type="number" min={1} max={99} value={form.label_count || 1} onChange={(e) => setCount('label_count', e.target.value)} /></label>
        </div>
        <label className="domestic-check">
          <input type="checkbox" checked={form.test_mode} onChange={(e) => setForm((prev) => ({ ...prev, test_mode: e.target.checked }))} />
          테스트 접수
        </label>
        <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => void handlePreview()}>확인</button>
        <button type="button" className="btn btn-primary" style={{ marginLeft: 8 }} disabled={saving || !preview} onClick={() => void handleSubmit()}>
          {saving ? '접수 중...' : '접수'}
        </button>
        {preview && (
          <p className="text-muted" style={{ marginTop: 12, marginBottom: 0 }}>
            우체국 {preview.api_sender.name} · 공급지 {preview.office_ser} · 송장 {preview.print_sender.name} · {preview.goods_name} {preview.goods_qty}개 · {preview.label_count}장 · {preview.box_label}
          </p>
        )}
      </Card>
    </div>
  );
}
