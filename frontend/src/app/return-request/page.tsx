'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  createKpostPickup,
  getKpostPickupMeta,
  listSavedRecipients,
  saveRecipient,
  type KpostPickupBoxSize,
  type KpostPickupPayload,
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

function emptyForm(defaultDate = ''): KpostPickupPayload {
  return {
    recipient_name: '',
    recipient_phone: '',
    zipcode: '',
    addr1: '',
    addr2: '',
    pickup_date: defaultDate,
    goods_name: '의류',
    box_size: 'MICRO',
    box_quantity: 1,
    notes: '',
    test_mode: false,
  };
}

function applySavedRecipientToForm(
  prev: KpostPickupPayload,
  recipient: SavedRecipient,
): KpostPickupPayload {
  return {
    ...prev,
    recipient_name: recipient.recipient_name,
    recipient_phone: recipient.recipient_phone,
    zipcode: recipient.zipcode,
    addr1: recipient.addr1,
    addr2: recipient.addr2 || '',
  };
}

function saveAliasError(
  saveAddress: boolean,
  alias: string,
  existingLabels: string[],
): string | null {
  if (!saveAddress) return null;
  const label = alias.trim();
  if (!label) return '주소지를 저장하려면 별칭을 입력해주세요.';
  if (label.length > 50) return '별칭은 50자 이하여야 합니다.';
  if (existingLabels.includes(label)) {
    return `'${label}' 별칭이 이미 있습니다. 다른 별칭을 입력해주세요.`;
  }
  return null;
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
  const [savedRecipients, setSavedRecipients] = useState<SavedRecipient[]>([]);
  const [selectedSavedId, setSelectedSavedId] = useState('');
  const [saveAddress, setSaveAddress] = useState(false);
  const [addressAlias, setAddressAlias] = useState('');


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

  function applySavedById(id: string) {
    if (!id) {
      setSelectedSavedId('');
      return;
    }
    const recipient = savedRecipients.find((item) => String(item.id) === id);
    if (!recipient) return;
    setSelectedSavedId(id);
    setForm((prev) => applySavedRecipientToForm(prev, recipient));
  }

  function updateForm<K extends keyof KpostPickupPayload>(key: K, value: KpostPickupPayload[K]) {
    setSelectedSavedId('');
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function openPostcode() {
    const run = () => {
      if (!window.daum?.Postcode) return;
      new window.daum.Postcode({
        oncomplete(data) {

          setSelectedSavedId('');
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

  async function handleSubmit() {
    const aliasErr = saveAliasError(
      saveAddress,
      addressAlias,
      savedRecipients.map((item) => item.label),
    );
    if (aliasErr) {
      setError(aliasErr);
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await createKpostPickup(token, form);
      let extra = '';
      if (saveAddress) {
        const label = addressAlias.trim();
        try {
          await saveRecipient(token, {
            label,
            recipient_name: form.recipient_name,
            recipient_phone: form.recipient_phone,
            zipcode: form.zipcode,
            addr1: form.addr1,
            addr2: form.addr2,
          });
          extra = ` · 주소지 '${label}' 저장됨`;
          const refreshed = await listSavedRecipients(token);
          setSavedRecipients(refreshed.items || []);
        } catch (err) {
          extra = ` · 접수는 완료됐지만 주소지 저장 실패: ${parseApiError(err)}`;
        }
      }
      if (result.duplicate_guard) {
        setSuccess((result.message || `기존 송장 ${result.tracking_no} 를 반환했습니다.`) + extra);
      } else {
        const mode = result.is_test ? '테스트 접수' : '우체국 접수';
        setSuccess(`${mode} 완료. 송장 ${result.tracking_no}${extra}`);
      }
      setSelectedSavedId('');
      setSaveAddress(false);
      setAddressAlias('');
      setForm((prev) => emptyForm(prev.pickup_date));
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading text="회수신청 로딩 중..." />;

  return (
    <div>
      <PageHeader
        title="회수신청"
        subtitle="고객 수거지로 우체국 방문수거를 접수합니다. 도착지는 동대구우체국, 공급지는 스프링풀필먼트입니다."
      />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title="접수 정보">
        <p className="text-muted" style={{ marginBottom: '1rem' }}>
          {liveReady
            ? `실접수 가능 · 공급지 ${officeSer} · 도착 ${centerLabel}`
            : `우체국 키가 없어 테스트 접수로 저장됩니다. 공급지 ${officeSer} · 도착 ${centerLabel}`}
        </p>
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <label style={{ flex: '1 1 240px' }}>
              저장된 주소지 별칭
              <select
                style={inputStyle}
                value={selectedSavedId}
                onChange={(e) => applySavedById(e.target.value)}
                disabled={savedRecipients.length === 0}
              >
                <option value="">
                  {savedRecipients.length === 0
                    ? '저장된 주소지가 없습니다'
                    : '별칭을 선택하면 접수정보가 자동입력됩니다'}
                </option>
                {savedRecipients.map((r) => (
                  <option key={r.id} value={String(r.id)}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
            <a href="/saved-recipients" className="btn btn-secondary" style={{ fontSize: '0.85rem' }}>
              저장된 주소지 관리
            </a>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <label>
            수취인 이름
            <input
              style={inputStyle}
              value={form.recipient_name}
              onChange={(e) => updateForm('recipient_name', e.target.value)}
            />
          </label>
          <label>
            연락처
            <input
              style={inputStyle}
              value={form.recipient_phone}
              placeholder="01012345678"
              onChange={(e) => updateForm('recipient_phone', e.target.value)}
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
              onChange={(e) => updateForm('addr2', e.target.value)}
            />
          </label>
          <label>
            수거 희망일
            <input
              type="date"
              style={inputStyle}
              value={form.pickup_date}
              onChange={(e) => {
      
                setForm((p) => ({ ...p, pickup_date: e.target.value }));
              }}
            />
          </label>
          <label>
            품명
            <select
              style={inputStyle}
              value={form.goods_name}
              onChange={(e) => {
      
                setForm((p) => ({ ...p, goods_name: e.target.value }));
              }}
            >
              <option value="의류">의류</option>
              <option value="화장품">화장품</option>
              <option value="악세사리">악세사리</option>
              <option value="기타">기타</option>
            </select>
          </label>
          <label>
            박스 규격
            <select
              style={inputStyle}
              value={form.box_size}
              onChange={(e) => {
      
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
                setForm((p) => ({ ...p, notes: e.target.value }));
              }}
            />
          </label>
        </div>
        <div
          style={{
            marginTop: '0.9rem',
            padding: '0.85rem',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            background: 'var(--bg-secondary, #f8f9fa)',
          }}
        >
          <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={saveAddress}
              onChange={(e) => {
                const checked = e.target.checked;
                setSaveAddress(checked);
                if (!checked) setAddressAlias('');
              }}
            />
            해당 정보 저장하기
          </label>
          {saveAddress && (
            <label style={{ display: 'block', marginTop: '0.7rem' }}>
              주소지 별칭
              <input
                style={inputStyle}
                value={addressAlias}
                placeholder="예: 본사, 경기창고"
                maxLength={50}
                onChange={(e) => {
                  setAddressAlias(e.target.value);
                }}
              />
            </label>
          )}
        </div>
        {liveReady && (
          <label style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={!!form.test_mode}
              onChange={(e) => {
                setForm((p) => ({ ...p, test_mode: e.target.checked }));
              }}
            />
            테스트 접수 (우체국에 실제 신청하지 않음)
          </label>
        )}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
            {saving ? '접수 중...' : liveReady && !form.test_mode ? '회수신청 접수' : '테스트 접수'}
          </button>
          {saving && (
            <p className="text-muted" style={{ margin: 0, fontSize: '0.85rem' }}>
              우체국에 접수 요청 중입니다. 18초 안에 성공 또는 오류가 표시됩니다.
            </p>
          )}
        </div>
      </Card>

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
