'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';
import {
  getVendors,
  getVendor,
  saveVendor,
  deleteVendor,
  getAvailableAliases,
  Vendor,
  VendorDetail,
} from '@/lib/api';

const SKU_OPTS = ['≤100', '≤300', '≤500', '≤1,000', '≤2,000', '>2,000'];
const YES_NO = ['YES', 'NO'];
const RATE_TYPES = ['A', 'STD'];

export default function VendorsPage() {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [filterMode, setFilterMode] = useState<'all' | 'active' | 'inactive'>('active');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [selectedVendor, setSelectedVendor] = useState<VendorDetail | null>(null);

  // 편집 폼 상태
  const [editName, setEditName] = useState('');
  const [editRateType, setEditRateType] = useState('A');
  const [editSkuGroup, setEditSkuGroup] = useState('≤100');
  const [editActive, setEditActive] = useState('YES');
  const [editBarcodeF, setEditBarcodeF] = useState('NO');
  const [editCustboxF, setEditCustboxF] = useState('NO');
  const [editVoidF, setEditVoidF] = useState('NO');
  const [editPpBagF, setEditPpBagF] = useState('NO');
  const [editMailerF, setEditMailerF] = useState('NO');
  const [editVideoOutF, setEditVideoOutF] = useState('NO');
  const [editVideoRetF, setEditVideoRetF] = useState('NO');

  // 별칭
  const [editAliasInbound, setEditAliasInbound] = useState<string[]>([]);
  const [editAliasShipping, setEditAliasShipping] = useState<string[]>([]);
  const [editAliasKpostIn, setEditAliasKpostIn] = useState<string[]>([]);
  const [editAliasKpostRet, setEditAliasKpostRet] = useState<string[]>([]);
  const [editAliasWorkLog, setEditAliasWorkLog] = useState<string[]>([]);

  // 사용 가능한 별칭
  const [availableInbound, setAvailableInbound] = useState<string[]>([]);
  const [availableShipping, setAvailableShipping] = useState<string[]>([]);
  const [availableKpostIn, setAvailableKpostIn] = useState<string[]>([]);
  const [availableKpostRet, setAvailableKpostRet] = useState<string[]>([]);
  const [availableWorkLog, setAvailableWorkLog] = useState<string[]>([]);

  // UI 상태
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadVendors();
  }, []);

  async function loadVendors() {
    try {
      setLoading(true);
      const data = await getVendors();
      setVendors(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '거래처 목록 로드 실패');
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectVendor(vendorId: string) {
    if (!vendorId) {
      setSelectedVendor(null);
      return;
    }

    try {
      setLoading(true);
      const [vendor, inbound, shipping, kpostIn, kpostRet, workLog] = await Promise.all([
        getVendor(vendorId),
        getAvailableAliases('inbound_slip', vendorId),
        getAvailableAliases('shipping_stats', vendorId),
        getAvailableAliases('kpost_in', vendorId),
        getAvailableAliases('kpost_ret', vendorId),
        getAvailableAliases('work_log', vendorId),
      ]);

      setSelectedVendor(vendor);

      // 폼 초기화
      setEditName(vendor.name || '');
      setEditRateType(vendor.rate_type || 'A');
      setEditSkuGroup(vendor.sku_group || '≤100');
      setEditActive(vendor.active || 'YES');
      setEditBarcodeF(vendor.barcode_f || 'NO');
      setEditCustboxF(vendor.custbox_f || 'NO');
      setEditVoidF(vendor.void_f || 'NO');
      setEditPpBagF(vendor.pp_bag_f || 'NO');
      setEditMailerF(vendor.mailer_f || 'NO');
      setEditVideoOutF(vendor.video_out_f || 'NO');
      setEditVideoRetF(vendor.video_ret_f || 'NO');

      setEditAliasInbound(vendor.alias_inbound_slip || []);
      setEditAliasShipping(vendor.alias_shipping_stats || []);
      setEditAliasKpostIn(vendor.alias_kpost_in || []);
      setEditAliasKpostRet(vendor.alias_kpost_ret || []);
      setEditAliasWorkLog(vendor.alias_work_log || []);

      // 사용 가능한 별칭 = 현재 매핑된 것 + 미매핑된 것
      setAvailableInbound([...vendor.alias_inbound_slip, ...inbound]);
      setAvailableShipping([...vendor.alias_shipping_stats, ...shipping]);
      setAvailableKpostIn([...vendor.alias_kpost_in, ...kpostIn]);
      setAvailableKpostRet([...vendor.alias_kpost_ret, ...kpostRet]);
      setAvailableWorkLog([...vendor.alias_work_log, ...workLog]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '거래처 상세 로드 실패');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!selectedVendor) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      await saveVendor({
        vendor: selectedVendor.vendor,
        name: editName,
        rate_type: editRateType,
        sku_group: editSkuGroup,
        active: editActive,
        barcode_f: editBarcodeF,
        custbox_f: editCustboxF,
        void_f: editVoidF,
        pp_bag_f: editPpBagF,
        mailer_f: editMailerF,
        video_out_f: editVideoOutF,
        video_ret_f: editVideoRetF,
        alias_inbound_slip: editAliasInbound,
        alias_shipping_stats: editAliasShipping,
        alias_kpost_in: editAliasKpostIn,
        alias_kpost_ret: editAliasKpostRet,
        alias_work_log: editAliasWorkLog,
      });

      setSuccess('저장 완료!');
      loadVendors();
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!selectedVendor) return;
    if (!confirm(`'${selectedVendor.vendor}' 거래처를 삭제하시겠습니까?`)) return;

    try {
      await deleteVendor(selectedVendor.vendor);
      setSuccess('삭제 완료');
      setSelectedVendor(null);
      loadVendors();
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  // 필터링된 거래처 목록
  const filteredVendors = vendors.filter((v) => {
    // 활성 상태 필터
    if (filterMode === 'active' && v.active !== 'YES') return false;
    if (filterMode === 'inactive' && v.active !== 'NO') return false;

    // 검색어 필터
    if (searchKeyword) {
      const kw = searchKeyword.toLowerCase();
      return (
        v.vendor.toLowerCase().includes(kw) ||
        (v.name && v.name.toLowerCase().includes(kw))
      );
    }

    return true;
  });

  const activeCount = vendors.filter((v) => v.active === 'YES').length;
  const inactiveCount = vendors.filter((v) => v.active !== 'YES').length;

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
            minHeight: '100px',
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

  if (loading && vendors.length === 0) {
    return <Loading />;
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>거래처 매핑 리스트</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 검색 & 필터 */}
      <Card>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="검색어 (거래처/별칭)"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            style={{
              padding: '0.5rem',
              border: '1px solid #ddd',
              borderRadius: '4px',
              width: '250px',
            }}
          />
          <select
            value={filterMode}
            onChange={(e) => setFilterMode(e.target.value as 'all' | 'active' | 'inactive')}
            style={{
              padding: '0.5rem',
              border: '1px solid #ddd',
              borderRadius: '4px',
            }}
          >
            <option value="all">전체 ({vendors.length})</option>
            <option value="active">활성만 ({activeCount})</option>
            <option value="inactive">비활성만 ({inactiveCount})</option>
          </select>
        </div>
      </Card>

      {/* 거래처 목록 테이블 */}
      <Card title="거래처 목록" style={{ marginTop: '1rem' }}>
        <div style={{ overflowX: 'auto', maxHeight: '400px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f5f5f5' }}>
              <tr>
                <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>활성</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>요금타입</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>SKU구간</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>바코드</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>박스</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>완충재</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>PP봉투</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>택배봉투</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>출고영상</th>
                <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>반품영상</th>
              </tr>
            </thead>
            <tbody>
              {filteredVendors.map((v) => (
                <tr
                  key={v.vendor}
                  onClick={() => handleSelectVendor(v.vendor)}
                  style={{
                    cursor: 'pointer',
                    backgroundColor: selectedVendor?.vendor === v.vendor ? '#e3f2fd' : 'transparent',
                  }}
                >
                  <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{v.vendor}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee', color: v.active === 'YES' ? 'green' : 'gray' }}>
                    {v.active || 'YES'}
                  </td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.rate_type}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.sku_group}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.barcode_f}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.custbox_f}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.void_f}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.pp_bag_f}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.mailer_f}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.video_out_f}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{v.video_ret_f}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 상세 편집 영역 */}
      {selectedVendor && (
        <Card title={`편집: ${selectedVendor.vendor}`} style={{ marginTop: '1rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>별칭 매핑</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <MultiSelect
              label="입고전표 별칭"
              options={availableInbound}
              selected={editAliasInbound}
              onChange={setEditAliasInbound}
            />
            <MultiSelect
              label="배송통계 별칭"
              options={availableShipping}
              selected={editAliasShipping}
              onChange={setEditAliasShipping}
            />
            <MultiSelect
              label="우체국접수 별칭"
              options={availableKpostIn}
              selected={editAliasKpostIn}
              onChange={setEditAliasKpostIn}
            />
            <MultiSelect
              label="우체국반품 별칭"
              options={availableKpostRet}
              selected={editAliasKpostRet}
              onChange={setEditAliasKpostRet}
            />
            <MultiSelect
              label="작업일지 별칭"
              options={availableWorkLog}
              selected={editAliasWorkLog}
              onChange={setEditAliasWorkLog}
            />
          </div>

          <h3 style={{ marginTop: '2rem', marginBottom: '1rem' }}>설정</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
            <SelectField label="활성 상태" value={editActive} options={YES_NO} onChange={setEditActive} />
            <SelectField label="요금타입" value={editRateType} options={RATE_TYPES} onChange={setEditRateType} />
            <SelectField label="SKU 구간" value={editSkuGroup} options={SKU_OPTS} onChange={setEditSkuGroup} />
            <SelectField label="바코드 부착" value={editBarcodeF} options={YES_NO} onChange={setEditBarcodeF} />
            <SelectField label="박스" value={editCustboxF} options={YES_NO} onChange={setEditCustboxF} />
            <SelectField label="완충재" value={editVoidF} options={YES_NO} onChange={setEditVoidF} />
            <SelectField label="PP 봉투" value={editPpBagF} options={YES_NO} onChange={setEditPpBagF} />
            <SelectField label="택배 봉투" value={editMailerF} options={YES_NO} onChange={setEditMailerF} />
            <SelectField label="출고영상촬영" value={editVideoOutF} options={YES_NO} onChange={setEditVideoOutF} />
            <SelectField label="반품영상촬영" value={editVideoRetF} options={YES_NO} onChange={setEditVideoRetF} />
          </div>

          <div style={{ marginTop: '2rem', display: 'flex', gap: '1rem' }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '0.75rem 2rem',
                backgroundColor: '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: saving ? 'not-allowed' : 'pointer',
              }}
            >
              {saving ? '저장 중...' : '변경 사항 저장'}
            </button>
            <button
              onClick={handleDelete}
              style={{
                padding: '0.75rem 2rem',
                backgroundColor: '#f44336',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              공급처 삭제
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}

