'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  deleteOverseasSavedHs,
  listOverseasSavedHs,
  saveOverseasHs,
  updateOverseasSavedHs,
  type OverseasSavedHs,
  type OverseasSavedHsPayload,
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

const emptyForm = (): OverseasSavedHsPayload => ({
  label: '',
  name_ko: '',
  name_en: '',
  hs_code: '',
  origin_country: 'KR',
  group_name: '저장품목',
});

export default function OverseasHsCodesPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<OverseasSavedHs[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<OverseasSavedHsPayload>(emptyForm());

  async function loadList(auth: string, q = '') {
    const data = await listOverseasSavedHs(auth, q);
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
        await updateOverseasSavedHs(token, editingId, form);
        setSuccess(`HS ${form.hs_code} 를 수정했습니다.`);
      } else {
        await saveOverseasHs(token, form);
        setSuccess(`HS ${form.hs_code} 를 저장했습니다.`);
      }
      setForm(emptyForm());
      setShowForm(false);
      setEditingId(null);
      await loadList(token, query);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  function handleEdit(item: OverseasSavedHs) {
    setForm({
      label: item.label,
      name_ko: item.name_ko,
      name_en: item.name_en,
      hs_code: item.hs_code,
      origin_country: item.origin_country,
      group_name: item.group_name,
    });
    setEditingId(item.id);
    setShowForm(true);
  }

  async function handleDelete(id: number, label: string) {
    if (!window.confirm(`'${label}' HS코드를 삭제할까요?`)) return;
    try {
      await deleteOverseasSavedHs(token, id);
      setSuccess(`'${label}' 을 삭제했습니다.`);
      await loadList(token, query);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="HS코드 목록 로딩 중..." />;

  return (
    <div className="overseas-page">
      <PageHeader title="해외배송 HS코드" subtitle="자주 쓰는 품목·HS 6자리를 저장하면 접수 인보이스 검색에서 바로 고를 수 있습니다." />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      <Card title={`저장 HS코드 · ${items.length}건`}>
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <input
            style={{ ...inputStyle, maxWidth: 280 }}
            value={query}
            placeholder="별칭, 품목명, HS코드 검색"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') loadList(token, query);
            }}
          />
          <button type="button" className="btn btn-secondary" onClick={() => loadList(token, query)}>검색</button>
          <button type="button" className="btn btn-primary" onClick={() => { setShowForm(!showForm); setEditingId(null); setForm(emptyForm()); }}>
            {showForm ? '취소' : '새 HS코드'}
          </button>
          <a href="/overseas-shipping" className="btn btn-secondary">접수 화면</a>
        </div>
        {showForm && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', border: '1px solid var(--border)', borderRadius: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <label>별칭<input style={inputStyle} value={form.label || ''} onChange={(e) => setForm((p) => ({ ...p, label: e.target.value }))} /></label>
              <label>HS코드 6자리<input style={inputStyle} value={form.hs_code} onChange={(e) => setForm((p) => ({ ...p, hs_code: e.target.value.replace(/\D/g, '').slice(0, 6) }))} /></label>
              <label>한글명<input style={inputStyle} value={form.name_ko || ''} onChange={(e) => setForm((p) => ({ ...p, name_ko: e.target.value }))} /></label>
              <label>영문명<input style={inputStyle} value={form.name_en} onChange={(e) => setForm((p) => ({ ...p, name_en: e.target.value }))} /></label>
              <label>원산지<input style={inputStyle} value={form.origin_country || 'KR'} onChange={(e) => setForm((p) => ({ ...p, origin_country: e.target.value.toUpperCase() }))} /></label>
              <label>그룹<input style={inputStyle} value={form.group_name || '저장품목'} onChange={(e) => setForm((p) => ({ ...p, group_name: e.target.value }))} /></label>
            </div>
            <div style={{ marginTop: '1rem' }}>
              <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? '저장 중...' : editingId ? '수정' : '저장'}
              </button>
            </div>
          </div>
        )}
        {items.length === 0 ? (
          <p className="text-muted">저장된 HS코드가 없습니다. 접수 화면에서 HS 저장을 누르면 여기에 쌓입니다.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {items.map((item) => (
              <div key={item.id} style={{ display: 'flex', gap: '1rem', padding: '1rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                <div style={{ flex: 1 }}>
                  <h4 style={{ marginBottom: '0.4rem' }}>{item.label} · HS {item.hs_code}</h4>
                  <div className="text-muted" style={{ fontSize: '0.9rem' }}>
                    {item.name_ko} · {item.name_en} · {item.origin_country} · {item.group_name}
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
