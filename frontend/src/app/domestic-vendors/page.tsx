'use client';

import { useEffect, useState } from 'react';
import Alert from '@/components/Alert';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  deleteDomesticVendor,
  listDomesticVendors,
  saveDomesticVendor,
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

const empty = {
  name: '',
  office_ser: '',
  sender_name: '',
  sender_phone: '',
  sender_zip: '',
  sender_addr1: '',
  sender_addr2: '',
};

export default function DomesticVendorsPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<DomesticVendor[]>([]);
  const [form, setForm] = useState(empty);
  const [editId, setEditId] = useState<number | null>(null);

  async function load(tok: string) {
    const res = await listDomesticVendors(tok);
    setItems(res.items || []);
  }

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    load(stored).catch((err) => setError(parseApiError(err))).finally(() => setLoading(false));
  }, []);

  function setField(key: keyof typeof empty, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await saveDomesticVendor(token, form, editId || undefined);
      setForm(empty);
      setEditId(null);
      setSuccess(editId ? '업체를 수정했습니다.' : '업체를 등록했습니다.');
      await load(token);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: DomesticVendor) {
    if (!window.confirm(`${item.name} 업체를 삭제할까요? 이미 접수한 송장은 그대로 남습니다.`)) return;
    try {
      await deleteDomesticVendor(token, item.id);
      if (editId === item.id) {
        setEditId(null);
        setForm(empty);
      }
      await load(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="출고 업체를 불러오는 중..." />;

  return (
    <div className="domestic-form">
      <PageHeader title="출고 업체" />
      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      <Card>
        <div className="domestic-row">
          <label className="domestic-field w-name">업체명<input value={form.name} onChange={(e) => setField('name', e.target.value)} /></label>
          <label className="domestic-field w-office">공급지번호<input value={form.office_ser} onChange={(e) => setField('office_ser', e.target.value)} /></label>
        </div>
        <div className="domestic-row">
          <label className="domestic-field w-name">보내는 사람<input value={form.sender_name} onChange={(e) => setField('sender_name', e.target.value)} /></label>
          <label className="domestic-field w-phone">전화<input value={form.sender_phone} onChange={(e) => setField('sender_phone', e.target.value)} /></label>
          <label className="domestic-field w-zip">우편번호<input value={form.sender_zip} onChange={(e) => setField('sender_zip', e.target.value)} /></label>
        </div>
        <div className="domestic-row">
          <label className="domestic-field w-addr">주소<input value={form.sender_addr1} onChange={(e) => setField('sender_addr1', e.target.value)} /></label>
          <label className="domestic-field w-detail">상세<input value={form.sender_addr2} onChange={(e) => setField('sender_addr2', e.target.value)} /></label>
        </div>
        <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void handleSave()}>
          {saving ? '저장 중...' : '저장'}
        </button>
        {editId && (
          <button type="button" className="btn btn-secondary" style={{ marginLeft: 8 }} onClick={() => { setEditId(null); setForm(empty); }}>
            취소
          </button>
        )}
      </Card>
      <Card>
        {items.length === 0 ? <p className="text-muted">등록된 업체가 없습니다.</p> : (
          <table>
            <thead>
              <tr><th>업체</th><th>공급지번호</th><th>보내는 사람</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.name}</td>
                  <td style={{ fontFamily: 'monospace' }}>{item.office_ser}</td>
                  <td>{item.sender_name} · {item.sender_phone}</td>
                  <td>
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
                    }}>수정</button>
                    <button type="button" className="btn btn-secondary" style={{ marginLeft: 6 }} onClick={() => void handleDelete(item)}>삭제</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
