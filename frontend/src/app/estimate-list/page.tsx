'use client';

import { useState, useEffect } from 'react';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const BRAND_LABEL: Record<string, string> = { fashion: '패션', beauty: '뷰티', etc: '기타' };
const PAGE_SIZES = [10, 30, 50] as const;

interface EstimateRow {
  id: number;
  company_name: string;
  contact: string;
  email: string;
  total_amount: number;
  brand_type: string;
  created_at: string;
}

interface EstimateItem {
  항목: string;
  수량: number;
  단가: number;
  금액: number;
  비고?: string;
}

interface EstimateDetail extends EstimateRow {
  items: EstimateItem[];
}

function fmt(n: number) {
  return n.toLocaleString('ko-KR');
}

export default function EstimateListPage() {
  const [items, setItems] = useState<EstimateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 상세/수정 모달
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<EstimateDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // 수정 폼 상태
  const [editCompanyName, setEditCompanyName] = useState('');
  const [editContact, setEditContact] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editBrandType, setEditBrandType] = useState('fashion');
  const [editItems, setEditItems] = useState<EstimateItem[]>([]);

  // 삭제 확인
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  // PDF 다운로드 로딩
  const [pdfLoading, setPdfLoading] = useState(false);

  // 새 견적서 생성 모달
  const [isCreating, setIsCreating] = useState(false);
  const [createCompanyName, setCreateCompanyName] = useState('');
  const [createContact, setCreateContact] = useState('');
  const [createEmail, setCreateEmail] = useState('');
  const [createBrandType, setCreateBrandType] = useState('fashion');
  const [createItems, setCreateItems] = useState<EstimateItem[]>([
    { 항목: '', 수량: 1, 단가: 0, 금액: 0, 비고: '' },
  ]);
  const [createLoading, setCreateLoading] = useState(false);

  useEffect(() => {
    loadEstimates();
  }, [page, pageSize]);

  async function loadEstimates() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('page_size', String(pageSize));
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);

      const res = await fetch(`${API_BASE}/estimate/list?${params.toString()}`);
      if (!res.ok) throw new Error('목록 로드 실패');
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : '목록 로드 실패');
    } finally {
      setLoading(false);
    }
  }

  function handleSearch() {
    setPage(1);
    loadEstimates();
  }

  async function loadDetail(id: number) {
    setSelectedId(id);
    setDetailLoading(true);
    setIsEditing(false);
    try {
      const res = await fetch(`${API_BASE}/estimate/detail/${id}`);
      if (!res.ok) throw new Error('상세 로드 실패');
      const data: EstimateDetail = await res.json();
      setDetail(data);
      setEditCompanyName(data.company_name);
      setEditContact(data.contact);
      setEditEmail(data.email);
      setEditBrandType(data.brand_type);
      setEditItems(data.items.map(item => ({ ...item })));
    } catch (err) {
      setError(err instanceof Error ? err.message : '상세 로드 실패');
      setSelectedId(null);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeModal() {
    setSelectedId(null);
    setDetail(null);
    setIsEditing(false);
    setEditItems([]);
  }

  function startEditing() {
    if (detail) {
      setEditItems(detail.items.map(item => ({ ...item })));
      setIsEditing(true);
    }
  }

  function cancelEditing() {
    if (detail) {
      setEditItems(detail.items.map(item => ({ ...item })));
    }
    setIsEditing(false);
  }

  function updateEditItem(index: number, field: keyof EstimateItem, value: string | number) {
    setEditItems(prev => {
      const newItems = [...prev];
      if (field === '항목' || field === '비고') {
        newItems[index] = { ...newItems[index], [field]: value as string };
      } else {
        const numValue = typeof value === 'string' ? parseInt(value) || 0 : value;
        newItems[index] = { ...newItems[index], [field]: numValue };
        if (field === '수량' || field === '단가') {
          newItems[index].금액 = newItems[index].수량 * newItems[index].단가;
        }
      }
      return newItems;
    });
  }

  function addEditItem() {
    setEditItems(prev => [...prev, { 항목: '', 수량: 0, 단가: 0, 금액: 0, 비고: '' }]);
  }

  function removeEditItem(index: number) {
    setEditItems(prev => prev.filter((_, i) => i !== index));
  }

  function getEditTotalAmount() {
    return editItems.reduce((sum, item) => sum + (item.금액 || 0), 0);
  }

  function openCreateModal() {
    setCreateCompanyName('');
    setCreateContact('');
    setCreateEmail('');
    setCreateBrandType('fashion');
    setCreateItems([{ 항목: '', 수량: 1, 단가: 0, 금액: 0, 비고: '' }]);
    setIsCreating(true);
  }

  function closeCreateModal() {
    setIsCreating(false);
  }

  function updateCreateItem(index: number, field: keyof EstimateItem, value: string | number) {
    setCreateItems(prev => {
      const newItems = [...prev];
      if (field === '항목' || field === '비고') {
        newItems[index] = { ...newItems[index], [field]: value as string };
      } else {
        const numValue = typeof value === 'string' ? parseInt(value) || 0 : value;
        newItems[index] = { ...newItems[index], [field]: numValue };
        if (field === '수량' || field === '단가') {
          newItems[index].금액 = newItems[index].수량 * newItems[index].단가;
        }
      }
      return newItems;
    });
  }

  function addCreateItem() {
    setCreateItems(prev => [...prev, { 항목: '', 수량: 1, 단가: 0, 금액: 0, 비고: '' }]);
  }

  function removeCreateItem(index: number) {
    setCreateItems(prev => prev.filter((_, i) => i !== index));
  }

  function getCreateTotalAmount() {
    return createItems.reduce((sum, item) => sum + (item.금액 || 0), 0);
  }

  async function handleCreateSave() {
    if (!createCompanyName.trim()) {
      setError('업체명을 입력해주세요.');
      return;
    }
    if (createItems.length === 0 || createItems.every(it => !it.항목.trim())) {
      setError('최소 1개 이상의 견적 항목을 입력해주세요.');
      return;
    }
    setCreateLoading(true);
    try {
      const totalAmount = getCreateTotalAmount();
      const res = await fetch(`${API_BASE}/estimate/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: createCompanyName,
          contact: createContact,
          email: createEmail,
          brand_type: createBrandType,
          items: createItems.filter(it => it.항목.trim()),
          total_amount: totalAmount,
        }),
      });
      if (!res.ok) throw new Error('견적서 저장 실패');
      setSuccess('견적서가 생성되었습니다.');
      closeCreateModal();
      loadEstimates();
    } catch (err) {
      setError(err instanceof Error ? err.message : '견적서 저장 실패');
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleSaveEdit() {
    if (!detail) return;
    try {
      const totalAmount = getEditTotalAmount();
      const res = await fetch(`${API_BASE}/estimate/${detail.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: editCompanyName,
          contact: editContact,
          email: editEmail,
          brand_type: editBrandType,
          items: editItems,
          total_amount: totalAmount,
        }),
      });
      if (!res.ok) throw new Error('수정 실패');
      setSuccess('견적서가 수정되었습니다.');
      setIsEditing(false);
      loadEstimates();
      loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '수정 실패');
    }
  }

  async function handleDelete(id: number) {
    try {
      const res = await fetch(`${API_BASE}/estimate/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('삭제 실패');
      setSuccess('견적서가 삭제되었습니다.');
      setDeleteConfirmId(null);
      closeModal();
      loadEstimates();
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }

  async function handleDownloadPdf() {
    if (!detail) return;
    setPdfLoading(true);
    try {
      const res = await fetch(`${API_BASE}/estimate/export/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: detail.company_name,
          contact: detail.contact,
          email: detail.email,
          items: detail.items,
          total_amount: detail.total_amount,
          brand_type: detail.brand_type,
        }),
      });
      if (!res.ok) throw new Error('PDF 생성 실패');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `견적서_${detail.company_name || 'estimate'}_${detail.created_at.split(' ')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      setSuccess('PDF가 다운로드되었습니다.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF 다운로드 실패');
    } finally {
      setPdfLoading(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const inputStyle: React.CSSProperties = {
    padding: '0.5rem 0.65rem', border: '1px solid #d1d5db', borderRadius: 8,
    fontSize: '0.85rem', outline: 'none', background: '#fff',
  };
  const btnStyle: React.CSSProperties = {
    padding: '0.5rem 1rem', border: 'none', borderRadius: 8,
    fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer', transition: 'all .15s',
  };
  const smallInputStyle: React.CSSProperties = {
    padding: '0.35rem 0.5rem', border: '1px solid #d1d5db', borderRadius: 6,
    fontSize: '0.8rem', outline: 'none', background: '#fff',
  };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#1f2937', margin: 0 }}>
          견적서 목록
        </h1>
        <button
          onClick={openCreateModal}
          style={{
            padding: '0.55rem 1.2rem', border: 'none', borderRadius: 8,
            background: 'linear-gradient(135deg, #10b981, #059669)', color: '#fff',
            fontSize: '0.875rem', fontWeight: 700, cursor: 'pointer',
            boxShadow: '0 2px 6px rgba(16,185,129,.35)',
          }}
        >
          + 새 견적서 만들기
        </button>
      </div>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 필터 바 */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end',
        background: '#fff', padding: '1rem', borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,.08)', marginBottom: '1rem',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>시작일</label>
          <input type="date" style={inputStyle} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>종료일</label>
          <input type="date" style={inputStyle} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>표시 개수</label>
          <select style={{ ...inputStyle, appearance: 'auto' as const }} value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>{s}개</option>
            ))}
          </select>
        </div>
        <button onClick={handleSearch} style={{ ...btnStyle, background: '#3b82f6', color: '#fff' }}>
          검색
        </button>
        {(dateFrom || dateTo) && (
          <button onClick={() => { setDateFrom(''); setDateTo(''); setTimeout(() => { setPage(1); loadEstimates(); }, 0); }} style={{ ...btnStyle, background: '#e5e7eb', color: '#374151' }}>
            초기화
          </button>
        )}
      </div>

      {/* 테이블 */}
      {loading ? (
        <div style={{ padding: '3rem', textAlign: 'center' }}><Loading /></div>
      ) : items.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '3rem', background: '#fff',
          borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,.08)', color: '#9ca3af',
        }}>
          저장된 견적서가 없습니다.
        </div>
      ) : (
        <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,.08)', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' as const }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>날짜</th>
                  <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>업체명</th>
                  <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>연락처</th>
                  <th style={{ padding: '0.7rem 0.6rem', textAlign: 'center', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>유형</th>
                  <th style={{ padding: '0.7rem 0.6rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>총액</th>
                  <th style={{ padding: '0.7rem 0.6rem', textAlign: 'center', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>관리</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '0.6rem', whiteSpace: 'nowrap', color: '#6b7280' }}>{row.created_at}</td>
                    <td style={{ padding: '0.6rem', fontWeight: 500 }}>{row.company_name || '-'}</td>
                    <td style={{ padding: '0.6rem', color: '#6b7280' }}>{row.contact || '-'}</td>
                    <td style={{ padding: '0.6rem', textAlign: 'center' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 10px', borderRadius: 12,
                        fontSize: '0.75rem', fontWeight: 600,
                        background: row.brand_type === 'fashion' ? '#dbeafe' : row.brand_type === 'beauty' ? '#fce7f3' : '#f3f4f6',
                        color: row.brand_type === 'fashion' ? '#1d4ed8' : row.brand_type === 'beauty' ? '#be185d' : '#374151',
                      }}>
                        {BRAND_LABEL[row.brand_type] || row.brand_type}
                      </span>
                    </td>
                    <td style={{ padding: '0.6rem', textAlign: 'right', fontWeight: 600 }}>₩{fmt(row.total_amount)}</td>
                    <td style={{ padding: '0.6rem', textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                        <button
                          onClick={() => loadDetail(row.id)}
                          style={{
                            padding: '4px 10px', fontSize: '0.75rem', fontWeight: 500,
                            background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
                          }}
                        >
                          상세
                        </button>
                        <button
                          onClick={() => setDeleteConfirmId(row.id)}
                          style={{
                            padding: '4px 10px', fontSize: '0.75rem', fontWeight: 500,
                            background: '#ef4444', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
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

          {/* 페이지네이션 */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '0.75rem 1rem', borderTop: '1px solid #e2e8f0', fontSize: '0.82rem', color: '#6b7280',
          }}>
            <span>총 {total}건 / {totalPages} 페이지</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                style={{
                  ...btnStyle, padding: '0.35rem 0.75rem', fontSize: '0.8rem',
                  background: page <= 1 ? '#f3f4f6' : '#e5e7eb', color: page <= 1 ? '#d1d5db' : '#374151',
                  cursor: page <= 1 ? 'default' : 'pointer',
                }}
              >
                이전
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                let p: number;
                if (totalPages <= 5) {
                  p = i + 1;
                } else if (page <= 3) {
                  p = i + 1;
                } else if (page >= totalPages - 2) {
                  p = totalPages - 4 + i;
                } else {
                  p = page - 2 + i;
                }
                return (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    style={{
                      ...btnStyle, padding: '0.35rem 0.65rem', fontSize: '0.8rem', minWidth: 32,
                      background: p === page ? '#3b82f6' : '#f3f4f6',
                      color: p === page ? '#fff' : '#374151',
                    }}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                style={{
                  ...btnStyle, padding: '0.35rem 0.75rem', fontSize: '0.8rem',
                  background: page >= totalPages ? '#f3f4f6' : '#e5e7eb', color: page >= totalPages ? '#d1d5db' : '#374151',
                  cursor: page >= totalPages ? 'default' : 'pointer',
                }}
              >
                다음
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 새 견적서 생성 모달 */}
      {isCreating && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem',
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, maxWidth: 820, width: '100%', maxHeight: '92vh',
            overflow: 'hidden', display: 'flex', flexDirection: 'column',
            boxShadow: '0 20px 50px rgba(0,0,0,.25)',
          }}>
            {/* 헤더 */}
            <div style={{
              padding: '1rem 1.25rem', borderBottom: '1px solid #e2e8f0',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              background: 'linear-gradient(135deg, #10b981, #059669)',
            }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', margin: 0 }}>
                새 견적서 만들기
              </h2>
              <button
                onClick={closeCreateModal}
                style={{
                  background: 'rgba(255,255,255,.2)', border: 'none', borderRadius: 8,
                  padding: '6px 12px', color: '#fff', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                }}
              >
                닫기
              </button>
            </div>

            {/* 본문 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem' }}>
              {/* 기본 정보 */}
              <div style={{ background: '#f0fdf4', borderRadius: 12, padding: '1rem', marginBottom: '1.25rem', border: '1px solid #bbf7d0' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#065f46', marginBottom: '0.75rem', margin: '0 0 0.75rem' }}>
                  기본 정보
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>
                      업체명 <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      value={createCompanyName}
                      onChange={(e) => setCreateCompanyName(e.target.value)}
                      placeholder="업체명 입력"
                      style={{ ...inputStyle, width: '100%', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>연락처</label>
                    <input
                      type="text"
                      value={createContact}
                      onChange={(e) => setCreateContact(e.target.value)}
                      placeholder="010-0000-0000"
                      style={{ ...inputStyle, width: '100%', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>이메일</label>
                    <input
                      type="email"
                      value={createEmail}
                      onChange={(e) => setCreateEmail(e.target.value)}
                      placeholder="example@email.com"
                      style={{ ...inputStyle, width: '100%', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>브랜드 유형</label>
                    <select
                      value={createBrandType}
                      onChange={(e) => setCreateBrandType(e.target.value)}
                      style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', appearance: 'auto' as const }}
                    >
                      <option value="fashion">패션</option>
                      <option value="beauty">뷰티</option>
                      <option value="etc">기타</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* 견적 항목 */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>
                    견적 항목
                  </h3>
                  <button
                    onClick={addCreateItem}
                    style={{
                      padding: '4px 12px', fontSize: '0.75rem', fontWeight: 600,
                      background: '#10b981', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
                    }}
                  >
                    + 항목 추가
                  </button>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                    <thead>
                      <tr style={{ background: '#f1f5f9' }}>
                        <th style={{ padding: '0.5rem', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 140 }}>항목명</th>
                        <th style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 80 }}>수량</th>
                        <th style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 100 }}>단가 (₩)</th>
                        <th style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 110 }}>금액</th>
                        <th style={{ padding: '0.5rem', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 100 }}>비고</th>
                        <th style={{ padding: '0.5rem', textAlign: 'center', fontWeight: 600, borderBottom: '1px solid #e2e8f0', width: 50 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {createItems.map((item, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '0.4rem' }}>
                            <input
                              type="text"
                              value={item.항목}
                              onChange={(e) => updateCreateItem(idx, '항목', e.target.value)}
                              style={{ ...smallInputStyle, width: '100%' }}
                              placeholder="예: 출고비"
                            />
                          </td>
                          <td style={{ padding: '0.4rem' }}>
                            <input
                              type="number"
                              value={item.수량}
                              onChange={(e) => updateCreateItem(idx, '수량', e.target.value)}
                              style={{ ...smallInputStyle, width: '100%', textAlign: 'right' }}
                              min={0}
                            />
                          </td>
                          <td style={{ padding: '0.4rem' }}>
                            <input
                              type="number"
                              value={item.단가}
                              onChange={(e) => updateCreateItem(idx, '단가', e.target.value)}
                              style={{ ...smallInputStyle, width: '100%', textAlign: 'right' }}
                              min={0}
                            />
                          </td>
                          <td style={{ padding: '0.4rem', textAlign: 'right', fontWeight: 600, color: '#1d4ed8', whiteSpace: 'nowrap' }}>
                            ₩{fmt(item.금액)}
                          </td>
                          <td style={{ padding: '0.4rem' }}>
                            <input
                              type="text"
                              value={item.비고 || ''}
                              onChange={(e) => updateCreateItem(idx, '비고', e.target.value)}
                              style={{ ...smallInputStyle, width: '100%' }}
                              placeholder="비고"
                            />
                          </td>
                          <td style={{ padding: '0.4rem', textAlign: 'center' }}>
                            <button
                              onClick={() => removeCreateItem(idx)}
                              disabled={createItems.length === 1}
                              style={{
                                padding: '2px 8px', fontSize: '0.7rem', fontWeight: 600,
                                background: createItems.length === 1 ? '#f3f4f6' : '#fee2e2',
                                color: createItems.length === 1 ? '#d1d5db' : '#dc2626',
                                border: 'none', borderRadius: 4,
                                cursor: createItems.length === 1 ? 'default' : 'pointer',
                              }}
                            >
                              삭제
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr style={{ background: '#f8fafc' }}>
                        <td colSpan={3} style={{ padding: '0.65rem 0.5rem', textAlign: 'right', fontWeight: 700, fontSize: '0.85rem' }}>
                          합계
                        </td>
                        <td style={{ padding: '0.65rem 0.5rem', textAlign: 'right', fontWeight: 700, color: '#1d4ed8', fontSize: '0.9rem', whiteSpace: 'nowrap' }}>
                          ₩{fmt(getCreateTotalAmount())}
                        </td>
                        <td colSpan={2}></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            </div>

            {/* 푸터 버튼 */}
            <div style={{
              padding: '1rem 1.25rem', borderTop: '1px solid #e2e8f0',
              display: 'flex', gap: 8, justifyContent: 'flex-end',
            }}>
              <button
                onClick={closeCreateModal}
                disabled={createLoading}
                style={{
                  padding: '0.65rem 1.5rem', border: '1px solid #d1d5db', borderRadius: 8,
                  background: '#fff', color: '#374151', fontSize: '0.9rem', fontWeight: 600,
                  cursor: createLoading ? 'not-allowed' : 'pointer', opacity: createLoading ? 0.6 : 1,
                }}
              >
                취소
              </button>
              <button
                onClick={handleCreateSave}
                disabled={createLoading}
                style={{
                  padding: '0.65rem 1.5rem', border: 'none', borderRadius: 8,
                  background: createLoading ? '#9ca3af' : '#10b981', color: '#fff',
                  fontSize: '0.9rem', fontWeight: 700,
                  cursor: createLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {createLoading ? '저장 중...' : '견적서 저장'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 삭제 확인 모달 */}
      {deleteConfirmId !== null && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem',
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, padding: '1.5rem', maxWidth: 360, width: '100%',
            boxShadow: '0 20px 40px rgba(0,0,0,.2)',
          }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem', color: '#1f2937' }}>
              삭제 확인
            </h3>
            <p style={{ fontSize: '0.9rem', color: '#6b7280', marginBottom: '1.5rem' }}>
              견적서 #{deleteConfirmId}를 삭제하시겠습니까?<br />
              이 작업은 되돌릴 수 없습니다.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setDeleteConfirmId(null)}
                style={{
                  flex: 1, padding: '0.65rem', border: '1px solid #d1d5db', borderRadius: 8,
                  background: '#fff', color: '#374151', fontSize: '0.9rem', fontWeight: 600, cursor: 'pointer',
                }}
              >
                취소
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                style={{
                  flex: 1, padding: '0.65rem', border: 'none', borderRadius: 8,
                  background: '#ef4444', color: '#fff', fontSize: '0.9rem', fontWeight: 600, cursor: 'pointer',
                }}
              >
                삭제
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 상세/수정 모달 */}
      {selectedId !== null && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem',
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, maxWidth: 800, width: '100%', maxHeight: '90vh',
            overflow: 'hidden', display: 'flex', flexDirection: 'column',
            boxShadow: '0 20px 40px rgba(0,0,0,.2)',
          }}>
            {/* 헤더 */}
            <div style={{
              padding: '1rem 1.25rem', borderBottom: '1px solid #e2e8f0',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', margin: 0 }}>
                견적서 #{selectedId} {isEditing ? '수정' : '상세'}
              </h2>
              <button
                onClick={closeModal}
                style={{
                  background: 'rgba(255,255,255,.2)', border: 'none', borderRadius: 8,
                  padding: '6px 12px', color: '#fff', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                }}
              >
                닫기
              </button>
            </div>

            {/* 본문 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem' }}>
              {detailLoading ? (
                <div style={{ padding: '3rem', textAlign: 'center' }}><Loading /></div>
              ) : detail ? (
                <>
                  {/* 기본 정보 */}
                  <div style={{
                    background: '#f8fafc', borderRadius: 12, padding: '1rem', marginBottom: '1rem',
                  }}>
                    <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>
                      기본 정보
                    </h3>
                    {isEditing ? (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>업체명</label>
                          <input
                            type="text"
                            value={editCompanyName}
                            onChange={(e) => setEditCompanyName(e.target.value)}
                            style={{ ...inputStyle, width: '100%' }}
                          />
                        </div>
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>연락처</label>
                          <input
                            type="text"
                            value={editContact}
                            onChange={(e) => setEditContact(e.target.value)}
                            style={{ ...inputStyle, width: '100%' }}
                          />
                        </div>
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>이메일</label>
                          <input
                            type="email"
                            value={editEmail}
                            onChange={(e) => setEditEmail(e.target.value)}
                            style={{ ...inputStyle, width: '100%' }}
                          />
                        </div>
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>브랜드 유형</label>
                          <select
                            value={editBrandType}
                            onChange={(e) => setEditBrandType(e.target.value)}
                            style={{ ...inputStyle, width: '100%', appearance: 'auto' as const }}
                          >
                            <option value="fashion">패션</option>
                            <option value="beauty">뷰티</option>
                            <option value="etc">기타</option>
                          </select>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.5rem', fontSize: '0.85rem' }}>
                        <div><span style={{ color: '#6b7280' }}>업체명:</span> <strong>{detail.company_name || '-'}</strong></div>
                        <div><span style={{ color: '#6b7280' }}>연락처:</span> <strong>{detail.contact || '-'}</strong></div>
                        <div><span style={{ color: '#6b7280' }}>이메일:</span> <strong>{detail.email || '-'}</strong></div>
                        <div>
                          <span style={{ color: '#6b7280' }}>유형:</span>{' '}
                          <span style={{
                            display: 'inline-block', padding: '2px 10px', borderRadius: 12,
                            fontSize: '0.75rem', fontWeight: 600,
                            background: detail.brand_type === 'fashion' ? '#dbeafe' : detail.brand_type === 'beauty' ? '#fce7f3' : '#f3f4f6',
                            color: detail.brand_type === 'fashion' ? '#1d4ed8' : detail.brand_type === 'beauty' ? '#be185d' : '#374151',
                          }}>
                            {BRAND_LABEL[detail.brand_type] || detail.brand_type}
                          </span>
                        </div>
                        <div><span style={{ color: '#6b7280' }}>생성일:</span> <strong>{detail.created_at}</strong></div>
                      </div>
                    )}
                  </div>

                  {/* 견적 항목 */}
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>
                        견적 항목
                      </h3>
                      {isEditing && (
                        <button
                          onClick={addEditItem}
                          style={{
                            padding: '4px 12px', fontSize: '0.75rem', fontWeight: 600,
                            background: '#10b981', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
                          }}
                        >
                          + 항목 추가
                        </button>
                      )}
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                        <thead>
                          <tr style={{ background: '#f1f5f9' }}>
                            <th style={{ padding: '0.5rem', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 120 }}>항목</th>
                            <th style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 80 }}>수량</th>
                            <th style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 80 }}>단가</th>
                            <th style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 100 }}>금액</th>
                            <th style={{ padding: '0.5rem', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e2e8f0', minWidth: 100 }}>비고</th>
                            {isEditing && <th style={{ padding: '0.5rem', textAlign: 'center', fontWeight: 600, borderBottom: '1px solid #e2e8f0', width: 50 }}></th>}
                          </tr>
                        </thead>
                        <tbody>
                          {isEditing ? (
                            editItems.map((item, idx) => (
                              <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                <td style={{ padding: '0.4rem' }}>
                                  <input
                                    type="text"
                                    value={item.항목}
                                    onChange={(e) => updateEditItem(idx, '항목', e.target.value)}
                                    style={{ ...smallInputStyle, width: '100%' }}
                                    placeholder="항목명"
                                  />
                                </td>
                                <td style={{ padding: '0.4rem' }}>
                                  <input
                                    type="number"
                                    value={item.수량}
                                    onChange={(e) => updateEditItem(idx, '수량', e.target.value)}
                                    style={{ ...smallInputStyle, width: '100%', textAlign: 'right' }}
                                  />
                                </td>
                                <td style={{ padding: '0.4rem' }}>
                                  <input
                                    type="number"
                                    value={item.단가}
                                    onChange={(e) => updateEditItem(idx, '단가', e.target.value)}
                                    style={{ ...smallInputStyle, width: '100%', textAlign: 'right' }}
                                  />
                                </td>
                                <td style={{ padding: '0.4rem', textAlign: 'right', fontWeight: 600, color: '#1d4ed8' }}>
                                  ₩{fmt(item.금액)}
                                </td>
                                <td style={{ padding: '0.4rem' }}>
                                  <input
                                    type="text"
                                    value={item.비고 || ''}
                                    onChange={(e) => updateEditItem(idx, '비고', e.target.value)}
                                    style={{ ...smallInputStyle, width: '100%' }}
                                    placeholder="비고"
                                  />
                                </td>
                                <td style={{ padding: '0.4rem', textAlign: 'center' }}>
                                  <button
                                    onClick={() => removeEditItem(idx)}
                                    style={{
                                      padding: '2px 8px', fontSize: '0.7rem', fontWeight: 600,
                                      background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 4, cursor: 'pointer',
                                    }}
                                  >
                                    삭제
                                  </button>
                                </td>
                              </tr>
                            ))
                          ) : (
                            detail.items.map((item, idx) => (
                              <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                <td style={{ padding: '0.5rem' }}>{item.항목}</td>
                                <td style={{ padding: '0.5rem', textAlign: 'right' }}>{fmt(item.수량)}</td>
                                <td style={{ padding: '0.5rem', textAlign: 'right' }}>₩{fmt(item.단가)}</td>
                                <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>₩{fmt(item.금액)}</td>
                                <td style={{ padding: '0.5rem', color: '#6b7280', fontSize: '0.78rem' }}>{item.비고 || ''}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                        <tfoot>
                          <tr style={{ background: '#f8fafc' }}>
                            <td colSpan={3} style={{ padding: '0.6rem', textAlign: 'right', fontWeight: 700 }}>합계</td>
                            <td style={{ padding: '0.6rem', textAlign: 'right', fontWeight: 700, color: '#1d4ed8' }}>
                              ₩{fmt(isEditing ? getEditTotalAmount() : detail.total_amount)}
                            </td>
                            <td colSpan={isEditing ? 2 : 1}></td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ textAlign: 'center', color: '#9ca3af', padding: '2rem' }}>
                  데이터를 불러올 수 없습니다.
                </div>
              )}
            </div>

            {/* 푸터 버튼 */}
            {detail && (
              <div style={{
                padding: '1rem 1.25rem', borderTop: '1px solid #e2e8f0',
                display: 'flex', gap: 8, justifyContent: 'space-between', flexWrap: 'wrap',
              }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  {!isEditing && (
                    <button
                      onClick={handleDownloadPdf}
                      disabled={pdfLoading}
                      style={{
                        padding: '0.6rem 1.25rem', border: '2px solid #3b82f6', borderRadius: 8,
                        background: '#fff', color: '#3b82f6', fontSize: '0.85rem', fontWeight: 600,
                        cursor: pdfLoading ? 'not-allowed' : 'pointer', opacity: pdfLoading ? 0.6 : 1,
                      }}
                    >
                      {pdfLoading ? 'PDF 생성 중...' : 'PDF 다운로드'}
                    </button>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {isEditing ? (
                    <>
                      <button
                        onClick={cancelEditing}
                        style={{
                          padding: '0.6rem 1.25rem', border: '1px solid #d1d5db', borderRadius: 8,
                          background: '#fff', color: '#374151', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                        }}
                      >
                        취소
                      </button>
                      <button
                        onClick={handleSaveEdit}
                        style={{
                          padding: '0.6rem 1.25rem', border: 'none', borderRadius: 8,
                          background: '#10b981', color: '#fff', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                        }}
                      >
                        저장
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => setDeleteConfirmId(detail.id)}
                        style={{
                          padding: '0.6rem 1.25rem', border: 'none', borderRadius: 8,
                          background: '#ef4444', color: '#fff', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                        }}
                      >
                        삭제
                      </button>
                      <button
                        onClick={startEditing}
                        style={{
                          padding: '0.6rem 1.25rem', border: 'none', borderRadius: 8,
                          background: '#f59e0b', color: '#fff', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                        }}
                      >
                        수정
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
