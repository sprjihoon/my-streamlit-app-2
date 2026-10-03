'use client';

import { useEffect, useRef, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import { AddressSearch } from '@/components/domestic/AddressSearch';
import { ConfirmDialog } from '@/components/domestic/ConfirmDialog';
import {
  deleteDomesticVendor,
  listDomesticVendors,
  saveDomesticVendor,
  type DomesticVendor,
} from '@/lib/api';
import {
  classifyDomesticError,
  firstField,
  focusDomesticField,
  validateVendor,
  VENDOR_FIELD_ORDER,
  type DomesticBanner,
  type FieldErrors,
} from '@/lib/domestic-form';

const empty = {
  name: '',
  office_ser: '',
  sender_name: '',
  sender_phone: '',
  sender_zip: '',
  sender_addr1: '',
  sender_addr2: '',
};

function inputProps(id: string, error?: string) {
  return {
    id,
    'aria-invalid': Boolean(error) || undefined,
    'aria-describedby': error ? `${id}-error` : undefined,
  };
}

export default function DomesticVendorsPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [banner, setBanner] = useState<DomesticBanner | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [items, setItems] = useState<DomesticVendor[]>([]);
  const [form, setForm] = useState(empty);
  const [editId, setEditId] = useState<number | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DomesticVendor | null>(null);
  const [deleting, setDeleting] = useState(false);
  const saveRef = useRef(false);
  const deleteRef = useRef(false);
  const pendingFocus = useRef<string | null>(null);
  const fieldErrorsRef = useRef(fieldErrors);
  fieldErrorsRef.current = fieldErrors;

  useEffect(() => {
    const key = pendingFocus.current;
    if (!key) return;
    pendingFocus.current = null;
    focusDomesticField(key);
  }, [fieldErrors]);

  async function load(tok: string) {
    const res = await listDomesticVendors(tok);
    setItems(res.items || []);
    setLoadError(null);
    setLoaded(true);
  }

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setLoadError('로그인이 필요합니다.');
      setLoaded(true);
      setLoading(false);
      return;
    }
    load(stored).catch((err) => {
      setLoadError(classifyDomesticError(err, 'vendor').message);
      setLoaded(true);
    }).finally(() => setLoading(false));
  }, []);

  function dropError(key: string) {
    const next = { ...fieldErrorsRef.current };
    if (!next[key]) return;
    delete next[key];
    fieldErrorsRef.current = next;
    setFieldErrors(next);
    setBanner((current) => {
      if (current?.kind !== 'validation') return current;
      const first = firstField(next, VENDOR_FIELD_ORDER);
      if (!first) return null;
      return { kind: 'validation', message: next[first] };
    });
  }

  function setField(key: keyof typeof empty, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
    dropError(key);
  }

  function revealErrors(errors: FieldErrors) {
    const first = firstField(errors, VENDOR_FIELD_ORDER);
    pendingFocus.current = first;
    setFieldErrors(errors);
    setBanner(first ? { kind: 'validation', message: errors[first] } : null);
  }

  async function handleSave() {
    if (saveRef.current) return;
    const errors = validateVendor(form);
    if (Object.keys(errors).length) {
      revealErrors(errors);
      setSuccess(null);
      return;
    }
    saveRef.current = true;
    setSaving(true);
    setBanner(null);
    setSuccess(null);
    try {
      await saveDomesticVendor(token, form, editId || undefined);
      const wasEdit = Boolean(editId);
      setForm(empty);
      setEditId(null);
      setFieldErrors({});
      setSuccess(wasEdit ? '업체를 수정했습니다.' : '업체를 등록했습니다.');
      await load(token);
    } catch (err) {
      const parsed = classifyDomesticError(err, 'vendor');
      setBanner(parsed);
      if (parsed.field) {
        pendingFocus.current = parsed.field;
        setFieldErrors({ [parsed.field]: parsed.message });
      }
    } finally {
      saveRef.current = false;
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete || deleteRef.current) return;
    deleteRef.current = true;
    setDeleting(true);
    setBanner(null);
    try {
      await deleteDomesticVendor(token, pendingDelete.id);
      if (editId === pendingDelete.id) {
        setEditId(null);
        setForm(empty);
      }
      setSuccess('업체를 삭제했습니다.');
      setPendingDelete(null);
      await load(token);
    } catch (err) {
      setBanner(classifyDomesticError(err, 'vendor'));
      setPendingDelete(null);
    } finally {
      deleteRef.current = false;
      setDeleting(false);
    }
  }

  if (loading && !loaded) return <Loading text="출고 업체를 불러오는 중..." />;

  return (
    <div className="domestic-page domestic-form">
      <PageHeader
        title="출고 업체"
        subtitle="주소 검색으로 우편번호와 주소를 채웁니다."
        actions={<a className="btn btn-secondary" href="/domestic-shipping">출고 접수</a>}
      />
      {loadError ? <Alert type="error">{loadError}</Alert> : null}
      {banner ? <Alert type="error">{banner.message}{banner.kind === 'server' || banner.kind === 'network' ? ' 입력한 내용은 그대로입니다.' : ''}</Alert> : null}
      {success ? <Alert type="success">{success}</Alert> : null}
      <Card>
        <section className="domestic-block">
          <p className="domestic-section">업체</p>
          <div className="domestic-row">
            <label className={`domestic-field w-name${fieldErrors.name ? ' is-invalid' : ''}`} htmlFor="name">
              업체명
              <input {...inputProps('name', fieldErrors.name)} value={form.name} onChange={(event) => setField('name', event.target.value)} />
              {fieldErrors.name ? <span className="domestic-field-error" id="name-error">{fieldErrors.name}</span> : null}
            </label>
            <label className={`domestic-field w-office${fieldErrors.office_ser ? ' is-invalid' : ''}`} htmlFor="office_ser">
              공급지번호
              <input {...inputProps('office_ser', fieldErrors.office_ser)} value={form.office_ser} onChange={(event) => setField('office_ser', event.target.value)} />
              {fieldErrors.office_ser ? <span className="domestic-field-error" id="office_ser-error">{fieldErrors.office_ser}</span> : null}
            </label>
          </div>
        </section>
        <section className="domestic-block">
          <p className="domestic-section">보내는 사람</p>
          <div className="domestic-row">
            <label className={`domestic-field w-name${fieldErrors.sender_name ? ' is-invalid' : ''}`} htmlFor="sender_name">
              이름
              <input {...inputProps('sender_name', fieldErrors.sender_name)} value={form.sender_name} onChange={(event) => setField('sender_name', event.target.value)} />
              {fieldErrors.sender_name ? <span className="domestic-field-error" id="sender_name-error">{fieldErrors.sender_name}</span> : null}
            </label>
            <label className={`domestic-field w-phone${fieldErrors.sender_phone ? ' is-invalid' : ''}`} htmlFor="sender_phone">
              전화
              <input {...inputProps('sender_phone', fieldErrors.sender_phone)} inputMode="tel" placeholder="01012345678" value={form.sender_phone} onChange={(event) => setField('sender_phone', event.target.value)} />
              {fieldErrors.sender_phone ? <span className="domestic-field-error" id="sender_phone-error">{fieldErrors.sender_phone}</span> : null}
            </label>
          </div>
          <AddressSearch
            zipId="sender_zip"
            addrId="sender_addr1"
            detailId="sender_addr2"
            zip={form.sender_zip}
            addr1={form.sender_addr1}
            addr2={form.sender_addr2}
            zipError={fieldErrors.sender_zip}
            addrError={fieldErrors.sender_addr1}
            disabled={saving}
            onDetail={(value) => setField('sender_addr2', value)}
            onZip={(value) => setField('sender_zip', value)}
            onAddr={(value) => setField('sender_addr1', value)}
            onPick={(picked) => {
              setForm((prev) => ({ ...prev, sender_zip: picked.zip, sender_addr1: picked.addr1 }));
              dropError('sender_zip');
              dropError('sender_addr1');
            }}
            onError={(message) => setBanner({ kind: 'network', message })}
          />
        </section>
        <div className="domestic-actions">
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void handleSave()}>
            {saving ? '저장 중...' : '저장'}
          </button>
          {editId ? (
            <button type="button" className="btn btn-secondary" onClick={() => { setEditId(null); setForm(empty); setFieldErrors({}); setBanner(null); }}>
              취소
            </button>
          ) : null}
        </div>
      </Card>
      <Card>
        {loadError && items.length === 0 ? null : items.length === 0 ? <p className="text-muted">등록된 업체가 없습니다.</p> : (
          <div className="table-container">
            <table>
              <thead>
                <tr><th>업체</th><th>공급지번호</th><th>보내는 사람</th><th></th></tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td className="domestic-mono">{item.office_ser}</td>
                    <td>{item.sender_name} · {item.sender_phone}</td>
                    <td>
                      <div className="domestic-row-actions">
                        <button type="button" className="btn btn-secondary" onClick={() => {
                          setEditId(item.id);
                          setForm({
                            name: item.name,
                            office_ser: item.office_ser,
                            sender_name: item.sender_name,
                            sender_phone: item.sender_phone,
                            sender_zip: item.sender_zip,
                            sender_addr1: item.sender_addr1,
                            sender_addr2: item.sender_addr2,
                          });
                          setFieldErrors({});
                          setBanner(null);
                        }}>수정</button>
                        <button type="button" className="btn btn-danger" onClick={() => setPendingDelete(item)}>삭제</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="업체 삭제"
        description={pendingDelete ? `${pendingDelete.name} 업체를 삭제할까요? 이미 접수한 송장은 그대로 남습니다.` : ''}
        confirmLabel="삭제"
        confirmClass="btn btn-danger"
        busy={deleting}
        busyLabel="삭제 중..."
        onDismiss={() => { if (!deleteRef.current) setPendingDelete(null); }}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
