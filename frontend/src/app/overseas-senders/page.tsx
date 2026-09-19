'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  deleteOverseasSavedSender,
  listOverseasSavedSenders,
  saveOverseasSender,
  updateOverseasSavedSender,
  type OverseasSavedSender,
  type OverseasSavedSenderPayload,
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

const emptyForm = (): OverseasSavedSenderPayload => ({
  label: '',
  name: '',
  phone: '',
  zipcode: '',
  addr1: '',
  addr2: '',
  addr3: '',
  is_default: false,
});

export default function OverseasSendersPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<OverseasSavedSender[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<OverseasSavedSenderPayload>(emptyForm());

  async function loadList(auth: string) {
    const data = await listOverseasSavedSenders(auth);
    setItems(data.items || []);
  }

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
        await loadList(stored);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleSave() {
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      if (editingId) {
        await updateOverseasSavedSender(token, editingId, form);
        setSuccess(`'${form.label}' 발송인을 수정했습니다.`);
      } else {
        await saveOverseasSender(token, form);
        setSuccess(`'${form.label}' 발송인을 저장했습니다.`);
      }
      setForm(emptyForm());
      setShowForm(false);
      setEditingId(null);
      await loadList(token);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  function handleEdit(item: OverseasSavedSender) {
    setForm({
      label: item.label,
      name: item.name,
      phone: item.phone,
      zipcode: item.zipcode,
      addr1: item.addr1,
      addr2: item.addr2,
      addr3: item.addr3,
      is_default: item.is_default,
    });
    setEditingId(item.id);
    setShowForm(true);
  }

  async function handleDelete(id: number, label: string) {
    if (!window.confirm(`'${label}' 발송인을 삭제할까요?`)) return;
    try {
      await deleteOverseasSavedSender(token, id);
      setSuccess(`'${label}' 발송인을 삭제했습니다.`);
      await loadList(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="발송인 목록 로딩 중..." />;

  return (
    <div className="overseas-page">
      <PageHeader title="해외배송 발송인" subtitle="자주 쓰는 발송인 이름·주소·전화를 저장하고 접수 화면에서 선택합니다." />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      <Card title={`발송인 목록 · ${items.length}건`}>
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem' }}>
          <button type="button" className="btn btn-primary" onClick={() => { setShowForm(!showForm); setEditingId(null); setForm(emptyForm()); }}>
            {showForm ? '취소' : '새 발송인'}
          </button>
          <a href="/overseas-shipping" className="btn btn-secondary">접수 화면</a>
        </div>
        {showForm && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', border: '1px solid var(--border)', borderRadius: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <label>별칭<input style={inputStyle} value={form.label} onChange={(e) => setForm((p) => ({ ...p, label: e.target.value }))} /></label>
              <label>이름<input style={inputStyle} value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} /></label>
              <label>전화<input style={inputStyle} value={form.phone || ''} onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))} /></label>
              <label>우편번호<input style={inputStyle} value={form.zipcode || ''} onChange={(e) => setForm((p) => ({ ...p, zipcode: e.target.value }))} /></label>
              <label>시/도<input style={inputStyle} value={form.addr1 || ''} onChange={(e) => setForm((p) => ({ ...p, addr1: e.target.value }))} /></label>
              <label>구/군<input style={inputStyle} value={form.addr2 || ''} onChange={(e) => setForm((p) => ({ ...p, addr2: e.target.value }))} /></label>
              <label style={{ gridColumn: '1 / -1' }}>상세주소<input style={inputStyle} value={form.addr3 || ''} onChange={(e) => setForm((p) => ({ ...p, addr3: e.target.value }))} /></label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input type="checkbox" checked={!!form.is_default} onChange={(e) => setForm((p) => ({ ...p, is_default: e.target.checked }))} />
                기본 발송인
              </label>
            </div>
            <div style={{ marginTop: '1rem' }}>
              <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? '저장 중...' : editingId ? '수정' : '저장'}
              </button>
            </div>
          </div>
        )}
        {items.length === 0 ? (
          <p className="text-muted">저장된 발송인이 없습니다.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {items.map((item) => (
              <div key={item.id} style={{ display: 'flex', gap: '1rem', padding: '1rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                <div style={{ flex: 1 }}>
                  <h4 style={{ marginBottom: '0.4rem' }}>{item.is_default ? '[기본] ' : ''}{item.label}</h4>
                  <div className="text-muted" style={{ fontSize: '0.9rem' }}>
                    <div>{item.name} · {item.phone}</div>
                    <div>[{item.zipcode}] {item.addr1} {item.addr2} {item.addr3}</div>
                  </div>
                </div>
                <button type="button" className="btn btn-primary" onClick={() => handleEdit(item)}>수정</button>
                <button type="button" className="btn btn-secondary" onClick={() => handleDelete(item.id, item.label)}>삭제</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
