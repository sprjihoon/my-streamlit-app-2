'use client';

import { useState, useEffect } from 'react';
import Card from '../../components/Card';
import Loading from '../../components/Loading';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface StorageRate {
  rate_id?: number;
  item_name: string;
  unit_price: number;
  unit: string;
  description: string;
  is_active: boolean;
}

interface VendorStorage {
  storage_id?: number;
  vendor_id: string;
  rate_id?: number;
  item_name: string;
  qty: number;
  unit_price: number;
  amount: number;
  period: string;
  remark: string;
  is_active: boolean;
}

interface Vendor {
  vendor: string;
  name: string;
}

const emptyStorage: VendorStorage = {
  vendor_id: '',
  rate_id: undefined,
  item_name: '',
  qty: 1,
  unit_price: 0,
  amount: 0,
  period: '',
  remark: '',
  is_active: true,
};

export default function StoragePage() {
  const [rates, setRates] = useState<StorageRate[]>([]);
  const [storages, setStorages] = useState<VendorStorage[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // 탭
  const [activeTab, setActiveTab] = useState<'rates' | 'vendor'>('vendor');
  
  // 필터
  const [selectedVendor, setSelectedVendor] = useState<string>('');
  const [selectedPeriod, setSelectedPeriod] = useState<string>('');
  
  // 편집
  const [editingStorage, setEditingStorage] = useState<VendorStorage | null>(null);
  const [editingRate, setEditingRate] = useState<StorageRate | null>(null);
  const [isNew, setIsNew] = useState(false);
  
  // 권한
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    setIsAdmin(localStorage.getItem('isAdmin') === 'true');
    loadVendors();
    loadRates();
    loadStorages();
    
    // 기본 기간 설정 (현재 월)
    const now = new Date();
    const period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    setSelectedPeriod(period);
  }, []);

  useEffect(() => {
    loadStorages();
  }, [selectedVendor, selectedPeriod]);

  async function loadVendors() {
    try {
      const res = await fetch(`${API_URL}/vendors`);
      if (res.ok) {
        const data = await res.json();
        // API는 배열을 직접 반환함
        const vendorList = Array.isArray(data) ? data : (data.vendors || []);
        setVendors(vendorList);
      }
    } catch (err) {
      console.error('Failed to load vendors:', err);
    }
  }

  async function loadRates() {
    try {
      const res = await fetch(`${API_URL}/storage/rates`);
      if (res.ok) {
        const data = await res.json();
        setRates(data.rates || []);
      }
    } catch (err) {
      console.error('Failed to load rates:', err);
    }
  }

  async function loadStorages() {
    try {
      setLoading(true);
      let url = `${API_URL}/storage/vendor?active_only=false`;
      if (selectedVendor) url += `&vendor_id=${encodeURIComponent(selectedVendor)}`;
      if (selectedPeriod) url += `&period=${encodeURIComponent(selectedPeriod)}`;
      
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setStorages(data.storages || []);
      }
    } catch (err) {
      setError('데이터를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }

  function handleNewStorage() {
    setEditingStorage({
      ...emptyStorage,
      period: selectedPeriod,
      vendor_id: selectedVendor,
    });
    setIsNew(true);
  }

  function handleEditStorage(storage: VendorStorage) {
    setEditingStorage({ ...storage });
    setIsNew(false);
  }

  function handleNewRate() {
    setEditingRate({
      item_name: '',
      unit_price: 0,
      unit: '월',
      description: '',
      is_active: true,
    });
    setIsNew(true);
  }

  function handleEditRate(rate: StorageRate) {
    setEditingRate({ ...rate });
    setIsNew(false);
  }

  async function handleSaveStorage() {
    if (!editingStorage) return;
    if (!editingStorage.vendor_id || !editingStorage.item_name) {
      setError('거래처와 품목명은 필수입니다.');
      return;
    }

    try {
      setSaving(true);
      const url = isNew
        ? `${API_URL}/storage/vendor`
        : `${API_URL}/storage/vendor/${editingStorage.storage_id}`;
      
      const res = await fetch(url, {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingStorage),
      });

      if (!res.ok) throw new Error('저장 실패');

      setEditingStorage(null);
      loadStorages();
      setSuccess(isNew ? '추가되었습니다.' : '수정되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveRate() {
    if (!editingRate) return;
    if (!editingRate.item_name) {
      setError('품목명은 필수입니다.');
      return;
    }

    try {
      setSaving(true);
      const url = isNew
        ? `${API_URL}/storage/rates`
        : `${API_URL}/storage/rates/${editingRate.rate_id}`;
      
      const res = await fetch(url, {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingRate),
      });

      if (!res.ok) throw new Error('저장 실패');

      setEditingRate(null);
      loadRates();
      setSuccess(isNew ? '추가되었습니다.' : '수정되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteStorage(storageId: number) {
    if (!confirm('정말 삭제하시겠습니까?')) return;
    try {
      await fetch(`${API_URL}/storage/vendor/${storageId}`, { method: 'DELETE' });
      loadStorages();
      setSuccess('삭제되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('삭제 실패');
    }
  }

  async function handleDeleteRate(rateId: number) {
    if (!confirm('정말 삭제하시겠습니까?')) return;
    try {
      await fetch(`${API_URL}/storage/rates/${rateId}`, { method: 'DELETE' });
      loadRates();
      setSuccess('삭제되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('삭제 실패');
    }
  }

  function handleStorageChange(field: keyof VendorStorage, value: string | number | boolean) {
    if (!editingStorage) return;
    
    const updated = { ...editingStorage, [field]: value };
    
    // 단가표에서 선택 시 자동 반영
    if (field === 'rate_id') {
      const rate = rates.find(r => r.rate_id === Number(value));
      if (rate) {
        updated.item_name = rate.item_name;
        updated.unit_price = rate.unit_price;
        updated.amount = updated.qty * rate.unit_price;
      }
    }
    
    // 금액 자동 계산
    if (field === 'qty' || field === 'unit_price') {
      updated.amount = Number(updated.qty) * Number(updated.unit_price);
    }
    
    setEditingStorage(updated);
  }

  function formatNumber(num: number): string {
    return num.toLocaleString();
  }

  const inputStyle = {
    width: '100%',
    padding: '0.5rem',
    border: '1px solid #ddd',
    borderRadius: '4px',
  };

  const tabStyle = (active: boolean) => ({
    padding: '0.75rem 1.5rem',
    backgroundColor: active ? '#2196F3' : '#f5f5f5',
    color: active ? 'white' : '#333',
    border: 'none',
    borderRadius: '4px 4px 0 0',
    cursor: 'pointer',
    fontWeight: active ? 'bold' : 'normal',
  });

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>보관료 관리</h1>

      {error && <div className="alert alert-error" style={{ marginBottom: '1rem', position: 'relative' }}>{error}<button onClick={() => setError(null)} style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', cursor: 'pointer', fontSize: '1rem' }}>×</button></div>}
      {success && <div className="alert alert-success" style={{ marginBottom: '1rem' }}>{success}</div>}

      {/* 탭 */}
      <div style={{ marginBottom: '0' }}>
        <button style={tabStyle(activeTab === 'vendor')} onClick={() => setActiveTab('vendor')}>
          거래처별 보관료
        </button>
        <button style={tabStyle(activeTab === 'rates')} onClick={() => setActiveTab('rates')}>
          보관료 단가표
        </button>
      </div>

      {/* 보관료 단가표 탭 */}
      {activeTab === 'rates' && (
        <Card title="💰 보관료 단가표" style={{ borderTopLeftRadius: 0 }}>
          {isAdmin && (
            <div style={{ marginBottom: '1rem' }}>
              <button
                onClick={handleNewRate}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#4CAF50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                ➕ 새 단가 추가
              </button>
            </div>
          )}

          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f5f5f5' }}>
                <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>품목명</th>
                <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>단가</th>
                <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>단위</th>
                <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>설명</th>
                {isAdmin && <th style={{ padding: '0.75rem', borderBottom: '2px solid #ddd' }}>관리</th>}
              </tr>
            </thead>
            <tbody>
              {rates.map((rate) => (
                <tr key={rate.rate_id}>
                  <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>{rate.item_name}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>₩{formatNumber(rate.unit_price)}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{rate.unit}</td>
                  <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: '#666' }}>{rate.description}</td>
                  {isAdmin && (
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                      <div style={{ display: 'flex', gap: '0.25rem' }}>
                        <button onClick={() => handleEditRate(rate)} style={{ padding: '0.25rem 0.5rem', backgroundColor: '#2196F3', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>수정</button>
                        <button onClick={() => handleDeleteRate(rate.rate_id!)} style={{ padding: '0.25rem 0.5rem', backgroundColor: '#f44336', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>삭제</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* 거래처별 보관료 탭 */}
      {activeTab === 'vendor' && (
        <>
          <Card title="🔍 필터" style={{ borderTopLeftRadius: 0 }}>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <div>
                <label style={{ marginRight: '0.5rem' }}>거래처:</label>
                <select
                  value={selectedVendor}
                  onChange={(e) => setSelectedVendor(e.target.value)}
                  style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid #ddd' }}
                >
                <option value="">전체</option>
                {vendors.map((v) => (
                  <option key={v.vendor} value={v.vendor}>{v.name || v.vendor}</option>
                ))}
                </select>
              </div>
              
              <div>
                <label style={{ marginRight: '0.5rem' }}>기간:</label>
                <input
                  type="month"
                  value={selectedPeriod}
                  onChange={(e) => setSelectedPeriod(e.target.value)}
                  style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              {isAdmin && (
                <button
                  onClick={handleNewStorage}
                  style={{
                    marginLeft: 'auto',
                    padding: '0.5rem 1rem',
                    backgroundColor: '#4CAF50',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  ➕ 보관료 추가
                </button>
              )}
            </div>
          </Card>

          <Card title={`📋 보관료 내역 (${storages.length}건)`} style={{ marginTop: '1rem' }}>
            {loading ? (
              <Loading />
            ) : storages.length === 0 ? (
              <p style={{ color: '#666' }}>등록된 보관료 내역이 없습니다.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>기간</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>품목</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>수량</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>단가</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>금액</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>비고</th>
                      {isAdmin && <th style={{ padding: '0.75rem', borderBottom: '2px solid #ddd' }}>관리</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {storages.map((storage) => (
                      <tr key={storage.storage_id} style={{ opacity: storage.is_active ? 1 : 0.5 }}>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                          {vendors.find(v => v.vendor === storage.vendor_id)?.name || storage.vendor_id}
                        </td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{storage.period}</td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{storage.item_name}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(storage.qty)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>₩{formatNumber(storage.unit_price)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>₩{formatNumber(storage.amount)}</td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: '#666' }}>{storage.remark || '-'}</td>
                        {isAdmin && (
                          <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                            <div style={{ display: 'flex', gap: '0.25rem' }}>
                              <button onClick={() => handleEditStorage(storage)} style={{ padding: '0.25rem 0.5rem', backgroundColor: '#2196F3', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>수정</button>
                              <button onClick={() => handleDeleteStorage(storage.storage_id!)} style={{ padding: '0.25rem 0.5rem', backgroundColor: '#f44336', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>삭제</button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ backgroundColor: '#f5f5f5', fontWeight: 'bold' }}>
                      <td colSpan={5} style={{ padding: '0.75rem', textAlign: 'right' }}>합계:</td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>₩{formatNumber(storages.reduce((sum, s) => sum + s.amount, 0))}</td>
                      <td colSpan={isAdmin ? 2 : 1}></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {/* 보관료 내역 편집 모달 */}
      {editingStorage && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setEditingStorage(null)}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              width: '500px',
              maxHeight: '90vh',
              overflow: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginBottom: '1.5rem' }}>{isNew ? '➕ 보관료 추가' : '✏️ 보관료 수정'}</h2>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>거래처 *</label>
              <select
                value={editingStorage.vendor_id}
                onChange={(e) => handleStorageChange('vendor_id', e.target.value)}
                style={inputStyle}
              >
                <option value="">선택하세요</option>
                {vendors.map((v) => (
                  <option key={v.vendor} value={v.vendor}>{v.name || v.vendor}</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>시작월 (참고용)</label>
              <input
                type="month"
                value={editingStorage.period}
                onChange={(e) => handleStorageChange('period', e.target.value)}
                style={inputStyle}
              />
              <small style={{ color: '#666' }}>* 활성 상태면 매월 자동 청구됩니다</small>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>품목 (단가표에서 선택)</label>
              <select
                value={editingStorage.rate_id || ''}
                onChange={(e) => handleStorageChange('rate_id', Number(e.target.value))}
                style={inputStyle}
              >
                <option value="">직접 입력</option>
                {rates.map((r) => (
                  <option key={r.rate_id} value={r.rate_id}>{r.item_name} (₩{formatNumber(r.unit_price)}/{r.unit})</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>품목명 *</label>
              <input
                type="text"
                value={editingStorage.item_name}
                onChange={(e) => handleStorageChange('item_name', e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>수량</label>
                <input
                  type="number"
                  value={editingStorage.qty}
                  onChange={(e) => handleStorageChange('qty', Number(e.target.value))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>단가</label>
                <input
                  type="number"
                  value={editingStorage.unit_price}
                  onChange={(e) => handleStorageChange('unit_price', Number(e.target.value))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>금액</label>
                <input
                  type="number"
                  value={editingStorage.amount}
                  readOnly
                  style={{ ...inputStyle, backgroundColor: '#f5f5f5' }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>비고</label>
              <input
                type="text"
                value={editingStorage.remark}
                onChange={(e) => handleStorageChange('remark', e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={editingStorage.is_active}
                  onChange={(e) => handleStorageChange('is_active', e.target.checked)}
                />
                활성 (인보이스 계산에 포함)
              </label>
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setEditingStorage(null)}
                style={{ padding: '0.5rem 1rem', backgroundColor: '#9e9e9e', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              >
                취소
              </button>
              <button
                onClick={handleSaveStorage}
                disabled={saving}
                style={{ padding: '0.5rem 1rem', backgroundColor: saving ? '#ccc' : '#4CAF50', color: 'white', border: 'none', borderRadius: '4px', cursor: saving ? 'not-allowed' : 'pointer' }}
              >
                {saving ? '저장 중...' : '💾 저장'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 단가 편집 모달 */}
      {editingRate && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setEditingRate(null)}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              width: '400px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginBottom: '1.5rem' }}>{isNew ? '➕ 단가 추가' : '✏️ 단가 수정'}</h2>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>품목명 *</label>
              <input
                type="text"
                value={editingRate.item_name}
                onChange={(e) => setEditingRate({ ...editingRate, item_name: e.target.value })}
                style={inputStyle}
                placeholder="예: PLT, 단프라"
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>단가</label>
                <input
                  type="number"
                  value={editingRate.unit_price}
                  onChange={(e) => setEditingRate({ ...editingRate, unit_price: Number(e.target.value) })}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>단위</label>
                <input
                  type="text"
                  value={editingRate.unit}
                  onChange={(e) => setEditingRate({ ...editingRate, unit: e.target.value })}
                  style={inputStyle}
                />
              </div>
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>설명</label>
              <input
                type="text"
                value={editingRate.description}
                onChange={(e) => setEditingRate({ ...editingRate, description: e.target.value })}
                style={inputStyle}
              />
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setEditingRate(null)}
                style={{ padding: '0.5rem 1rem', backgroundColor: '#9e9e9e', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              >
                취소
              </button>
              <button
                onClick={handleSaveRate}
                disabled={saving}
                style={{ padding: '0.5rem 1rem', backgroundColor: saving ? '#ccc' : '#4CAF50', color: 'white', border: 'none', borderRadius: '4px', cursor: saving ? 'not-allowed' : 'pointer' }}
              >
                {saving ? '저장 중...' : '💾 저장'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

