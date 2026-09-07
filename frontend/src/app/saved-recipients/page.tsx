'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  deleteSavedRecipient,
  listSavedRecipients,
  saveRecipient,
  updateSavedRecipient,
  type SavedRecipient,
  type SavedRecipientPayload,
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

export default function SavedRecipientsPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [recipients, setRecipients] = useState<SavedRecipient[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<SavedRecipientPayload>({
    label: '',
    recipient_name: '',
    recipient_phone: '',
    zipcode: '',
    addr1: '',
    addr2: '',
  });

  async function loadRecipients(auth: string) {
    const data = await listSavedRecipients(auth);
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
    (async () => {
      try {
        await loadRecipients(stored);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function openPostcode() {
    if (!window.daum?.Postcode) {
      setError('다음 주소 검색 API를 로드하지 못했습니다.');
      return;
    }
    new window.daum.Postcode({
      oncomplete: (data) => {
        setForm((prev) => ({
          ...prev,
          zipcode: data.zonecode,
          addr1: data.roadAddress || data.jibunAddress,
        }));
      },
    }).open();
  }

  async function handleSave() {
    setError(null);
    setSuccess(null);
    if (!form.label.trim()) {
      setError('별칭을 입력해주세요.');
      return;
    }
    if (!form.recipient_name.trim()) {
      setError('수취인 이름을 입력해주세요.');
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
        await updateSavedRecipient(token, editingId, form);
        setSuccess(`'${form.label}' 수취인을 수정했습니다.`);
      } else {
        await saveRecipient(token, form);
        setSuccess(`'${form.label}' 수취인을 저장했습니다.`);
      }
      setForm({
        label: '',
        recipient_name: '',
        recipient_phone: '',
        zipcode: '',
        addr1: '',
        addr2: '',
      });
      setShowAddForm(false);
      setEditingId(null);
      await loadRecipients(token);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  function handleEdit(recipient: SavedRecipient) {
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
    setForm({
      label: '',
      recipient_name: '',
      recipient_phone: '',
      zipcode: '',
      addr1: '',
      addr2: '',
    });
    setShowAddForm(false);
    setEditingId(null);
    setError(null);
  }

  async function handleDelete(id: number, label: string) {
    if (!window.confirm(`'${label}' 수취인을 삭제할까요?`)) return;
    setError(null);
    setSuccess(null);
    try {
      await deleteSavedRecipient(token, id);
      setSuccess(`'${label}' 수취인을 삭제했습니다.`);
      await loadRecipients(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="저장된 주소지 로딩 중..." />;

  return (
    <div>
      <PageHeader
        title="저장된 주소지"
        subtitle="자주 사용하는 수취인 정보를 저장하고 관리합니다."
      />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title="저장된 수취인">
        <div style={{ marginBottom: '1rem' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setShowAddForm(!showAddForm)}
            disabled={saving}
          >
            {showAddForm ? '취소' : '새 주소지 추가'}
          </button>
        </div>

        {showAddForm && (
          <div
            style={{
              marginBottom: '1.5rem',
              padding: '1rem',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-secondary)',
            }}
          >
            <h4 style={{ marginBottom: '1rem' }}>{editingId ? '주소지 수정' : '새 주소지 추가'}</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <label style={{ gridColumn: '1 / -1' }}>
                별칭 (예: 본사, 경기창고)
                <input
                  style={inputStyle}
                  value={form.label}
                  placeholder="별칭 입력"
                  onChange={(e) => setForm((p) => ({ ...p, label: e.target.value }))}
                />
              </label>
              <label>
                수취인 이름
                <input
                  style={inputStyle}
                  value={form.recipient_name}
                  onChange={(e) => setForm((p) => ({ ...p, recipient_name: e.target.value }))}
                />
              </label>
              <label>
                연락처
                <input
                  style={inputStyle}
                  value={form.recipient_phone}
                  placeholder="01012345678"
                  onChange={(e) => setForm((p) => ({ ...p, recipient_phone: e.target.value }))}
                />
              </label>
              <div style={{ gridColumn: '1 / -1' }}>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
                  <label style={{ flex: '0 0 120px' }}>
                    우편번호
                    <input style={inputStyle} value={form.zipcode} readOnly />
                  </label>
                  <label style={{ flex: 1 }}>
                    도로명 주소
                    <input style={inputStyle} value={form.addr1} readOnly />
                  </label>
                  <button type="button" className="btn btn-secondary" onClick={openPostcode}>
                    주소 검색
                  </button>
                </div>
              </div>
              <label style={{ gridColumn: '1 / -1' }}>
                상세주소 (동·호·층)
                <input
                  style={inputStyle}
                  value={form.addr2}
                  placeholder="예: 3층, 201호, 제3층"
                  onChange={(e) => setForm((p) => ({ ...p, addr2: e.target.value }))}
                />
              </label>
            </div>
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? '저장 중...' : editingId ? '수정' : '저장'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleCancelEdit}
                disabled={saving}
              >
                취소
              </button>
            </div>
          </div>
        )}

        {recipients.length === 0 ? (
          <p className="text-muted">저장된 주소지가 없습니다.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {recipients.map((r) => (
              <div
                key={r.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  padding: '1rem',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  backgroundColor: 'var(--bg-secondary)',
                }}
              >
                <div style={{ flex: 1 }}>
                  <h4 style={{ marginBottom: '0.5rem' }}>{r.label}</h4>
                  <div className="text-muted" style={{ fontSize: '0.9rem' }}>
                    <div>{r.recipient_name} · {r.recipient_phone}</div>
                    <div>
                      [{r.zipcode}] {r.addr1} {r.addr2}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleEdit(r)}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    수정
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => handleDelete(r.id, r.label)}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    삭제
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
