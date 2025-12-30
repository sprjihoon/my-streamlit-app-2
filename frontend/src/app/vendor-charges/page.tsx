'use client';

import { useState, useEffect } from 'react';
import Card from '../../components/Card';
import Loading from '../../components/Loading';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface VendorCharge {
  charge_id?: number;
  vendor_id: string;
  item_name: string;
  qty: number;
  unit_price: number;
  amount: number;
  remark: string;
  charge_type: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

interface Vendor {
  vendor: string;
  name: string;
}

const emptyCharge: VendorCharge = {
  vendor_id: '',
  item_name: '',
  qty: 1,
  unit_price: 0,
  amount: 0,
  remark: '',
  charge_type: '기타',
  is_active: true,
};

export default function VendorChargesPage() {
  const [charges, setCharges] = useState<VendorCharge[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // 필터
  const [selectedVendor, setSelectedVendor] = useState<string>('');
  const [showInactive, setShowInactive] = useState(false);
  
  // 편집 모달
  const [editingCharge, setEditingCharge] = useState<VendorCharge | null>(null);
  const [isNewCharge, setIsNewCharge] = useState(false);
  
  // 권한
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const storedIsAdmin = localStorage.getItem('isAdmin') === 'true';
    setIsAdmin(storedIsAdmin);
    loadVendors();
    loadCharges();
  }, []);

  useEffect(() => {
    loadCharges();
  }, [selectedVendor, showInactive]);

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

  async function loadCharges() {
    try {
      setLoading(true);
      let url = `${API_URL}/vendor-charges?active_only=${!showInactive}`;
      if (selectedVendor) {
        url += `&vendor_id=${encodeURIComponent(selectedVendor)}`;
      }
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setCharges(data.charges || []);
      }
    } catch (err) {
      setError('데이터를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }

  function handleNew() {
    setEditingCharge({ ...emptyCharge });
    setIsNewCharge(true);
  }

  function handleEdit(charge: VendorCharge) {
    setEditingCharge({ ...charge });
    setIsNewCharge(false);
  }

  async function handleSave() {
    if (!editingCharge) return;
    if (!editingCharge.vendor_id || !editingCharge.item_name) {
      setError('거래처와 품명은 필수입니다.');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      const url = isNewCharge
        ? `${API_URL}/vendor-charges`
        : `${API_URL}/vendor-charges/${editingCharge.charge_id}`;
      
      const method = isNewCharge ? 'POST' : 'PUT';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingCharge),
      });

      if (!res.ok) {
        throw new Error('저장 실패');
      }

      setEditingCharge(null);
      loadCharges();
      setSuccess(isNewCharge ? '새 항목이 추가되었습니다.' : '수정되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(chargeId: number) {
    if (!confirm('정말 삭제하시겠습니까?')) return;

    try {
      const res = await fetch(`${API_URL}/vendor-charges/${chargeId}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        throw new Error('삭제 실패');
      }

      loadCharges();
      setSuccess('삭제되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  function handleChargeChange(field: keyof VendorCharge, value: string | number | boolean) {
    if (!editingCharge) return;
    
    const updated = { ...editingCharge, [field]: value };
    
    // 금액 자동 계산
    if (field === 'qty' || field === 'unit_price') {
      updated.amount = Number(updated.qty) * Number(updated.unit_price);
    }
    
    setEditingCharge(updated);
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

  if (loading && charges.length === 0) {
    return <Loading />;
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ marginBottom: '1.5rem' }}>💰 거래처별 추가 비용 관리</h1>

      {error && (
        <div style={{ padding: '1rem', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px', marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: '1rem', backgroundColor: '#e8f5e9', color: '#2e7d32', borderRadius: '4px', marginBottom: '1rem' }}>
          {success}
        </div>
      )}

      {/* 필터 및 추가 버튼 */}
      <Card title="🔍 필터">
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
                <option key={v.vendor} value={v.vendor}>
                  {v.name || v.vendor}
                </option>
              ))}
            </select>
          </div>
          
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            비활성 항목 표시
          </label>

          {isAdmin && (
            <button
              onClick={handleNew}
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
              ➕ 새 항목 추가
            </button>
          )}
        </div>
      </Card>

      {/* 목록 */}
      <Card title={`📋 청구 비용 목록 (${charges.length}건)`} style={{ marginTop: '1rem' }}>
        {loading ? (
          <Loading />
        ) : charges.length === 0 ? (
          <p style={{ color: '#666' }}>등록된 항목이 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>유형</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>품명</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>수량</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>단가</th>
                  <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>금액</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>비고</th>
                  <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>상태</th>
                  {isAdmin && <th style={{ padding: '0.75rem', borderBottom: '2px solid #ddd' }}>관리</th>}
                </tr>
              </thead>
              <tbody>
                {charges.map((charge) => (
                  <tr key={charge.charge_id} style={{ opacity: charge.is_active ? 1 : 0.5 }}>
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                      {vendors.find(v => v.vendor === charge.vendor_id)?.name || charge.vendor_id}
                    </td>
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{charge.charge_type}</td>
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{charge.item_name}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(charge.qty)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>₩{formatNumber(charge.unit_price)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>₩{formatNumber(charge.amount)}</td>
                    <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: '#666' }}>{charge.remark || '-'}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>
                      {charge.is_active ? '✅' : '❌'}
                    </td>
                    {isAdmin && (
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <div style={{ display: 'flex', gap: '0.25rem' }}>
                          <button
                            onClick={() => handleEdit(charge)}
                            style={{
                              padding: '0.25rem 0.5rem',
                              backgroundColor: '#2196F3',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                            }}
                          >
                            수정
                          </button>
                          <button
                            onClick={() => handleDelete(charge.charge_id!)}
                            style={{
                              padding: '0.25rem 0.5rem',
                              backgroundColor: '#f44336',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                            }}
                          >
                            삭제
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 편집 모달 */}
      {editingCharge && (
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
          onClick={() => setEditingCharge(null)}
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
            <h2 style={{ marginBottom: '1.5rem' }}>
              {isNewCharge ? '➕ 새 항목 추가' : '✏️ 항목 수정'}
            </h2>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>거래처 *</label>
              <select
                value={editingCharge.vendor_id}
                onChange={(e) => handleChargeChange('vendor_id', e.target.value)}
                style={inputStyle}
              >
                <option value="">선택하세요</option>
                {vendors.map((v) => (
                  <option key={v.vendor} value={v.vendor}>
                    {v.name || v.vendor}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>비용 유형</label>
              <select
                value={editingCharge.charge_type}
                onChange={(e) => handleChargeChange('charge_type', e.target.value)}
                style={inputStyle}
              >
                <option value="기타">기타</option>
                <option value="월정액">월정액</option>
                <option value="추가작업">추가작업</option>
              </select>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>품명 *</label>
              <input
                type="text"
                value={editingCharge.item_name}
                onChange={(e) => handleChargeChange('item_name', e.target.value)}
                style={inputStyle}
                placeholder="예: 보관비 (11월)"
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>수량</label>
                <input
                  type="number"
                  value={editingCharge.qty}
                  onChange={(e) => handleChargeChange('qty', Number(e.target.value))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>단가</label>
                <input
                  type="number"
                  value={editingCharge.unit_price}
                  onChange={(e) => handleChargeChange('unit_price', Number(e.target.value))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>금액</label>
                <input
                  type="number"
                  value={editingCharge.amount}
                  onChange={(e) => handleChargeChange('amount', Number(e.target.value))}
                  style={{ ...inputStyle, backgroundColor: '#f5f5f5' }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>비고</label>
              <input
                type="text"
                value={editingCharge.remark}
                onChange={(e) => handleChargeChange('remark', e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={editingCharge.is_active}
                  onChange={(e) => handleChargeChange('is_active', e.target.checked)}
                />
                활성 (인보이스 계산에 포함)
              </label>
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setEditingCharge(null)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#9e9e9e',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                취소
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: saving ? '#ccc' : '#4CAF50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}
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

