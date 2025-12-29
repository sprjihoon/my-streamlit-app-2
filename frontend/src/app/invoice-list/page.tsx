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
 * 기존 Streamlit invoice_list.py와 동일한 기능
 */
export default function InvoiceListPage() {
  // 목록 상태
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // 필터
  const [periods, setPeriods] = useState<string[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>('');
  const [vendors, setVendors] = useState<string[]>([]);
  const [selectedVendor, setSelectedVendor] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  
  // 선택 상태
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectAll, setSelectAll] = useState(false);
  
  // 상세 보기
  const [detailInvoice, setDetailInvoice] = useState<InvoiceDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  
  // 통계
  const [sumAmount, setSumAmount] = useState(0);

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
        // 기본값: 가장 최근 기간
        if (!selectedPeriod && data.periods.length > 0) {
          // setSelectedPeriod(data.periods[0]);
        }
      }
      
      // 고유 업체명 추출
      const uniqueVendors = [...new Set(data.invoices?.map((i: Invoice) => i.vendor) || [])];
      setVendors(uniqueVendors.filter(v => v) as string[]);
      
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
      const res = await fetch(`${API_URL}/invoices/${invoiceId}`);
      const data = await res.json();
      setDetailInvoice(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '상세 조회 실패');
    } finally {
      setLoadingDetail(false);
    }
  }

  // 삭제
  async function handleDelete(invoiceId: number) {
    if (!confirm(`인보이스 #${invoiceId}을(를) 삭제하시겠습니까?`)) return;
    
    try {
      const res = await fetch(`${API_URL}/invoices/${invoiceId}`, { method: 'DELETE' });
      if (res.ok) {
        loadInvoices();
        if (detailInvoice?.invoice_id === invoiceId) {
          setDetailInvoice(null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  // 선택 삭제
  async function handleDeleteSelected() {
    if (selectedIds.length === 0) return;
    if (!confirm(`선택된 ${selectedIds.length}건의 인보이스를 삭제하시겠습니까?`)) return;
    
    try {
      for (const id of selectedIds) {
        await fetch(`${API_URL}/invoices/${id}`, { method: 'DELETE' });
      }
      setSelectedIds([]);
      setSelectAll(false);
      loadInvoices();
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  // 확정
  async function handleConfirm(invoiceId: number) {
    try {
      const res = await fetch(`${API_URL}/invoices/${invoiceId}/confirm`, { method: 'POST' });
      if (res.ok) {
        loadInvoices();
        if (detailInvoice?.invoice_id === invoiceId) {
          setDetailInvoice({ ...detailInvoice, status: '확정' });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '확정 실패');
    }
  }

  // 엑셀 다운로드 - 전체 (필터 적용)
  function handleExportAll() {
    const params = new URLSearchParams();
    if (selectedPeriod) params.append('period', selectedPeriod);
    if (selectedVendor) params.append('vendor', selectedVendor);
    window.open(`${API_URL}/invoices/export/xlsx?${params.toString()}`, '_blank');
  }

  // 엑셀 다운로드 - 선택 항목
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

  const formatNumber = (n: number) => n.toLocaleString('ko-KR');

  if (loading) {
    return <Loading text="인보이스 목록 로딩 중..." />;
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>📜 인보이스 목록</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

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
            {/* 전체 선택 */}
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

            {/* 테이블 */}
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
                            상세
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
                          {inv.status !== '확정' && (
                            <button
                              onClick={() => handleConfirm(inv.invoice_id)}
                              style={{
                                padding: '0.25rem 0.5rem',
                                fontSize: '0.75rem',
                                backgroundColor: '#ff9800',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer',
                              }}
                            >
                              확정
                            </button>
                          )}
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

      {/* 상세 보기 모달 */}
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
          onClick={() => setDetailInvoice(null)}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              maxWidth: '900px',
              maxHeight: '80vh',
              overflow: 'auto',
              width: '90%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {loadingDetail ? (
              <Loading text="상세 정보 로딩 중..." />
            ) : detailInvoice && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h2>인보이스 #{detailInvoice.invoice_id} 상세</h2>
                  <button
                    onClick={() => setDetailInvoice(null)}
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
                  <div style={{ textAlign: 'center', padding: '1rem', backgroundColor: '#e8f5e9', borderRadius: '4px' }}>
                    <div style={{ fontWeight: 'bold', color: 'green' }}>₩{formatNumber(detailInvoice.total_amount)}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>총 금액</div>
                  </div>
                </div>

                <h3 style={{ marginBottom: '0.5rem' }}>📝 항목</h3>
                {detailInvoice.items.length === 0 ? (
                  <p style={{ color: '#666' }}>항목이 없습니다.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ backgroundColor: '#f5f5f5' }}>
                        <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>항목</th>
                        <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>수량</th>
                        <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>단가</th>
                        <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>금액</th>
                        <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>비고</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailInvoice.items.map((item, idx) => (
                        <tr key={idx}>
                          <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.항목}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.수량)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>₩{formatNumber(item.단가)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>₩{formatNumber(item.금액)}</td>
                          <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: '#666' }}>{item.비고 || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr style={{ fontWeight: 'bold', backgroundColor: '#f5f5f5' }}>
                        <td colSpan={3} style={{ padding: '0.5rem' }}>합계</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>₩{formatNumber(detailInvoice.total_amount)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                )}

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
                  {detailInvoice.status !== '확정' && (
                    <button
                      onClick={() => handleConfirm(detailInvoice.invoice_id)}
                      style={{
                        padding: '0.5rem 1rem',
                        backgroundColor: '#ff9800',
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
