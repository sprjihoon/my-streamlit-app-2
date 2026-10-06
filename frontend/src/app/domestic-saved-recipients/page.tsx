'use client';

import { useEffect, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import { AddressSearch } from '@/components/domestic/AddressSearch';
import {
  deleteDomesticSavedRecipient,
  listDomesticSavedRecipients,
  saveDomesticRecipient,
  updateDomesticSavedRecipient,
  type DomesticSavedRecipient,
  type DomesticSavedRecipientPayload,
} from '@/lib/api';
import { classifyDomesticError } from '@/lib/domestic-form';

const empty = {
  label: '',
  recipient_name: '',
  recipient_phone: '',
  zipcode: '',
  addr1: '',
  addr2: '',
};

export default function DomesticSavedRecipientsPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [recipients, setRecipients] = useState<DomesticSavedRecipient[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<DomesticSavedRecipientPayload>(empty);

  async function loadRecipients(auth: string) {
    const data = await listDomesticSavedRecipients(auth);
    setRecipients(data.items || []);
  }

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    loadRecipients(stored).catch((err) => {
      setError(classifyDomesticError(err, 'shipment').message);
    }).finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setError(null);
    setSuccess(null);
    if (!form.label.trim()) {
      setError('별칭을 입력해주세요.');
      return;
    }
    if (!form.recipient_name.trim()) {
      setError('받는 사람 이름을 입력해주세요.');
      return;
    }
    if (!form.recipient_phone.trim()) {
      setError('연락처를 입력해주세요.');
      return;
    }
    if (!form.zipcode || !form.addr1) {
      setError('주소를 입력해주세요.');
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        await updateDomesticSavedRecipient(token, editingId, form);
        setSuccess(`'${form.label}' 주소지를 수정했습니다.`);
      } else {
        await saveDomesticRecipient(token, form);
        setSuccess(`'${form.label}' 주소지를 저장했습니다.`);
      }
      setForm(empty);
      setShowAddForm(false);
      setEditingId(null);
      await loadRecipients(token);
    } catch (err) {
      setError(classifyDomesticError(err, 'shipment').message);
    } finally {
      setSaving(false);
    }
  }

  function handleEdit(recipient: DomesticSavedRecipient) {
    setForm({
      label: recipient.label,
      recipient_name: recipient.recipient_name,
      recipient_phone: recipient.recipient_phone,
      zipcode: recipient.zipcode,
      addr1: recipient.addr1,
      addr2: recipient.addr2,
    });
    setEditingId(recipient.id);
    setShowAddForm(true);
    setError(null);
    setSuccess(null);
  }

  function handleCancelEdit() {
    setForm(empty);
    setShowAddForm(false);
    setEditingId(null);
    setError(null);
  }

  async function handleDelete(id: number, label: string) {
    if (!window.confirm(`'${label}' 주소지를 삭제할까요?`)) return;
    setError(null);
    setSuccess(null);
    try {
      await deleteDomesticSavedRecipient(token, id);
      setSuccess(`'${label}' 주소지를 삭제했습니다.`);
      await loadRecipients(token);
    } catch (err) {
      setError(classifyDomesticError(err, 'shipment').message);
    }
  }

  if (loading) return <Loading text="출고 주소지를 불러오는 중..." />;

  return (
    <div className="domestic-page domestic-form">
      <PageHeader
        title="출고 주소지"
        subtitle="국내 출고의 받는 사람 주소입니다. 회수신청 주소와 따로 저장됩니다."
        actions={<a className="btn btn-secondary" href="/domestic-shipping">출고 접수</a>}
      />
      {error ? <Alert type="error">{error}</Alert> : null}
      {success ? <Alert type="success">{success}</Alert> : null}
      <Card>
        <div className="domestic-actions">
          <button type="button" className="btn btn-primary" onClick={() => setShowAddForm(!showAddForm)} disabled={saving}>
            {showAddForm ? '취소' : '새 주소지 추가'}
          </button>
        </div>
        {showAddForm ? (
          <section className="domestic-block">
            <p className="domestic-section">{editingId ? '주소지 수정' : '새 주소지'}</p>
            <label className="domestic-field w-name" htmlFor="label">
              별칭
              <input id="label" value={form.label} placeholder="예: 본사, 경기창고" onChange={(event) => setForm((prev) => ({ ...prev, label: event.target.value }))} />
            </label>
            <div className="domestic-row">
              <label className="domestic-field w-name" htmlFor="recipient_name">
                이름
                <input id="recipient_name" value={form.recipient_name} onChange={(event) => setForm((prev) => ({ ...prev, recipient_name: event.target.value }))} />
              </label>
              <label className="domestic-field w-phone" htmlFor="recipient_phone">
                전화
                <input id="recipient_phone" inputMode="tel" placeholder="01012345678" value={form.recipient_phone} onChange={(event) => setForm((prev) => ({ ...prev, recipient_phone: event.target.value }))} />
              </label>
            </div>
            <AddressSearch
              zipId="zipcode"
              addrId="addr1"
              detailId="addr2"
              zip={form.zipcode}
              addr1={form.addr1}
              addr2={form.addr2}
              disabled={saving}
              onZip={(value) => setForm((prev) => ({ ...prev, zipcode: value }))}
              onAddr={(value) => setForm((prev) => ({ ...prev, addr1: value }))}
              onDetail={(value) => setForm((prev) => ({ ...prev, addr2: value }))}
              onPick={(picked) => setForm((prev) => ({ ...prev, zipcode: picked.zip, addr1: picked.addr1 }))}
              onError={(message) => setError(message)}
            />
            <div className="domestic-actions">
              <button type="button" className="btn btn-primary" onClick={() => void handleSave()} disabled={saving}>
                {saving ? '저장 중...' : editingId ? '수정' : '저장'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleCancelEdit} disabled={saving}>
                취소
              </button>
            </div>
          </section>
        ) : null}
        {recipients.length === 0 ? <p className="text-muted">저장된 주소지가 없습니다.</p> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {recipients.map((item) => (
              <div key={item.id} style={{ display: 'flex', gap: '1rem', alignItems: 'center', padding: '1rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                <div style={{ flex: 1 }}>
                  <h4 style={{ marginBottom: '0.35rem' }}>{item.label}</h4>
                  <p className="text-muted" style={{ margin: 0 }}>
                    {item.recipient_name} · {item.recipient_phone}<br />
                    [{item.zipcode}] {item.addr1} {item.addr2}
                  </p>
                </div>
                <button type="button" className="btn btn-primary" onClick={() => handleEdit(item)}>수정</button>
                <button type="button" className="btn btn-secondary" onClick={() => void handleDelete(item.id, item.label)}>삭제</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
