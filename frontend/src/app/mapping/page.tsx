'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';
import {
  saveVendor,
  getVendors,
  getVendor,
  getAvailableAliases,
  getAliasesForVendor,
  getUnmatchedAliases,
  getMappingSummary,
  UnmatchedAlias,
  Vendor,
  VendorDetail,
  MappingSummary,
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

const FILE_TYPES = ['inbound_slip', 'shipping_stats', 'kpost_in', 'kpost_ret', 'work_log'];

interface AliasOptions {
  mapped: string[];
  available: string[];
}

export default function MappingPage() {
  // 거래처 목록
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedVendorId, setSelectedVendorId] = useState<string>('');
  const [isEditMode, setIsEditMode] = useState(false);

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

  // 사용 가능한 별칭 목록 (신규 등록용)
  const [availableInbound, setAvailableInbound] = useState<string[]>([]);
  const [availableShipping, setAvailableShipping] = useState<string[]>([]);
  const [availableKpostIn, setAvailableKpostIn] = useState<string[]>([]);
  const [availableKpostRet, setAvailableKpostRet] = useState<string[]>([]);
  const [availableWorkLog, setAvailableWorkLog] = useState<string[]>([]);

  // 수정용 별칭 옵션 (매핑된 것 + 사용 가능한 것)
  const [editAliasOptions, setEditAliasOptions] = useState<Record<string, AliasOptions>>({});

  // 미매칭 별칭
  const [unmatchedAliases, setUnmatchedAliases] = useState<UnmatchedAlias[]>([]);

  // 매핑 현황
  const [mappingSummary, setMappingSummary] = useState<MappingSummary[]>([]);
  const [showMappingSummary, setShowMappingSummary] = useState(false);
  const [mappingFilter, setMappingFilter] = useState('');

  // UI 상태
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 초기 데이터 로드
  useEffect(() => {
    loadVendors();
    loadAvailableAliases();
    loadUnmatchedAliases();
  }, []);

  async function loadVendors() {
    try {
      const data = await getVendors();
      setVendors(data);
    } catch (err) {
      console.error('Failed to load vendors:', err);
    }
  }

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

  async function loadMappingSummary() {
    try {
      const data = await getMappingSummary();
      setMappingSummary(data);
    } catch (err) {
      console.error('Failed to load mapping summary:', err);
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

  // 거래처 선택 시 수정 모드로 전환
  async function handleSelectVendor(vendorId: string) {
    if (!vendorId) {
      resetForm();
      setIsEditMode(false);
      return;
    }

    try {
      setLoading(true);
      setSelectedVendorId(vendorId);
      setIsEditMode(true);

      // 거래처 상세 정보 로드
      const vendorDetail = await getVendor(vendorId);
      
      // 폼에 값 설정
      setVendorPk(vendorDetail.vendor);
      setName(vendorDetail.name || '');
      setRateType(vendorDetail.rate_type || 'A');
      setSkuGroup(vendorDetail.sku_group || '≤100');
      setActive(vendorDetail.active || 'YES');
      setBarcodeF(vendorDetail.barcode_f || 'NO');
      setCustboxF(vendorDetail.custbox_f || 'NO');
      setVoidF(vendorDetail.void_f || 'NO');
      setPpBagF(vendorDetail.pp_bag_f || 'NO');
      setMailerF(vendorDetail.mailer_f || 'NO');
      setVideoOutF(vendorDetail.video_out_f || 'NO');
      setVideoRetF(vendorDetail.video_ret_f || 'NO');

      // 현재 매핑된 별칭 설정
      setAliasInbound(vendorDetail.alias_inbound_slip || []);
      setAliasShipping(vendorDetail.alias_shipping_stats || []);
      setAliasKpostIn(vendorDetail.alias_kpost_in || []);
      setAliasKpostRet(vendorDetail.alias_kpost_ret || []);
      setAliasWorkLog(vendorDetail.alias_work_log || []);

      // 수정용 별칭 옵션 로드 (매핑된 것 + 사용 가능한 것)
      const aliasPromises = FILE_TYPES.map(ft => getAliasesForVendor(vendorId, ft));
      const aliasResults = await Promise.all(aliasPromises);
      
      const options: Record<string, AliasOptions> = {};
      FILE_TYPES.forEach((ft, idx) => {
        options[ft] = aliasResults[idx];
      });
      setEditAliasOptions(options);

    } catch (err) {
      setError(err instanceof Error ? err.message : '거래처 로드 실패');
    } finally {
      setLoading(false);
    }
  }

  function resetForm() {
    setSelectedVendorId('');
    setVendorPk('');
    setName('');
    setRateType('A');
    setSkuGroup('≤100');
    setActive('YES');
    setBarcodeF('NO');
    setCustboxF('NO');
    setVoidF('NO');
    setPpBagF('NO');
    setMailerF('NO');
    setVideoOutF('NO');
    setVideoRetF('NO');
    setAliasInbound([]);
    setAliasShipping([]);
    setAliasKpostIn([]);
    setAliasKpostRet([]);
    setAliasWorkLog([]);
    setEditAliasOptions({});
    setIsEditMode(false);
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
      resetForm();

      // 목록 및 별칭 새로고침
      loadVendors();
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
    // 선택된 항목이 옵션에 없으면 추가 (수정 모드에서 기존 매핑 표시용)
    const optionSet = new Set<string>([...selected, ...options]);
    const allOptions = Array.from(optionSet).sort();
    
    function toggleOption(opt: string) {
      if (selected.includes(opt)) {
        onChange(selected.filter(v => v !== opt));
      } else {
        onChange([...selected, opt]);
      }
    }
    
    return (
      <div style={{ marginBottom: '1rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
          {label} {selected.length > 0 && <span style={{ color: 'green' }}>({selected.length}개 선택됨)</span>}
        </label>
        <div
          style={{
            width: '100%',
            maxHeight: '150px',
            overflowY: 'auto',
            border: '1px solid #ddd',
            borderRadius: '4px',
            backgroundColor: '#fafafa',
          }}
        >
          {allOptions.length === 0 ? (
            <div style={{ padding: '0.5rem', color: '#999', textAlign: 'center' }}>
              사용 가능한 별칭 없음
            </div>
          ) : (
            allOptions.map((opt) => (
              <label
                key={opt}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.5rem',
                  cursor: 'pointer',
                  backgroundColor: selected.includes(opt) ? '#e3f2fd' : 'transparent',
                  borderBottom: '1px solid #eee',
                }}
                onClick={() => toggleOption(opt)}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(opt)}
                  onChange={() => {}}
                  style={{ cursor: 'pointer' }}
                />
                <span style={{ fontWeight: selected.includes(opt) ? 'bold' : 'normal' }}>
                  {opt}
                </span>
              </label>
            ))
          )}
        </div>
        <small style={{ color: '#666' }}>클릭하여 선택/해제</small>
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

  // 별칭 옵션 가져오기 (수정 모드 vs 신규 등록)
  function getAliasOptionsForType(fileType: string): string[] {
    if (isEditMode && editAliasOptions[fileType]) {
      return editAliasOptions[fileType].available;
    }
    switch (fileType) {
      case 'inbound_slip': return availableInbound;
      case 'shipping_stats': return availableShipping;
      case 'kpost_in': return availableKpostIn;
      case 'kpost_ret': return availableKpostRet;
      case 'work_log': return availableWorkLog;
      default: return [];
    }
  }

  if (loading) {
    return <Loading text="매핑 데이터 로딩 중..." />;
  }

  // 빈 상태 안내 (폼은 계속 표시)

  const totalUnmatched = unmatchedAliases.reduce((sum, u) => sum + u.count, 0);

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>거래처 매핑 관리</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 빈 상태 안내 */}
      {vendors.length === 0 && (
        <Alert 
          type="info" 
          message="등록된 거래처가 없습니다. 아래 폼을 사용하여 첫 번째 거래처를 등록하세요." 
          onClose={() => {}} 
        />
      )}

      {/* 거래처 선택 */}
      <Card title="거래처 선택" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
              기존 거래처 수정
            </label>
            <select
              value={selectedVendorId}
              onChange={(e) => handleSelectVendor(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            >
              <option value="">-- 신규 등록 --</option>
              {vendors.map((v) => (
                <option key={v.vendor} value={v.vendor}>
                  {v.vendor} {v.name ? `(${v.name})` : ''} {v.active === 'YES' ? '🟢' : '⚪'}
                </option>
              ))}
            </select>
          </div>
          {isEditMode && (
            <button
              onClick={resetForm}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: '#9e9e9e',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              신규 등록으로 전환
            </button>
          )}
        </div>
      </Card>

      <Card title={isEditMode ? `거래처 수정: ${vendorPk}` : '신규 공급처 등록'}>
        {loading ? (
          <Loading />
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                  거래처명 (PK) {isEditMode && <span style={{ color: '#999' }}>(수정 불가)</span>}
                </label>
                <input
                  type="text"
                  value={vendorPk}
                  onChange={(e) => setVendorPk(e.target.value)}
                  placeholder="DB에 저장될 고유 키"
                  disabled={isEditMode}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    backgroundColor: isEditMode ? '#f5f5f5' : 'white',
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

            <h3 style={{ marginTop: '2rem', marginBottom: '1rem' }}>
              별칭 매핑
              {isEditMode && <span style={{ fontSize: '0.875rem', color: '#666', marginLeft: '1rem' }}>
                (이미 매핑된 별칭과 사용 가능한 별칭이 표시됩니다)
              </span>}
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <MultiSelect
                label="입고전표 별칭"
                options={getAliasOptionsForType('inbound_slip')}
                selected={aliasInbound}
                onChange={setAliasInbound}
              />
              <MultiSelect
                label="배송통계 별칭"
                options={getAliasOptionsForType('shipping_stats')}
                selected={aliasShipping}
                onChange={setAliasShipping}
              />
              <MultiSelect
                label="우체국접수 별칭"
                options={getAliasOptionsForType('kpost_in')}
                selected={aliasKpostIn}
                onChange={setAliasKpostIn}
              />
              <MultiSelect
                label="우체국반품 별칭"
                options={getAliasOptionsForType('kpost_ret')}
                selected={aliasKpostRet}
                onChange={setAliasKpostRet}
              />
              <MultiSelect
                label="작업일지 별칭"
                options={getAliasOptionsForType('work_log')}
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
                backgroundColor: saving ? '#ccc' : isEditMode ? '#2196F3' : '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontSize: '1rem',
              }}
            >
              {saving ? '저장 중...' : isEditMode ? '거래처 업데이트' : '거래처 저장'}
            </button>
          </>
        )}
      </Card>

      {/* 매핑 상세 현황 섹션 */}
      <Card title="📋 매핑 상세 현황" style={{ marginTop: '2rem' }}>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', alignItems: 'center' }}>
          <button
            onClick={() => {
              if (!showMappingSummary) {
                loadMappingSummary();
              }
              setShowMappingSummary(!showMappingSummary);
            }}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: showMappingSummary ? '#f44336' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            {showMappingSummary ? '접기' : '매핑 현황 보기'}
          </button>
          {showMappingSummary && (
            <>
              <input
                type="text"
                placeholder="거래처명 검색..."
                value={mappingFilter}
                onChange={(e) => setMappingFilter(e.target.value)}
                style={{
                  padding: '0.5rem',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  width: '200px',
                }}
              />
              <button
                onClick={loadMappingSummary}
                style={{
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
            </>
          )}
        </div>
        
        {showMappingSummary && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd', whiteSpace: 'nowrap' }}>
                    거래처
                  </th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd', whiteSpace: 'nowrap' }}>
                    상태
                  </th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                    입고전표
                  </th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                    배송통계
                  </th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                    우체국접수
                  </th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                    우체국반품
                  </th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                    작업일지
                  </th>
                </tr>
              </thead>
              <tbody>
                {mappingSummary
                  .filter(m => 
                    !mappingFilter || 
                    m.vendor.toLowerCase().includes(mappingFilter.toLowerCase()) ||
                    m.name.toLowerCase().includes(mappingFilter.toLowerCase())
                  )
                  .map((m) => (
                    <tr 
                      key={m.vendor} 
                      style={{ 
                        backgroundColor: m.active === 'YES' ? 'white' : '#f9f9f9',
                        cursor: 'pointer',
                      }}
                      onClick={() => handleSelectVendor(m.vendor)}
                    >
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', fontWeight: 500 }}>
                        {m.vendor}
                        {m.name && m.name !== m.vendor && (
                          <span style={{ color: '#666', fontWeight: 'normal', marginLeft: '0.5rem' }}>
                            ({m.name})
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', textAlign: 'center' }}>
                        {m.active === 'YES' ? '🟢' : '⚪'}
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: m.inbound_slip.length ? '#333' : '#ccc' }}>
                        {m.inbound_slip.length > 0 ? m.inbound_slip.join(', ') : '-'}
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: m.shipping_stats.length ? '#333' : '#ccc' }}>
                        {m.shipping_stats.length > 0 ? m.shipping_stats.join(', ') : '-'}
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: m.kpost_in.length ? '#333' : '#ccc' }}>
                        {m.kpost_in.length > 0 ? m.kpost_in.join(', ') : '-'}
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: m.kpost_ret.length ? '#333' : '#ccc' }}>
                        {m.kpost_ret.length > 0 ? m.kpost_ret.join(', ') : '-'}
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: m.work_log.length ? '#333' : '#ccc' }}>
                        {m.work_log.length > 0 ? m.work_log.join(', ') : '-'}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {mappingSummary.length === 0 && (
              <p style={{ textAlign: 'center', color: '#999', padding: '2rem' }}>
                등록된 거래처가 없습니다.
              </p>
            )}
          </div>
        )}
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
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>
                    미매칭 별칭
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
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', fontSize: '0.875rem', color: '#666' }}>
                      {item.aliases.slice(0, 5).join(', ')}
                      {item.aliases.length > 5 && ` ... 외 ${item.aliases.length - 5}건`}
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
