'use client';

import { useCallback, useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  createKpostPickup,
  deleteSavedRecipient,
  getKpostPickupMeta,
  listSavedRecipients,
  previewKpostPickup,
  saveRecipient,
  type KpostPickupBoxSize,
  type KpostPickupPayload,
  type KpostPickupPreview,
  type SavedRecipient,
} from '@/lib/api';

declare global {
  interface Window {
    daum?: {
      Postcode: new (opts: {
        oncomplete: (data: { zonecode: string; roadAddress: string; jibunAddress: string }) => void;
      }) => { open: () => void };
    };
  }
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
};

function parseApiError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    /* ignore */
  }
  return raw;
}

function emptyForm(defaultDate = ''): KpostPickupPayload {
  return {
    recipient_name: '',
    recipient_phone: '',
    zipcode: '',
    addr1: '',
    addr2: '',
    pickup_date: defaultDate,
    goods_name: '해외배송 물품',
    box_size: 'DEFAULT',
    box_quantity: 1,
    notes: '',
    test_mode: false,
  };
}

export default function ReturnRequestPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [liveReady, setLiveReady] = useState(false);
  const [centerLabel, setCenterLabel] = useState('스프링풀필먼트 · 동대구우체국');
  const [officeSer, setOfficeSer] = useState('260940699');
  const [boxSizes, setBoxSizes] = useState<KpostPickupBoxSize[]>([]);
  const [form, setForm] = useState<KpostPickupPayload>(emptyForm());
  const [preview, setPreview] = useState<KpostPickupPreview | null>(null);
  const [savedRecipients, setSavedRecipients] = useState<SavedRecipient[]>([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveLabel, setSaveLabel] = useState('');


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
        const [meta, recipients] = await Promise.all([
          getKpostPickupMeta(stored),
          listSavedRecipients(stored),
        ]);
        setLiveReady(meta.live_ready);
        setBoxSizes(meta.box_sizes || []);
        setCenterLabel(`${meta.center.name} · ${meta.center.addr}`);
        if (meta.office_ser) setOfficeSer(meta.office_ser);
        setForm(emptyForm(meta.default_pickup_date));
        setSavedRecipients(recipients.items || []);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function openPostcode() {
    const run = () => {
      if (!window.daum?.Postcode) return;
      new window.daum.Postcode({
        oncomplete(data) {
          setPreview(null);
          setForm((prev) => ({
            ...prev,
            zipcode: data.zonecode,
            addr1: data.roadAddress || data.jibunAddress,
          }));
        },
      }).open();
    };
    if (window.daum?.Postcode) {
      run();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';
    script.onload = run;
    document.body.appendChild(script);
  }

  async function handlePreview() {
    setError(null);
    setSuccess(null);
    try {
      const data = await previewKpostPickup(token, form);
      setPreview(data.preview);
    } catch (err) {
      setPreview(null);
      setError(parseApiError(err));
    }
  }

  async function handleSubmit() {
    if (!preview) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await createKpostPickup(token, form);
      if (result.duplicate_guard) {
        setSuccess(result.message || `기존 송장 ${result.tracking_no} 를 반환했습니다.`);
      } else {
        const mode = result.is_test ? '테스트 접수' : '우체국 접수';
        setSuccess(`${mode} 완료. 송장 ${result.tracking_no}`);
      }
      setPreview(null);
      setForm((prev) => emptyForm(prev.pickup_date));
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  function loadRecipient(recipient: SavedRecipient) {
    setPreview(null);
    setForm((prev) => ({
      ...prev,
      recipient_name: recipient.recipient_name,
      recipient_phone: recipient.recipient_phone,
      zipcode: recipient.zipcode,
      addr1: recipient.addr1,
      addr2: recipient.addr2,
    }));
  }

  async function handleSaveRecipient() {
    if (!saveLabel.trim()) {
      setError('라벨을 입력해주세요.');
      return;
    }
    if (!form.recipient_name.trim() || !form.recipient_phone.trim() || !form.zipcode.trim() || !form.addr1.trim()) {
      setError('수취인 정보를 모두 입력해주세요.');
      return;
    }
    setError(null);
    try {
      await saveRecipient(token, {
        label: saveLabel.trim(),
        recipient_name: form.recipient_name,
        recipient_phone: form.recipient_phone,
        zipcode: form.zipcode,
        addr1: form.addr1,
        addr2: form.addr2,
      });
      const recipients = await listSavedRecipients(token);
      setSavedRecipients(recipients.items || []);
      setSuccess(`'${saveLabel.trim()}' 수취인을 저장했습니다.`);
      setShowSaveDialog(false);
      setSaveLabel('');
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleDeleteRecipient(id: number, label: string) {
    if (!window.confirm(`'${label}' 수취인을 삭제할까요?`)) return;
    setError(null);
    try {
      await deleteSavedRecipient(token, id);
      const recipients = await listSavedRecipients(token);
      setSavedRecipients(recipients.items || []);
      setSuccess(`'${label}' 수취인을 삭제했습니다.`);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="회수신청 로딩 중..." />;

  return (
    <div>
      <PageHeader
        title="회수신청"
        subtitle="Infront 고객 수거지로 우체국 방문수거를 접수합니다. 도착지는 동대구우체국, 공급지는 스프링풀필먼트입니다."
      />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title="접수 정보">
        <p className="text-muted" style={{ marginBottom: '1rem' }}>
          {liveReady
            ? `실접수 가능 · 공급지 ${officeSer} · 도착 ${centerLabel}`
            : `우체국 키가 없어 테스트 접수로 저장됩니다. 공급지 ${officeSer} · 도착 ${centerLabel}`}
        </p>
        {savedRecipients.length > 0 && (
          <div style={{ marginBottom: '1rem' }}>
            <label className="text-muted" style={{ fontSize: '0.85rem' }}>
              저장된 수취인
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem' }}>
              {savedRecipients.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => loadRecipient(r)}
                  style={{ fontSize: '0.85rem', padding: '0.4rem 0.7rem' }}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <label>
            수취인 이름
            <input
              style={inputStyle}
              value={form.recipient_name}
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, recipient_name: e.target.value }));
              }}
            />
          </label>
          <label>
            연락처
            <input
              style={inputStyle}
              value={form.recipient_phone}
              placeholder="01012345678"
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, recipient_phone: e.target.value }));
              }}
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
              placeholder="예: 201호, 제3층"
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, addr2: e.target.value }));
              }}
            />
          </label>
          <label>
            수거 희망일
            <input
              type="date"
              style={inputStyle}
              value={form.pickup_date}
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, pickup_date: e.target.value }));
              }}
            />
          </label>
          <label>
            품명
            <input
              style={inputStyle}
              value={form.goods_name}
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, goods_name: e.target.value }));
              }}
            />
          </label>
          <label>
            박스 규격
            <select
              style={inputStyle}
              value={form.box_size}
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, box_size: e.target.value }));
              }}
            >
              {boxSizes.map((box) => (
                <option key={box.code} value={box.code}>
                  {box.label} · {box.desc}
                </option>
              ))}
            </select>
          </label>
          <label>
            박스 수량
            <input
              type="number"
              min="1"
              max="99"
              style={inputStyle}
              value={form.box_quantity || 1}
              onChange={(e) => {
                setPreview(null);
                const val = Math.max(1, Math.min(99, parseInt(e.target.value) || 1));
                setForm((p) => ({ ...p, box_quantity: val }));
              }}
            />
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            수거 메모
            <input
              style={inputStyle}
              value={form.notes}
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, notes: e.target.value }));
              }}
            />
          </label>
        </div>
        {liveReady && (
          <label style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={!!form.test_mode}
              onChange={(e) => {
                setPreview(null);
                setForm((p) => ({ ...p, test_mode: e.target.checked }));
              }}
            />
            테스트 접수 (우체국에 실제 신청하지 않음)
          </label>
        )}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-secondary" onClick={handlePreview}>
            미리보기
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowSaveDialog(true)}
            disabled={!form.recipient_name.trim() || !form.zipcode.trim()}
          >
            수취인 저장
          </button>
        </div>
      </Card>

      {showSaveDialog && (
        <Card title="수취인 저장">
          <label>
            라벨 (예: 홍길동 강남점)
            <input
              style={inputStyle}
              value={saveLabel}
              onChange={(e) => setSaveLabel(e.target.value)}
              placeholder="수취인을 구분할 이름"
              maxLength={50}
            />
          </label>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="btn btn-primary" onClick={handleSaveRecipient}>
              저장
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setShowSaveDialog(false);
                setSaveLabel('');
              }}
            >
              취소
            </button>
          </div>
        </Card>
      )}

      {preview && (
        <Card title="접수 확인">
          <p style={{ marginBottom: '0.75rem' }}>
            아래 내용으로 {preview.is_test ? '테스트 저장' : '우체국 실접수'}합니다. 맞으면 접수를 눌러주세요.
          </p>
          <div className="table-container">
            <table>
              <tbody>
                {[
                  ['수취인', `${preview.recipient_name} / ${preview.recipient_phone}`],
                  ['수거지', `[${preview.zipcode}] ${preview.addr1} ${preview.addr2}`],
                  ['수거일', preview.pickup_date],
                  ['품명/규격', `${preview.goods_name} · ${preview.box_label}`],
                  ['도착', `${preview.center_name} · ${preview.center_addr}`],
                  ['공급지코드', preview.office_ser || officeSer],
                  ['메모', preview.notes || '-'],
                ].map(([label, value]) => (
                  <tr key={label}>
                    <th style={{ width: '120px' }}>{label}</th>
                    <td>{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="btn btn-primary" disabled={saving} onClick={handleSubmit}>
              {saving ? '접수 중...' : preview.is_test ? '테스트 접수' : '회수신청 접수'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setPreview(null)}>
              취소
            </button>
          </div>
        </Card>
      )}

      <Card title="접수 내역 확인">
        <p className="text-muted" style={{ marginBottom: '1rem' }}>
          회수신청 접수 내역을 조회하고 관리하려면 접수목록 페이지를 이용하세요.
        </p>
        <a href="/kpost-pickup-list" className="btn btn-primary">
          접수목록 보기
        </a>
      </Card>
    </div>
  );
}
