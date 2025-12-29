'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Invoice {
  invoice_id: number;
  vendor_id: string;
  vendor: string;
  period_from: string;
  period_to: string;
  total_amount: number;
  status: string;
  created_at: string;
  modified_by: string | null;
  modified_at: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

interface InvoiceItem {
  항목: string;
  수량: number;
  단가: number;
  금액: number;
  비고: string;
}

interface InvoiceDetail {
  invoice_id: number;
  vendor: string;
  period_from: string;
  period_to: string;
  total_amount: number;
  status: string;
  items: InvoiceItem[];
}

/**
 * 인보이스 목록 페이지
 * 기존 Streamlit invoice_list.py와 동일한 기능 + 항목 수정 기능
 */
export default function InvoiceListPage() {
  // 목록 상태
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // 필터
  const [periods, setPeriods] = useState<string[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>('');
  const [vendors, setVendors] = useState<string[]>([]);
  const [selectedVendor, setSelectedVendor] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  
  // 선택 상태
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectAll, setSelectAll] = useState(false);
  
  // 상세 보기 / 편집 모달
  const [detailInvoice, setDetailInvoice] = useState<InvoiceDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editItems, setEditItems] = useState<InvoiceItem[]>([]);
  const [saving, setSaving] = useState(false);
  
  // 통계
  const [sumAmount, setSumAmount] = useState(0);
  
  // 권한 체크
  const [isAdmin, setIsAdmin] = useState(false);
  
  useEffect(() => {
    const storedIsAdmin = localStorage.getItem('isAdmin') === 'true';
    setIsAdmin(storedIsAdmin);
  }, []);

  // 인보이스 목록 로드
  useEffect(() => {
    loadInvoices();
  }, [selectedPeriod, selectedVendor, selectedStatus]);

  async function loadInvoices() {
    try {
      setLoading(true);
      setError(null);
      
      const params = new URLSearchParams();
      if (selectedPeriod) params.append('period', selectedPeriod);
      if (selectedVendor) params.append('vendor', selectedVendor);
      if (selectedStatus) params.append('status', selectedStatus);
      
      const res = await fetch(`${API_URL}/invoices?${params.toString()}`);
      const data = await res.json();
      
      if (data.error) {
        setError(data.error);
        setInvoices([]);
        return;
      }
      
      setInvoices(data.invoices || []);
      setSumAmount(data.sum_amount || 0);
      
      if (data.periods) {
        setPeriods(data.periods);
      }
      
      const vendorSet = new Set<string>();
      (data.invoices || []).forEach((i: Invoice) => {
        if (i.vendor) vendorSet.add(i.vendor);
      });
      setVendors(Array.from(vendorSet));
      
    } catch (err) {
      setError(err instanceof Error ? err.message : '로드 실패');
      setInvoices([]);
    } finally {
      setLoading(false);
    }
  }

  // 전체 선택
  function handleSelectAll() {
    if (selectAll) {
      setSelectedIds([]);
      setSelectAll(false);
    } else {
      setSelectedIds(invoices.map(i => i.invoice_id));
      setSelectAll(true);
    }
  }

  // 개별 선택
  function handleToggleSelect(id: number) {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter(x => x !== id));
    } else {
      setSelectedIds([...selectedIds, id]);
    }
  }

  // 상세 조회
  async function handleViewDetail(invoiceId: number) {
    try {
      setLoadingDetail(true);
      setIsEditing(false);
      const res = await fetch(`${API_URL}/invoices/${invoiceId}`);
      const data = await res.json();
      setDetailInvoice(data);
      setEditItems(data.items.map((item: InvoiceItem) => ({ ...item })));
    } catch (err) {
      setError(err instanceof Error ? err.message : '상세 조회 실패');
    } finally {
      setLoadingDetail(false);
    }
  }

  // 편집 모드 시작
  function handleStartEdit() {
    if (detailInvoice) {
      setEditItems(detailInvoice.items.map(item => ({ ...item })));
      setIsEditing(true);
    }
  }

  // 편집 취소
  function handleCancelEdit() {
    if (detailInvoice) {
      setEditItems(detailInvoice.items.map(item => ({ ...item })));
    }
    setIsEditing(false);
  }

  // 항목 값 변경
  function handleItemChange(index: number, field: keyof InvoiceItem, value: string | number) {
    const updated = [...editItems];
    if (field === '수량' || field === '단가' || field === '금액') {
      updated[index][field] = Number(value) || 0;
    } else {
      updated[index][field] = String(value);
    }
    // 금액 자동 계산 (수량 또는 단가 변경 시)
    if (field === '수량' || field === '단가') {
      updated[index]['금액'] = updated[index]['수량'] * updated[index]['단가'];
    }
    setEditItems(updated);
  }

  // 항목 추가
  function handleAddItem() {
    setEditItems([...editItems, { 항목: '', 수량: 0, 단가: 0, 금액: 0, 비고: '' }]);
  }

  // 항목 삭제
  function handleRemoveItem(index: number) {
    setEditItems(editItems.filter((_, i) => i !== index));
  }

  // 현재 사용자 닉네임 가져오기
  function getCurrentUserNickname(): string {
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        return user.nickname || '시스템';
      }
    } catch {}
    return '시스템';
  }

  // 저장
  async function handleSave() {
    if (!detailInvoice) return;
    
    try {
      setSaving(true);
      setError(null);
      
      const userNickname = getCurrentUserNickname();
      
      const res = await fetch(`${API_URL}/invoices/${detailInvoice.invoice_id}/items`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: editItems, user_nickname: userNickname }),
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '저장 실패');
      }
      
      const result = await res.json();
      
      // 상세 정보 다시 로드
      await handleViewDetail(detailInvoice.invoice_id);
      setIsEditing(false);
      setSuccess(`✅ 저장 완료 (총액: ₩${result.total_amount.toLocaleString()}, 수정자: ${result.modified_by})`);
      
      // 목록 새로고침
      loadInvoices();
      
      setTimeout(() => setSuccess(null), 3000);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  // 삭제 (관리자만)
  async function handleDelete(invoiceId: number) {
    if (!isAdmin) {
      setError('삭제 권한이 없습니다. 관리자만 삭제할 수 있습니다.');
      return;
    }
    if (!confirm(`인보이스 #${invoiceId}을(를) 삭제하시겠습니까?`)) return;
    
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/invoices/${invoiceId}?token=${token}`, { method: 'DELETE' });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || '삭제 실패');
      }
      loadInvoices();
      if (detailInvoice?.invoice_id === invoiceId) {
        setDetailInvoice(null);
      }
      setSuccess(`✅ 인보이스 #${invoiceId} 삭제 완료`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  // 선택 삭제 (관리자만)
  async function handleDeleteSelected() {
    if (!isAdmin) {
      setError('삭제 권한이 없습니다. 관리자만 삭제할 수 있습니다.');
      return;
    }
    if (selectedIds.length === 0) return;
    if (!confirm(`선택된 ${selectedIds.length}건의 인보이스를 삭제하시겠습니까?`)) return;
    
    try {
      const token = localStorage.getItem('token');
      for (const id of selectedIds) {
        const res = await fetch(`${API_URL}/invoices/${id}?token=${token}`, { method: 'DELETE' });
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || '삭제 실패');
        }
      }
      setSelectedIds([]);
      setSelectAll(false);
      loadInvoices();
      setSuccess(`✅ ${selectedIds.length}건 삭제 완료`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  // 확정
  async function handleConfirm(invoiceId: number) {
    try {
      const userNickname = getCurrentUserNickname();
      const res = await fetch(
        `${API_URL}/invoices/${invoiceId}/confirm?user_nickname=${encodeURIComponent(userNickname)}`,
        { method: 'POST' }
      );
      if (res.ok) {
        loadInvoices();
        if (detailInvoice?.invoice_id === invoiceId) {
          setDetailInvoice({ ...detailInvoice, status: '확정' });
        }
        setSuccess(`✅ 인보이스 #${invoiceId} 확정 완료 (${userNickname})`);
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '확정 실패');
    }
  }

  // 미확정으로 변경
  async function handleUnconfirm(invoiceId: number) {
    try {
      const userNickname = getCurrentUserNickname();
      const res = await fetch(
        `${API_URL}/invoices/${invoiceId}/unconfirm?user_nickname=${encodeURIComponent(userNickname)}`,
        { method: 'POST' }
      );
      if (res.ok) {
        loadInvoices();
        if (detailInvoice?.invoice_id === invoiceId) {
          setDetailInvoice({ ...detailInvoice, status: '미확정' });
        }
        setSuccess(`⏪ 인보이스 #${invoiceId} 미확정으로 변경 (${userNickname})`);
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '미확정 변경 실패');
    }
  }

  // 엑셀 다운로드 - 전체
  function handleExportAll() {
    const params = new URLSearchParams();
    if (selectedPeriod) params.append('period', selectedPeriod);
    if (selectedVendor) params.append('vendor', selectedVendor);
    window.open(`${API_URL}/invoices/export/xlsx?${params.toString()}`, '_blank');
  }

  // 엑셀 다운로드 - 선택
  function handleExportSelected() {
    if (selectedIds.length === 0) {
      alert('선택된 인보이스가 없습니다.');
      return;
    }
    const idsStr = selectedIds.join(',');
    window.open(`${API_URL}/invoices/export/xlsx?invoice_ids=${idsStr}`, '_blank');
  }

  // 엑셀 다운로드 - 단일
  function handleExportSingle(invoiceId: number) {
    window.open(`${API_URL}/invoices/${invoiceId}/export/xlsx`, '_blank');
  }

  // 편집 항목 합계 계산
  const editTotalAmount = editItems.reduce((sum, item) => sum + (item.금액 || 0), 0);

  const formatNumber = (n: number) => n.toLocaleString('ko-KR');

  if (loading) {
    return <Loading text="인보이스 목록 로딩 중..." />;
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>📜 인보이스 목록</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 필터 */}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>기간 (YYYY-MM)</label>
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px', minWidth: '150px' }}
            >
              <option value="">전체</option>
              {periods.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>업체</label>
            <select
              value={selectedVendor}
              onChange={(e) => setSelectedVendor(e.target.value)}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px', minWidth: '150px' }}
            >
              <option value="">전체</option>
              {vendors.map(v => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>상태</label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px', minWidth: '100px' }}
            >
              <option value="">전체</option>
              <option value="확정">확정</option>
              <option value="미확정">미확정</option>
            </select>
          </div>
          <button
            onClick={loadInvoices}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#2196F3',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            🔄 새로고침
          </button>
        </div>
      </Card>

      {/* 통계 및 버튼 */}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <span style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>
              📋 {invoices.length}건
            </span>
            <span style={{ marginLeft: '1rem', color: '#666' }}>
              / 기간: {selectedPeriod || '전체'} / 총 합계: <strong>₩{formatNumber(sumAmount)}</strong>
            </span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={handleExportAll}
              disabled={invoices.length === 0}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: invoices.length === 0 ? '#ccc' : '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: invoices.length === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              📥 전체 XLSX
            </button>
            <button
              onClick={handleExportSelected}
              disabled={selectedIds.length === 0}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: selectedIds.length === 0 ? '#ccc' : '#2196F3',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: selectedIds.length === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              📥 선택 XLSX ({selectedIds.length}건)
            </button>
            {isAdmin && (
              <button
                onClick={handleDeleteSelected}
                disabled={selectedIds.length === 0}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: selectedIds.length === 0 ? '#ccc' : '#f44336',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: selectedIds.length === 0 ? 'not-allowed' : 'pointer',
                }}
              >
                🗑️ 선택 삭제 ({selectedIds.length}건)
              </button>
            )}
          </div>
        </div>
      </Card>

      {/* 목록 */}
      <Card>
        {invoices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#666' }}>
            인보이스가 없습니다.
            <div style={{ marginTop: '1rem' }}>
              <a href="/invoice" style={{ color: '#2196F3', textDecoration: 'none' }}>
                ➕ 새 인보이스 계산
              </a>
            </div>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={selectAll}
                  onChange={handleSelectAll}
                />
                전체 선택
              </label>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd', width: '50px' }}></th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>번호</th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>업체</th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>기간</th>
                    <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>금액</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>상태</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>수정/확정</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd' }}>작업</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.invoice_id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(inv.invoice_id)}
                          onChange={() => handleToggleSelect(inv.invoice_id)}
                        />
                      </td>
                      <td style={{ padding: '0.5rem' }}>
                        <strong>#{inv.invoice_id}</strong>
                      </td>
                      <td style={{ padding: '0.5rem' }}>{inv.vendor}</td>
                      <td style={{ padding: '0.5rem' }}>
                        {inv.period_from} ~ {inv.period_to}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                        ₩{formatNumber(inv.total_amount)}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                        <span
                          style={{
                            padding: '0.25rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            backgroundColor: inv.status === '확정' ? '#d1e7dd' : '#fff3cd',
                            color: inv.status === '확정' ? '#0f5132' : '#664d03',
                          }}
                        >
                          {inv.status}
                        </span>
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'center', fontSize: '0.75rem' }}>
                        {inv.modified_by && (
                          <div style={{ color: '#666' }}>
                            ✏️ {inv.modified_by}
                          </div>
                        )}
                        {inv.confirmed_by && (
                          <div style={{ color: '#0f5132' }}>
                            ✅ {inv.confirmed_by}
                          </div>
                        )}
                        {!inv.modified_by && !inv.confirmed_by && (
                          <span style={{ color: '#999' }}>-</span>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: '0.25rem', justifyContent: 'center' }}>
                          <button
                            onClick={() => handleViewDetail(inv.invoice_id)}
                            style={{
                              padding: '0.25rem 0.5rem',
                              fontSize: '0.75rem',
                              backgroundColor: '#2196F3',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                            }}
                          >
                            상세/수정
                          </button>
                          <button
                            onClick={() => handleExportSingle(inv.invoice_id)}
                            style={{
                              padding: '0.25rem 0.5rem',
                              fontSize: '0.75rem',
                              backgroundColor: '#4CAF50',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                            }}
                          >
                            XLSX
                          </button>
                          {inv.status === '확정' ? (
                            <button
                              onClick={() => handleUnconfirm(inv.invoice_id)}
                              style={{
                                padding: '0.25rem 0.5rem',
                                fontSize: '0.75rem',
                                backgroundColor: '#9e9e9e',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer',
                              }}
                              title="확정 해제"
                            >
                              확정해제
                            </button>
                          ) : (
                            <button
                              onClick={() => handleConfirm(inv.invoice_id)}
                              style={{
                                padding: '0.25rem 0.5rem',
                                fontSize: '0.75rem',
                                backgroundColor: '#4CAF50',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer',
                              }}
                              title="인보이스 확정"
                            >
                              확정
                            </button>
                          )}
                          {isAdmin && (
                            <button
                              onClick={() => handleDelete(inv.invoice_id)}
                              style={{
                                padding: '0.25rem 0.5rem',
                                fontSize: '0.75rem',
                                backgroundColor: '#f44336',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer',
                              }}
                            >
                              삭제
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      {/* 상세 보기 / 편집 모달 */}
      {(loadingDetail || detailInvoice) && (
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
          onClick={() => { setDetailInvoice(null); setIsEditing(false); }}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              maxWidth: '1000px',
              maxHeight: '90vh',
              overflow: 'auto',
              width: '95%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {loadingDetail ? (
              <Loading text="상세 정보 로딩 중..." />
            ) : detailInvoice && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h2>인보이스 #{detailInvoice.invoice_id} {isEditing ? '수정' : '상세'}</h2>
                  <button
                    onClick={() => { setDetailInvoice(null); setIsEditing(false); }}
                    style={{
                      background: 'none',
                      border: 'none',
                      fontSize: '1.5rem',
                      cursor: 'pointer',
                    }}
                  >
                    ✕
                  </button>
                </div>
                
                {/* 인보이스 기본 정보 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                  <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <div style={{ fontWeight: 'bold' }}>{detailInvoice.vendor}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>업체</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <div style={{ fontWeight: 'bold' }}>{detailInvoice.period_from}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>시작일</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <div style={{ fontWeight: 'bold' }}>{detailInvoice.period_to}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>종료일</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: isEditing ? '#fff3e0' : '#e8f5e9', borderRadius: '4px' }}>
                    <div style={{ fontWeight: 'bold', color: isEditing ? '#e65100' : 'green' }}>
                      ₩{formatNumber(isEditing ? editTotalAmount : detailInvoice.total_amount)}
                    </div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>총 금액{isEditing && ' (수정중)'}</div>
                  </div>
                </div>

                {/* 편집/보기 모드 전환 버튼 */}
                <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem' }}>
                  {!isEditing ? (
                    <button
                      onClick={handleStartEdit}
                      style={{
                        padding: '0.5rem 1rem',
                        backgroundColor: '#ff9800',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                      }}
                    >
                      ✏️ 수정하기
                    </button>
                  ) : (
                    <>
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
                      <button
                        onClick={handleCancelEdit}
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
                        onClick={handleAddItem}
                        style={{
                          padding: '0.5rem 1rem',
                          backgroundColor: '#2196F3',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                        }}
                      >
                        ➕ 항목 추가
                      </button>
                    </>
                  )}
                </div>

                {/* 항목 테이블 */}
                <h3 style={{ marginBottom: '0.5rem' }}>📝 항목</h3>
                {(isEditing ? editItems : detailInvoice.items).length === 0 ? (
                  <p style={{ color: '#666' }}>항목이 없습니다.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#f5f5f5' }}>
                          <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd', minWidth: '200px' }}>항목</th>
                          <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd', minWidth: '80px' }}>수량</th>
                          <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd', minWidth: '100px' }}>단가</th>
                          <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd', minWidth: '100px' }}>금액</th>
                          <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd', minWidth: '150px' }}>비고</th>
                          {isEditing && <th style={{ padding: '0.5rem', borderBottom: '2px solid #ddd', width: '50px' }}></th>}
                        </tr>
                      </thead>
                      <tbody>
                        {(isEditing ? editItems : detailInvoice.items).map((item, idx) => (
                          <tr key={idx}>
                            <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                              {isEditing ? (
                                <input
                                  type="text"
                                  value={item.항목}
                                  onChange={(e) => handleItemChange(idx, '항목', e.target.value)}
                                  style={{ width: '100%', padding: '0.25rem', border: '1px solid #ddd', borderRadius: '4px' }}
                                />
                              ) : item.항목}
                            </td>
                            <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                              {isEditing ? (
                                <input
                                  type="number"
                                  value={item.수량}
                                  onChange={(e) => handleItemChange(idx, '수량', e.target.value)}
                                  style={{ width: '80px', padding: '0.25rem', border: '1px solid #ddd', borderRadius: '4px', textAlign: 'right' }}
                                />
                              ) : formatNumber(item.수량)}
                            </td>
                            <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                              {isEditing ? (
                                <input
                                  type="number"
                                  value={item.단가}
                                  onChange={(e) => handleItemChange(idx, '단가', e.target.value)}
                                  style={{ width: '100px', padding: '0.25rem', border: '1px solid #ddd', borderRadius: '4px', textAlign: 'right' }}
                                />
                              ) : `₩${formatNumber(item.단가)}`}
                            </td>
                            <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                              {isEditing ? (
                                <input
                                  type="number"
                                  value={item.금액}
                                  onChange={(e) => handleItemChange(idx, '금액', e.target.value)}
                                  style={{ width: '100px', padding: '0.25rem', border: '1px solid #ddd', borderRadius: '4px', textAlign: 'right', backgroundColor: '#f5f5f5' }}
                                />
                              ) : `₩${formatNumber(item.금액)}`}
                            </td>
                            <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: '#666' }}>
                              {isEditing ? (
                                <input
                                  type="text"
                                  value={item.비고}
                                  onChange={(e) => handleItemChange(idx, '비고', e.target.value)}
                                  style={{ width: '100%', padding: '0.25rem', border: '1px solid #ddd', borderRadius: '4px' }}
                                />
                              ) : (item.비고 || '-')}
                            </td>
                            {isEditing && (
                              <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', textAlign: 'center' }}>
                                <button
                                  onClick={() => handleRemoveItem(idx)}
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
                                  ✕
                                </button>
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr style={{ fontWeight: 'bold', backgroundColor: '#f5f5f5' }}>
                          <td colSpan={3} style={{ padding: '0.5rem' }}>합계</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                            ₩{formatNumber(isEditing ? editTotalAmount : detailInvoice.total_amount)}
                          </td>
                          <td colSpan={isEditing ? 2 : 1}></td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}

                {/* 하단 버튼 */}
                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => handleExportSingle(detailInvoice.invoice_id)}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#4CAF50',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                    }}
                  >
                    📥 이 인보이스 XLSX
                  </button>
                  {detailInvoice.status === '확정' ? (
                    <button
                      onClick={() => handleUnconfirm(detailInvoice.invoice_id)}
                      style={{
                        padding: '0.5rem 1rem',
                        backgroundColor: '#9e9e9e',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                      }}
                    >
                      ⏪ 확정 해제
                    </button>
                  ) : (
                    <button
                      onClick={() => handleConfirm(detailInvoice.invoice_id)}
                      style={{
                        padding: '0.5rem 1rem',
                        backgroundColor: '#4CAF50',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                      }}
                    >
                      ✅ 인보이스 확정
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
