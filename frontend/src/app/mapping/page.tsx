'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';
import {
  saveVendor,
  getAvailableAliases,
  getUnmatchedAliases,
  UnmatchedAlias,
} from '@/lib/api';

const SKU_OPTS = ['≤100', '≤300', '≤500', '≤1,000', '≤2,000', '>2,000'];
const YES_NO = ['YES', 'NO'];
const RATE_TYPES = ['A', 'STD'];

const FILE_TYPE_NAMES: Record<string, string> = {
  inbound_slip: '입고전표',
  shipping_stats: '배송통계',
  kpost_in: '우체국접수',
  kpost_ret: '우체국반품',
  work_log: '작업일지',
};

export default function MappingPage() {
  // 폼 상태
  const [vendorPk, setVendorPk] = useState('');
  const [name, setName] = useState('');
  const [rateType, setRateType] = useState('A');
  const [skuGroup, setSkuGroup] = useState('≤100');
  const [active, setActive] = useState('YES');
  const [barcodeF, setBarcodeF] = useState('NO');
  const [custboxF, setCustboxF] = useState('NO');
  const [voidF, setVoidF] = useState('NO');
  const [ppBagF, setPpBagF] = useState('NO');
  const [mailerF, setMailerF] = useState('NO');
  const [videoOutF, setVideoOutF] = useState('NO');
  const [videoRetF, setVideoRetF] = useState('NO');

  // 별칭 선택
  const [aliasInbound, setAliasInbound] = useState<string[]>([]);
  const [aliasShipping, setAliasShipping] = useState<string[]>([]);
  const [aliasKpostIn, setAliasKpostIn] = useState<string[]>([]);
  const [aliasKpostRet, setAliasKpostRet] = useState<string[]>([]);
  const [aliasWorkLog, setAliasWorkLog] = useState<string[]>([]);

  // 사용 가능한 별칭 목록
  const [availableInbound, setAvailableInbound] = useState<string[]>([]);
  const [availableShipping, setAvailableShipping] = useState<string[]>([]);
  const [availableKpostIn, setAvailableKpostIn] = useState<string[]>([]);
  const [availableKpostRet, setAvailableKpostRet] = useState<string[]>([]);
  const [availableWorkLog, setAvailableWorkLog] = useState<string[]>([]);

  // 미매칭 별칭
  const [unmatchedAliases, setUnmatchedAliases] = useState<UnmatchedAlias[]>([]);

  // UI 상태
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 초기 데이터 로드
  useEffect(() => {
    loadAvailableAliases();
    loadUnmatchedAliases();
  }, []);

  async function loadAvailableAliases() {
    try {
      setLoading(true);
      const [inbound, shipping, kpostIn, kpostRet, workLog] = await Promise.all([
        getAvailableAliases('inbound_slip'),
        getAvailableAliases('shipping_stats'),
        getAvailableAliases('kpost_in'),
        getAvailableAliases('kpost_ret'),
        getAvailableAliases('work_log'),
      ]);
      setAvailableInbound(inbound);
      setAvailableShipping(shipping);
      setAvailableKpostIn(kpostIn);
      setAvailableKpostRet(kpostRet);
      setAvailableWorkLog(workLog);
    } catch (err) {
      console.error('Failed to load aliases:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadUnmatchedAliases() {
    try {
      const data = await getUnmatchedAliases();
      setUnmatchedAliases(data);
    } catch (err) {
      console.error('Failed to load unmatched aliases:', err);
    }
  }

  async function handleSave() {
    if (!vendorPk.trim()) {
      setError('거래처명(PK)를 입력하세요.');
      return;
    }
    if (!name.trim()) {
      setError('거래처명(표준)을 입력하세요.');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await saveVendor({
        vendor: vendorPk.trim(),
        name: name.trim(),
        rate_type: rateType,
        sku_group: skuGroup,
        active,
        barcode_f: barcodeF,
        custbox_f: custboxF,
        void_f: voidF,
        pp_bag_f: ppBagF,
        mailer_f: mailerF,
        video_out_f: videoOutF,
        video_ret_f: videoRetF,
        alias_inbound_slip: aliasInbound,
        alias_shipping_stats: aliasShipping,
        alias_kpost_in: aliasKpostIn,
        alias_kpost_ret: aliasKpostRet,
        alias_work_log: aliasWorkLog,
      });

      setSuccess(
        `거래처 '${result.vendor}' ${result.action === 'created' ? '신규 등록' : '업데이트'} 완료!`
      );

      // 폼 초기화
      setVendorPk('');
      setName('');
      setAliasInbound([]);
      setAliasShipping([]);
      setAliasKpostIn([]);
      setAliasKpostRet([]);
      setAliasWorkLog([]);

      // 별칭 목록 새로고침
      loadAvailableAliases();
      loadUnmatchedAliases();
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  function MultiSelect({
    label,
    options,
    selected,
    onChange,
  }: {
    label: string;
    options: string[];
    selected: string[];
    onChange: (values: string[]) => void;
  }) {
    return (
      <div style={{ marginBottom: '1rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
          {label}
        </label>
        <select
          multiple
          value={selected}
          onChange={(e) => {
            const values = Array.from(e.target.selectedOptions, (opt) => opt.value);
            onChange(values);
          }}
          style={{
            width: '100%',
            minHeight: '120px',
            padding: '0.5rem',
            border: '1px solid #ddd',
            borderRadius: '4px',
          }}
        >
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        <small style={{ color: '#666' }}>Ctrl+클릭으로 여러 개 선택</small>
      </div>
    );
  }

  function SelectField({
    label,
    value,
    options,
    onChange,
  }: {
    label: string;
    value: string;
    options: string[];
    onChange: (v: string) => void;
  }) {
    return (
      <div style={{ marginBottom: '1rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
          {label}
        </label>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: '100%',
            padding: '0.5rem',
            border: '1px solid #ddd',
            borderRadius: '4px',
          }}
        >
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (loading) {
    return <Loading />;
  }

  const totalUnmatched = unmatchedAliases.reduce((sum, u) => sum + u.count, 0);

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>거래처 매핑 관리</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      <Card title="신규 공급처 등록">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
              거래처명 (PK)
            </label>
            <input
              type="text"
              value={vendorPk}
              onChange={(e) => setVendorPk(e.target.value)}
              placeholder="DB에 저장될 고유 키"
              style={{
                width: '100%',
                padding: '0.5rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
              거래처명 (표준)
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="표시용 이름"
              style={{
                width: '100%',
                padding: '0.5rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            />
          </div>
        </div>

        <h3 style={{ marginTop: '2rem', marginBottom: '1rem' }}>별칭 매핑</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <MultiSelect
            label="입고전표 별칭"
            options={availableInbound}
            selected={aliasInbound}
            onChange={setAliasInbound}
          />
          <MultiSelect
            label="배송통계 별칭"
            options={availableShipping}
            selected={aliasShipping}
            onChange={setAliasShipping}
          />
          <MultiSelect
            label="우체국접수 별칭"
            options={availableKpostIn}
            selected={aliasKpostIn}
            onChange={setAliasKpostIn}
          />
          <MultiSelect
            label="우체국반품 별칭"
            options={availableKpostRet}
            selected={aliasKpostRet}
            onChange={setAliasKpostRet}
          />
          <MultiSelect
            label="작업일지 별칭"
            options={availableWorkLog}
            selected={aliasWorkLog}
            onChange={setAliasWorkLog}
          />
        </div>

        <h3 style={{ marginTop: '2rem', marginBottom: '1rem' }}>설정</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
          <SelectField label="활성 상태" value={active} options={YES_NO} onChange={setActive} />
          <SelectField label="요금타입" value={rateType} options={RATE_TYPES} onChange={setRateType} />
          <SelectField label="바코드 부착" value={barcodeF} options={YES_NO} onChange={setBarcodeF} />
          <SelectField label="박스" value={custboxF} options={YES_NO} onChange={setCustboxF} />
          <SelectField label="완충재" value={voidF} options={YES_NO} onChange={setVoidF} />
          <SelectField label="PP 봉투" value={ppBagF} options={YES_NO} onChange={setPpBagF} />
          <SelectField label="택배 봉투" value={mailerF} options={YES_NO} onChange={setMailerF} />
          <SelectField label="대표 SKU 구간" value={skuGroup} options={SKU_OPTS} onChange={setSkuGroup} />
          <SelectField label="출고영상촬영" value={videoOutF} options={YES_NO} onChange={setVideoOutF} />
          <SelectField label="반품영상촬영" value={videoRetF} options={YES_NO} onChange={setVideoRetF} />
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            marginTop: '2rem',
            padding: '0.75rem 2rem',
            backgroundColor: '#4CAF50',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: saving ? 'not-allowed' : 'pointer',
            fontSize: '1rem',
          }}
        >
          {saving ? '저장 중...' : '거래처 저장/업데이트'}
        </button>
      </Card>

      {/* 미매칭 Alias 섹션 */}
      <Card title="미매칭 Alias 현황" style={{ marginTop: '2rem' }}>
        {totalUnmatched === 0 ? (
          <p style={{ color: 'green' }}>모든 업로드 데이터가 정상 매핑되었습니다!</p>
        ) : (
          <>
            <p style={{ color: '#ff9800', marginBottom: '1rem' }}>
              미매칭 alias {totalUnmatched.toLocaleString()}건 발견
            </p>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>
                    파일 타입
                  </th>
                  <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #ddd' }}>
                    건수
                  </th>
                </tr>
              </thead>
              <tbody>
                {unmatchedAliases.map((item) => (
                  <tr key={item.file_type}>
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                      {FILE_TYPE_NAMES[item.file_type] || item.file_type}
                    </td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                      {item.count.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        <button
          onClick={() => {
            loadAvailableAliases();
            loadUnmatchedAliases();
          }}
          style={{
            marginTop: '1rem',
            padding: '0.5rem 1rem',
            backgroundColor: '#2196F3',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          새로고침
        </button>
      </Card>
    </div>
  );
}

