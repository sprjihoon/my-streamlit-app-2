'use client';

import { useEffect, useRef, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import { AddressSearch } from '@/components/domestic/AddressSearch';
import { ConfirmDialog } from '@/components/domestic/ConfirmDialog';
import {
  createDomesticShipping,
  getDomesticMeta,
  listDomesticSavedRecipients,
  listDomesticVendors,
  previewDomesticShipping,
  saveDomesticRecipient,
  type DomesticBoxSize,
  type DomesticPreview,
  type DomesticSavedRecipient,
  type DomesticSubmitPayload,
  type DomesticVendor,
} from '@/lib/api';
import {
  classifyDomesticError,
  firstField,
  focusDomesticField,
  SHIPMENT_FIELD_ORDER,
  validateShipment,
  type DomesticBanner,
  type FieldErrors,
} from '@/lib/domestic-form';

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

type Created = Awaited<ReturnType<typeof createDomesticShipping>>;
type Busy = null | 'preview' | 'confirm' | 'submit';

function inputProps(id: string, error?: string) {
  return {
    id,
    'aria-invalid': Boolean(error) || undefined,
    'aria-describedby': error ? `${id}-error` : undefined,
  };
}

export default function DomesticShippingPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [banner, setBanner] = useState<DomesticBanner | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [liveReady, setLiveReady] = useState(false);
  const [vendors, setVendors] = useState<DomesticVendor[]>([]);
  const [savedRecipients, setSavedRecipients] = useState<DomesticSavedRecipient[]>([]);
  const [selectedSavedId, setSelectedSavedId] = useState('');
  const [saveAddress, setSaveAddress] = useState(false);
  const [addressAlias, setAddressAlias] = useState('');
  const [saveNote, setSaveNote] = useState('');
  const [boxSizes, setBoxSizes] = useState<DomesticBoxSize[]>([]);
  const [form, setForm] = useState<DomesticSubmitPayload>(emptyForm());
  const [preview, setPreview] = useState<DomesticPreview | null>(null);
  const [confirmPreview, setConfirmPreview] = useState<DomesticPreview | null>(null);
  const [result, setResult] = useState<Created | null>(null);
  const busyRef = useRef(false);
  const submitOnce = useRef(false);
  const pendingFocus = useRef<string | null>(null);
  const fieldErrorsRef = useRef(fieldErrors);
  fieldErrorsRef.current = fieldErrors;

  useEffect(() => {
    const key = pendingFocus.current;
    if (!key) return;
    pendingFocus.current = null;
    focusDomesticField(key);
  }, [fieldErrors]);

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setBanner({ kind: 'auth', message: '로그인이 필요합니다.' });
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const [meta, vendorRes, savedRes] = await Promise.all([
          getDomesticMeta(stored),
          listDomesticVendors(stored),
          listDomesticSavedRecipients(stored).catch(() => ({ items: [] as DomesticSavedRecipient[] })),
        ]);
        setLiveReady(meta.live_ready);
        setBoxSizes(meta.box_sizes || []);
        setVendors(vendorRes.items || []);
        setSavedRecipients(savedRes.items || []);
        setForm((prev) => ({ ...prev, test_mode: !meta.live_ready }));
      } catch (err) {
        setBanner(classifyDomesticError(err, 'shipment'));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function revealErrors(errors: FieldErrors) {
    const first = firstField(errors, SHIPMENT_FIELD_ORDER);
    pendingFocus.current = first;
    setFieldErrors(errors);
    setBanner(first ? { kind: 'validation', message: errors[first] } : null);
  }

  function dropError(key: string) {
    const next = { ...fieldErrorsRef.current };
    if (!next[key]) return;
    delete next[key];
    fieldErrorsRef.current = next;
    setFieldErrors(next);
    setBanner((current) => {
      if (current?.kind !== 'validation') return current;
      const first = firstField(next, SHIPMENT_FIELD_ORDER);
      if (!first) return null;
      return { kind: 'validation', message: next[first] };
    });
  }

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
    dropError('vendor_id');
    ['print_sender_name', 'print_sender_phone', 'print_sender_zip', 'print_sender_addr1'].forEach(dropError);
  }

  function setField(key: keyof DomesticSubmitPayload, value: string) {
    setPreview(null);
    if (String(key).startsWith('recipient_')) setSelectedSavedId('');
    setForm((prev) => ({ ...prev, [key]: value }));
    dropError(key);
  }

  function applySavedRecipient(id: string) {
    if (!id) {
      setSelectedSavedId('');
      return;
    }
    const saved = savedRecipients.find((item) => String(item.id) === id);
    if (!saved) return;
    setSelectedSavedId(id);
    setPreview(null);
    setForm((prev) => ({
      ...prev,
      ...(saved.recipient_name != null ? { recipient_name: saved.recipient_name } : {}),
      ...(saved.recipient_phone != null ? { recipient_phone: saved.recipient_phone } : {}),
      ...(saved.zipcode != null ? { recipient_zip: saved.zipcode } : {}),
      ...(saved.addr1 != null ? { recipient_addr1: saved.addr1 } : {}),
      ...(saved.addr2 != null ? { recipient_addr2: saved.addr2 } : {}),
    }));
    ['recipient_name', 'recipient_phone', 'recipient_zip', 'recipient_addr1'].forEach(dropError);
  }

  function setCount(key: 'goods_qty' | 'label_count', raw: string) {
    const count = Math.max(1, Math.min(99, parseInt(raw, 10) || 1));
    setPreview(null);
    setForm((prev) => ({ ...prev, [key]: count }));
    dropError(key);
  }

  function pickAddress(prefix: 'recipient' | 'print_sender', picked: { zip: string; addr1: string }) {
    setPreview(null);
    setForm((prev) => (
      prefix === 'recipient'
        ? { ...prev, recipient_zip: picked.zip, recipient_addr1: picked.addr1 }
        : { ...prev, print_sender_zip: picked.zip, print_sender_addr1: picked.addr1 }
    ));
    if (prefix === 'recipient') setSelectedSavedId('');
    dropError(prefix === 'recipient' ? 'recipient_zip' : 'print_sender_zip');
    dropError(prefix === 'recipient' ? 'recipient_addr1' : 'print_sender_addr1');
  }

  function revealFailure(err: unknown) {
    const parsed = classifyDomesticError(err, 'shipment');
    setBanner(parsed);
    if (!parsed.field) return;
    pendingFocus.current = parsed.field;
    setFieldErrors({ [parsed.field]: parsed.message });
  }

  async function handlePreview() {
    if (busyRef.current) return;
    const errors = validateShipment(form, vendors, boxSizes);
    if (Object.keys(errors).length) {
      revealErrors(errors);
      return;
    }
    busyRef.current = true;
    setBusy('preview');
    setBanner(null);
    try {
      const res = await previewDomesticShipping(token, form);
      setPreview(res.preview);
      setFieldErrors({});
    } catch (err) {
      revealFailure(err);
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  function saveAliasError() {
    if (!saveAddress) return '';
    const label = addressAlias.trim();
    if (!label) return '주소지를 저장하려면 별칭을 입력해주세요.';
    if (label.length > 50) return '별칭은 50자 이하여야 합니다.';
    return '';
  }

  async function handleSubmit() {
    if (busyRef.current) return;
    const aliasError = saveAliasError();
    if (aliasError) {
      setBanner({ kind: 'validation', message: aliasError });
      return;
    }
    const errors = validateShipment(form, vendors, boxSizes);
    if (Object.keys(errors).length) {
      revealErrors(errors);
      return;
    }
    busyRef.current = true;
    setBusy('preview');
    setBanner(null);
    try {
      let current = preview;
      if (!current) {
        const res = await previewDomesticShipping(token, form);
        current = res.preview;
        setPreview(current);
      }
      setConfirmPreview(current);
      setBusy('confirm');
    } catch (err) {
      revealFailure(err);
      busyRef.current = false;
      setBusy(null);
    }
  }

  function dismissConfirm() {
    if (busy === 'submit') return;
    setConfirmPreview(null);
    busyRef.current = false;
    setBusy(null);
  }

  async function confirmSubmit() {
    if (submitOnce.current || !confirmPreview) return;
    submitOnce.current = true;
    setBusy('submit');
    try {
      const created = await createDomesticShipping(token, form);
      let note = '';
      if (saveAddress) {
        const label = addressAlias.trim();
        try {
          await saveDomesticRecipient(token, {
            label,
            recipient_name: form.recipient_name,
            recipient_phone: form.recipient_phone,
            zipcode: form.recipient_zip,
            addr1: form.recipient_addr1,
            addr2: form.recipient_addr2,
          });
          note = `주소지 '${label}'을 저장했습니다.`;
          const refreshed = await listDomesticSavedRecipients(token);
          setSavedRecipients(refreshed.items || []);
          setSaveAddress(false);
          setAddressAlias('');
        } catch (err) {
          const parsed = classifyDomesticError(err, 'shipment');
          note = `접수는 완료됐지만 주소 저장에 실패했습니다. ${parsed.message}`;
        }
      }
      setSaveNote(note);
      setResult(created);
      setConfirmPreview(null);
      setFieldErrors({});
      setBanner(null);
    } catch (err) {
      revealFailure(err);
      setConfirmPreview(null);
    } finally {
      submitOnce.current = false;
      busyRef.current = false;
      setBusy(null);
    }
  }

  function startAnother() {
    const vendor = vendors.find((item) => item.id === form.vendor_id);
    setResult(null);
    setPreview(null);
    setConfirmPreview(null);
    setSelectedSavedId('');
    setSaveAddress(false);
    setAddressAlias('');
    setSaveNote('');
    setBanner(null);
    setFieldErrors({});
    setForm((prev) => ({
      ...emptyForm(),
      vendor_id: prev.vendor_id,
      print_sender_name: vendor?.sender_name || prev.print_sender_name,
      print_sender_phone: vendor?.sender_phone || prev.print_sender_phone,
      print_sender_zip: vendor?.sender_zip || prev.print_sender_zip,
      print_sender_addr1: vendor?.sender_addr1 || prev.print_sender_addr1,
      print_sender_addr2: vendor?.sender_addr2 || prev.print_sender_addr2,
      goods_name: prev.goods_name,
      goods_qty: prev.goods_qty,
      box_size: prev.box_size,
      label_count: prev.label_count,
      test_mode: prev.test_mode,
    }));
  }

  if (loading) return <Loading text="출고 접수를 준비하는 중..." />;

  const locked = busy !== null;
  const sheets = confirmPreview?.label_count || form.label_count || 1;
  const confirmText = confirmPreview
    ? (form.test_mode || !liveReady
      ? `테스트로 ${sheets}장 접수할까요? 우체국에는 보내지 않습니다.`
      : `우체국에 ${confirmPreview.api_sender.name} / 공급지 ${confirmPreview.office_ser} 로 ${sheets}장 접수할까요?`)
    : '';

  return (
    <div className="domestic-page domestic-form">
      <PageHeader
        title="국내 출고"
        subtitle="업체를 고르고 받는 사람과 상품을 입력한 뒤 접수합니다."
        actions={<a className="btn btn-secondary" href="/domestic-shipping-list">접수목록</a>}
      />
      {banner ? (
        <Alert type={banner.kind === 'validation' || banner.kind === 'auth' ? 'error' : banner.kind === 'uncertain' ? 'warning' : 'error'}>
          {banner.kind === 'network' ? `${banner.message} 입력한 내용은 그대로입니다.` : banner.message}
          {banner.kind === 'server' ? ' 입력한 내용은 그대로입니다. 다시 접수할 수 있습니다.' : ''}
          {banner.kind === 'uncertain' ? ' 자동으로 다시 보내지 않았습니다. ' : ''}
          {banner.kind === 'uncertain' ? <a href="/domestic-shipping-list">접수목록에서 생성 여부를 확인</a> : null}
        </Alert>
      ) : null}
      {!banner && !liveReady ? <p className="text-muted">우체국 연결이 없어 테스트로 저장됩니다.</p> : null}

      {result ? (
        <CreatedResult result={result} note={saveNote} onAgain={startAnother} />
      ) : (
        <Card>
          <section className="domestic-block">
            <p className="domestic-section">업체</p>
            <div className="domestic-row">
              <label className={`domestic-field w-vendor${fieldErrors.vendor_id ? ' is-invalid' : ''}`} htmlFor="vendor_id">
                업체
                <select
                  {...inputProps('vendor_id', fieldErrors.vendor_id)}
                  value={form.vendor_id || ''}
                  onChange={(event) => applyVendor(Number(event.target.value))}
                >
                  <option value="">선택</option>
                  {vendors.map((vendor) => (
                    <option key={vendor.id} value={vendor.id}>{vendor.name}</option>
                  ))}
                </select>
                {fieldErrors.vendor_id ? <span className="domestic-field-error" id="vendor_id-error">{fieldErrors.vendor_id}</span> : null}
              </label>
            </div>
          </section>

          <section className="domestic-block">
            <p className="domestic-section">송장 보내는 사람</p>
            <div className="domestic-row">
              <label className={`domestic-field w-name${fieldErrors.print_sender_name ? ' is-invalid' : ''}`} htmlFor="print_sender_name">
                이름
                <input {...inputProps('print_sender_name', fieldErrors.print_sender_name)} value={form.print_sender_name} onChange={(event) => setField('print_sender_name', event.target.value)} />
                {fieldErrors.print_sender_name ? <span className="domestic-field-error" id="print_sender_name-error">{fieldErrors.print_sender_name}</span> : null}
              </label>
              <label className={`domestic-field w-phone${fieldErrors.print_sender_phone ? ' is-invalid' : ''}`} htmlFor="print_sender_phone">
                전화
                <input {...inputProps('print_sender_phone', fieldErrors.print_sender_phone)} inputMode="tel" placeholder="01012345678" value={form.print_sender_phone} onChange={(event) => setField('print_sender_phone', event.target.value)} />
                {fieldErrors.print_sender_phone ? <span className="domestic-field-error" id="print_sender_phone-error">{fieldErrors.print_sender_phone}</span> : null}
              </label>
            </div>
            <AddressSearch
              zipId="print_sender_zip"
              addrId="print_sender_addr1"
              detailId="print_sender_addr2"
              zip={form.print_sender_zip}
              addr1={form.print_sender_addr1}
              addr2={form.print_sender_addr2}
              zipError={fieldErrors.print_sender_zip}
              addrError={fieldErrors.print_sender_addr1}
              disabled={locked}
              onDetail={(value) => setField('print_sender_addr2', value)}
              onZip={(value) => setField('print_sender_zip', value)}
              onAddr={(value) => setField('print_sender_addr1', value)}
              onPick={(picked) => pickAddress('print_sender', picked)}
              onError={(message) => setBanner({ kind: 'network', message })}
            />
          </section>

          <section className="domestic-block domestic-block-primary">
            <p className="domestic-section">받는 사람</p>
            <div className="domestic-row">
              <label className="domestic-field w-vendor" htmlFor="saved_recipient">
                저장된 주소지
                <select
                  id="saved_recipient"
                  value={selectedSavedId}
                  disabled={locked || savedRecipients.length === 0}
                  onChange={(event) => applySavedRecipient(event.target.value)}
                >
                  <option value="">
                    {savedRecipients.length === 0 ? '저장된 주소지가 없습니다' : '선택하면 받는 사람만 채웁니다'}
                  </option>
                  {savedRecipients.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </label>
              <a className="btn btn-secondary" href="/domestic-saved-recipients">주소지 관리</a>
            </div>
            <div className="domestic-row">
              <label className={`domestic-field w-name${fieldErrors.recipient_name ? ' is-invalid' : ''}`} htmlFor="recipient_name">
                이름
                <input {...inputProps('recipient_name', fieldErrors.recipient_name)} value={form.recipient_name} onChange={(event) => setField('recipient_name', event.target.value)} />
                {fieldErrors.recipient_name ? <span className="domestic-field-error" id="recipient_name-error">{fieldErrors.recipient_name}</span> : null}
              </label>
              <label className={`domestic-field w-phone${fieldErrors.recipient_phone ? ' is-invalid' : ''}`} htmlFor="recipient_phone">
                전화
                <input {...inputProps('recipient_phone', fieldErrors.recipient_phone)} inputMode="tel" placeholder="01012345678" value={form.recipient_phone} onChange={(event) => setField('recipient_phone', event.target.value)} />
                {fieldErrors.recipient_phone ? <span className="domestic-field-error" id="recipient_phone-error">{fieldErrors.recipient_phone}</span> : null}
              </label>
            </div>
            <AddressSearch
              zipId="recipient_zip"
              addrId="recipient_addr1"
              detailId="recipient_addr2"
              zip={form.recipient_zip}
              addr1={form.recipient_addr1}
              addr2={form.recipient_addr2}
              zipError={fieldErrors.recipient_zip}
              addrError={fieldErrors.recipient_addr1}
              disabled={locked}
              onDetail={(value) => setField('recipient_addr2', value)}
              onZip={(value) => setField('recipient_zip', value)}
              onAddr={(value) => setField('recipient_addr1', value)}
              onPick={(picked) => pickAddress('recipient', picked)}
              onError={(message) => setBanner({ kind: 'network', message })}
            />
            <label className="domestic-check" htmlFor="save_address">
              <input
                id="save_address"
                type="checkbox"
                checked={saveAddress}
                disabled={locked}
                onChange={(event) => {
                  setSaveAddress(event.target.checked);
                  if (!event.target.checked) setAddressAlias('');
                }}
              />
              받는 사람 주소 저장
            </label>
            {saveAddress ? (
              <label className={`domestic-field w-name${fieldErrors.address_alias ? ' is-invalid' : ''}`} htmlFor="address_alias">
                주소지 별칭
                <input
                  id="address_alias"
                  value={addressAlias}
                  maxLength={50}
                  placeholder="예: 본사, 경기창고"
                  disabled={locked}
                  onChange={(event) => setAddressAlias(event.target.value)}
                />
              </label>
            ) : null}
            <div className="domestic-row">
              <label className="domestic-field w-notes" htmlFor="notes">
                배송메시지
                <input id="notes" value={form.notes} onChange={(event) => setField('notes', event.target.value)} />
              </label>
            </div>
          </section>

          <section className="domestic-block">
            <p className="domestic-section">상품</p>
            <div className="domestic-row">
              <label className={`domestic-field w-goods${fieldErrors.goods_name ? ' is-invalid' : ''}`} htmlFor="goods_name">
                상품
                <input {...inputProps('goods_name', fieldErrors.goods_name)} value={form.goods_name} onChange={(event) => setField('goods_name', event.target.value)} />
                {fieldErrors.goods_name ? <span className="domestic-field-error" id="goods_name-error">{fieldErrors.goods_name}</span> : null}
              </label>
              <label className={`domestic-field w-qty${fieldErrors.goods_qty ? ' is-invalid' : ''}`} htmlFor="goods_qty">
                상품수량
                <input {...inputProps('goods_qty', fieldErrors.goods_qty)} type="number" min={1} max={99} value={form.goods_qty || 1} onChange={(event) => setCount('goods_qty', event.target.value)} />
                {fieldErrors.goods_qty ? <span className="domestic-field-error" id="goods_qty-error">{fieldErrors.goods_qty}</span> : null}
              </label>
              <label className={`domestic-field w-box${fieldErrors.box_size ? ' is-invalid' : ''}`} htmlFor="box_size">
                박스
                <select {...inputProps('box_size', fieldErrors.box_size)} value={form.box_size} onChange={(event) => setField('box_size', event.target.value)}>
                  {boxSizes.map((size) => <option key={size.code} value={size.code}>{size.label}</option>)}
                </select>
                {fieldErrors.box_size ? <span className="domestic-field-error" id="box_size-error">{fieldErrors.box_size}</span> : null}
              </label>
              <label className={`domestic-field w-qty${fieldErrors.label_count ? ' is-invalid' : ''}`} htmlFor="label_count">
                송장 갯수
                <input {...inputProps('label_count', fieldErrors.label_count)} type="number" min={1} max={99} value={form.label_count || 1} onChange={(event) => setCount('label_count', event.target.value)} />
                {fieldErrors.label_count ? <span className="domestic-field-error" id="label_count-error">{fieldErrors.label_count}</span> : null}
              </label>
            </div>
          </section>

          <label className="domestic-check">
            <input
              type="checkbox"
              checked={form.test_mode}
              onChange={(event) => {
                setPreview(null);
                setForm((prev) => ({ ...prev, test_mode: event.target.checked }));
              }}
            />
            테스트 접수
          </label>
          <div className="domestic-actions">
            <button type="button" className="btn btn-secondary" disabled={locked} onClick={() => void handlePreview()}>
              {busy === 'preview' ? '확인 중...' : '확인'}
            </button>
            <button type="button" className="btn btn-primary" disabled={locked} onClick={() => void handleSubmit()}>
              {busy === 'submit' ? '접수 중...' : busy === 'preview' ? '확인 중...' : '접수'}
            </button>
          </div>
          {preview ? (
            <p className="text-muted" style={{ marginTop: 12, marginBottom: 0 }}>
              받는 사람 {preview.recipient.name} · 우체국 {preview.api_sender.name} · 공급지 {preview.office_ser} · 송장 {preview.print_sender.name} · {preview.goods_name} {preview.goods_qty}개 · {preview.label_count}장 · {preview.box_label}
            </p>
          ) : null}
        </Card>
      )}

      <ConfirmDialog
        open={Boolean(confirmPreview)}
        title={form.test_mode || !liveReady ? '테스트 접수' : '우체국 접수'}
        description={confirmText}
        confirmLabel="접수"
        confirmClass="btn btn-primary"
        busy={busy === 'submit'}
        busyLabel="접수 중..."
        onDismiss={dismissConfirm}
        onConfirm={() => void confirmSubmit()}
      >
        {confirmPreview ? <PreviewFacts preview={confirmPreview} notes={form.notes} /> : null}
      </ConfirmDialog>
    </div>
  );
}

function PreviewFacts({ preview, notes }: { preview: DomesticPreview; notes: string }) {
  return (
    <dl className="domestic-facts domestic-dialog-facts">
      <dt>받는 사람</dt>
      <dd>{preview.recipient.name} · {preview.recipient.phone}<br />{preview.recipient.zip} {preview.recipient.addr1} {preview.recipient.addr2}</dd>
      <dt>업체</dt>
      <dd>{preview.vendor_name}</dd>
      <dt>송장 보내는 사람</dt>
      <dd>{preview.print_sender.name}</dd>
      <dt>상품</dt>
      <dd>{preview.goods_name} {preview.goods_qty}개 · {preview.box_label} · {preview.label_count}장</dd>
      {notes.trim() ? (<><dt>배송메시지</dt><dd>{notes.trim()}</dd></>) : null}
    </dl>
  );
}

function CreatedResult({ result, note, onAgain }: { result: Created; note: string; onAgain: () => void }) {
  const ids = result.ids?.length ? result.ids : (result.id ? [result.id] : []);
  const trackings = result.tracking_nos?.length
    ? result.tracking_nos
    : (result.tracking_no ? [result.tracking_no] : []);
  const paired = ids.length === trackings.length;
  const printHref = ids.length > 1
    ? `/domestic-print/batch?ids=${ids.join(',')}`
    : (ids[0] ? `/domestic-print/${ids[0]}` : '');
  const detailHref = result.id ? `/domestic-shipping-list/${result.id}` : '';

  return (
    <Card>
      <p className="domestic-section">접수 결과</p>
      {note ? <p>{note}</p> : null}
      {result.duplicate_guard ? <p>이미 접수된 건을 그대로 보여줍니다.</p> : null}
      {result.partial ? <p>요청한 장수 중 일부만 접수되었습니다.</p> : null}
      <dl className="domestic-facts">
        {result.order_no ? (<><dt>접수번호</dt><dd className="domestic-mono">{result.order_no}</dd></>) : null}
        {trackings.length ? (
          <>
            <dt>송장번호</dt>
            <dd className="domestic-mono">{trackings.filter(Boolean).join(', ') || '-'}</dd>
          </>
        ) : null}
        {result.preview?.recipient?.name ? (<><dt>받는 사람</dt><dd>{result.preview.recipient.name}</dd></>) : null}
        {result.preview?.vendor_name ? (<><dt>업체</dt><dd>{result.preview.vendor_name}</dd></>) : null}
        {result.price ? (<><dt>요금</dt><dd>{result.price}</dd></>) : null}
        <dt>구분</dt>
        <dd>{result.is_test ? '테스트' : '접수'}</dd>
      </dl>
      {paired && ids.length > 1 ? (
        <ul className="domestic-result-links">
          {ids.map((id, index) => (
            <li key={id}>
              <span className="domestic-mono">{trackings[index] || id}</span>
              {' '}
              <a href={`/domestic-shipping-list/${id}`}>상세</a>
              {' · '}
              <a href={`/domestic-print/${id}`} target="_blank" rel="noreferrer">출력</a>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="domestic-actions">
        {detailHref ? <a className="btn btn-secondary" href={detailHref}>상세 보기</a> : null}
        {printHref ? <a className="btn btn-primary" href={printHref} target="_blank" rel="noreferrer">출력</a> : null}
        <button type="button" className="btn btn-secondary" onClick={onAgain}>새 접수</button>
      </div>
    </Card>
  );
}
