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

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  /* ─── 스타일 ─── */
  const inputStyle: React.CSSProperties = {
    padding: '0.5rem 0.65rem', border: '1px solid #d1d5db', borderRadius: 8,
    fontSize: '0.85rem', outline: 'none', background: '#fff',
  };
  const btnStyle: React.CSSProperties = {
    padding: '0.5rem 1rem', border: 'none', borderRadius: 8,
    fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer', transition: 'all .15s',
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '1rem' }}>
      <h1 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '1rem', color: '#1f2937' }}>
        견적서 목록
      </h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

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
    </div>
  );
}
