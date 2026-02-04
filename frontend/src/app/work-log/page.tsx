'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { 
  getWorkLogs, 
  getWorkLogStats, 
  createWorkLog,
  updateWorkLog, 
  deleteWorkLog,
  WorkLog, 
  WorkLogFilters, 
  WorkLogStats 
} from '@/lib/api';

export default function WorkLogPage() {
  const [logs, setLogs] = useState<WorkLog[]>([]);
  const [filters, setFilters] = useState<WorkLogFilters | null>(null);
  const [stats, setStats] = useState<WorkLogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 필터 상태
  const [periodFrom, setPeriodFrom] = useState('');
  const [periodTo, setPeriodTo] = useState('');
  const [vendor, setVendor] = useState('');
  const [workType, setWorkType] = useState('');
  const [author, setAuthor] = useState('');
  const [source, setSource] = useState('');

  // 편집 모달 상태
  const [editingLog, setEditingLog] = useState<WorkLog | null>(null);
  const [editForm, setEditForm] = useState({
    날짜: '',
    업체명: '',
    분류: '',
    단가: 0,
    수량: 1,
    비고1: '',
  });

  // 삭제 확인 모달
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // 새 작업일지 추가 모달
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    날짜: new Date().toISOString().split('T')[0],
    업체명: '',
    분류: '',
    단가: 0,
    수량: 1,
    비고1: '',
  });
  const [addLoading, setAddLoading] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [logsRes, statsRes] = await Promise.all([
        getWorkLogs({
          period_from: periodFrom || undefined,
          period_to: periodTo || undefined,
          vendor: vendor || undefined,
          work_type: workType || undefined,
          author: author || undefined,
          source: source || undefined,
          limit: 500,
        }),
        getWorkLogStats({
          period_from: periodFrom || undefined,
          period_to: periodTo || undefined,
        }),
      ]);

      setLogs(logsRes.logs);
      setFilters(logsRes.filters);
      setStats(statsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : '데이터를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    loadData();
  };

  const handleReset = () => {
    setPeriodFrom('');
    setPeriodTo('');
    setVendor('');
    setWorkType('');
    setAuthor('');
    setSource('');
    setTimeout(() => loadData(), 100);
  };

  const handleEdit = (log: WorkLog) => {
    setEditingLog(log);
    setEditForm({
      날짜: log.날짜 || '',
      업체명: log.업체명 || '',
      분류: log.분류 || '',
      단가: log.단가 || 0,
      수량: log.수량 || 1,
      비고1: log.비고1 || '',
    });
  };

  const handleSaveEdit = async () => {
    if (!editingLog) return;

    try {
      await updateWorkLog(editingLog.id, editForm);
      setMessage({ type: 'success', text: '작업일지가 수정되었습니다.' });
      setEditingLog(null);
      loadData();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '수정에 실패했습니다.' });
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteWorkLog(id);
      setMessage({ type: 'success', text: '작업일지가 삭제되었습니다.' });
      setDeletingId(null);
      loadData();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '삭제에 실패했습니다.' });
    }
  };

  const handleAdd = async () => {
    if (!addForm.업체명 || !addForm.분류 || addForm.단가 <= 0) {
      setMessage({ type: 'error', text: '업체명, 작업 종류, 단가는 필수입니다.' });
      return;
    }

    setAddLoading(true);
    try {
      await createWorkLog({
        날짜: addForm.날짜,
        업체명: addForm.업체명,
        분류: addForm.분류,
        단가: addForm.단가,
        수량: addForm.수량,
        비고1: addForm.비고1 || undefined,
        출처: 'manual',
      });
      setMessage({ type: 'success', text: '작업일지가 추가되었습니다.' });
      setShowAddModal(false);
      setAddForm({
        날짜: new Date().toISOString().split('T')[0],
        업체명: '',
        분류: '',
        단가: 0,
        수량: 1,
        비고1: '',
      });
      loadData();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '추가에 실패했습니다.' });
    } finally {
      setAddLoading(false);
    }
  };

  const formatPrice = (price: number | null) => {
    if (price === null) return '-';
    return `${price.toLocaleString()}원`;
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return '-';
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const getSourceBadge = (source: string | null) => {
    const colors: Record<string, string> = {
      bot: '#22c55e',
      excel: '#3b82f6',
      manual: '#8b5cf6',
    };
    const labels: Record<string, string> = {
      bot: '🤖 봇',
      excel: '📊 엑셀',
      manual: '✏️ 수동',
    };
    const color = colors[source || ''] || '#6b7280';
    const label = labels[source || ''] || source || '-';
    
    return (
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        padding: '0.125rem 0.5rem',
        borderRadius: '4px',
        fontSize: '0.75rem',
        backgroundColor: color,
        color: 'white',
        fontWeight: source === 'bot' ? '600' : '400',
      }}>
        {label}
      </span>
    );
  };

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '1rem' }}>
        📋 작업일지
      </h1>

      {message && (
        <Alert 
          type={message.type} 
          message={message.text} 
          onClose={() => setMessage(null)} 
        />
      )}

      {error && (
        <Alert type="error" message={error} onClose={() => setError(null)} />
      )}

      {/* 통계 카드 */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <Card title="전체 건수">
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total.toLocaleString()}</p>
          </Card>
          <Card title="전체 금액">
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#16a34a' }}>
              {stats.total_amount.toLocaleString()}원
            </p>
          </Card>
          <Card title="오늘 건수">
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb' }}>{stats.today.toLocaleString()}</p>
          </Card>
          {stats.by_source.slice(0, 2).map((item, idx) => (
            <Card key={idx} title={`출처: ${item.출처 || '미지정'}`}>
              <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{item.count.toLocaleString()}건</p>
            </Card>
          ))}
        </div>
      )}

      {/* 필터 */}
      <Card title="검색 필터">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>시작일</label>
            <input
              type="date"
              value={periodFrom}
              onChange={(e) => setPeriodFrom(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>종료일</label>
            <input
              type="date"
              value={periodTo}
              onChange={(e) => setPeriodTo(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>업체명</label>
            <select
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              {filters?.vendors.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>작업 종류</label>
            <select
              value={workType}
              onChange={(e) => setWorkType(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              {filters?.work_types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>작성자</label>
            <select
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              {filters?.authors.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>출처</label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              <option value="bot">봇</option>
              <option value="excel">엑셀</option>
              <option value="manual">수동</option>
            </select>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handleSearch}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            검색
          </button>
          <button
            onClick={handleReset}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#6b7280',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            초기화
          </button>
        </div>
      </Card>

      {/* 작업일지 목록 */}
      <div style={{ marginTop: '1rem' }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: '0.5rem'
        }}>
          <h3 style={{ fontSize: '1rem', fontWeight: '600' }}>
            작업일지 목록 ({logs.length}건)
          </h3>
          <button
            onClick={() => setShowAddModal(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 1rem',
              backgroundColor: '#22c55e',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: '500',
            }}
          >
            ➕ 수동 추가
          </button>
        </div>
      <Card title="" style={{ marginTop: '0' }}>
        {loading ? (
          <Loading />
        ) : logs.length === 0 ? (
          <p style={{ color: '#666' }}>작업일지가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>날짜</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>업체명</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>작업</th>
                  <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #ddd' }}>수량</th>
                  <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #ddd' }}>단가</th>
                  <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #ddd' }}>합계</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>작성자</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>출처</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>저장시간</th>
                  <th style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #ddd' }}>작업</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '0.5rem' }}>{log.날짜 || '-'}</td>
                    <td style={{ padding: '0.5rem', fontWeight: '500' }}>{log.업체명 || '-'}</td>
                    <td style={{ padding: '0.5rem' }}>{log.분류 || '-'}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>{log.수량?.toLocaleString() || '-'}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>{formatPrice(log.단가)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: '600', color: '#16a34a' }}>
                      {formatPrice(log.합계)}
                    </td>
                    <td style={{ padding: '0.5rem' }}>{log.작성자 || '-'}</td>
                    <td style={{ padding: '0.5rem' }}>{getSourceBadge(log.출처)}</td>
                    <td style={{ padding: '0.5rem', fontSize: '0.75rem', color: '#666' }}>
                      {formatDateTime(log.저장시간)}
                    </td>
                    <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                      <button
                        onClick={() => handleEdit(log)}
                        style={{
                          padding: '0.25rem 0.5rem',
                          marginRight: '0.25rem',
                          backgroundColor: '#3b82f6',
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
                        onClick={() => setDeletingId(log.id)}
                        style={{
                          padding: '0.25rem 0.5rem',
                          backgroundColor: '#ef4444',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                        }}
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      </div>

      {/* 새 작업일지 추가 모달 */}
      {showAddModal && (
        <div style={{
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
        }}>
          <div style={{
            backgroundColor: 'white',
            padding: '1.5rem',
            borderRadius: '8px',
            maxWidth: '500px',
            width: '90%',
          }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '1rem' }}>
              ➕ 작업일지 수동 추가
            </h2>
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  날짜 <span style={{ color: 'red' }}>*</span>
                </label>
                <input
                  type="date"
                  value={addForm.날짜}
                  onChange={(e) => setAddForm({ ...addForm, 날짜: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  업체명 <span style={{ color: 'red' }}>*</span>
                </label>
                <input
                  type="text"
                  value={addForm.업체명}
                  onChange={(e) => setAddForm({ ...addForm, 업체명: e.target.value })}
                  placeholder="업체명을 입력하세요"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  작업 종류 <span style={{ color: 'red' }}>*</span>
                </label>
                <input
                  type="text"
                  value={addForm.분류}
                  onChange={(e) => setAddForm({ ...addForm, 분류: e.target.value })}
                  placeholder="예: 1톤하차, 양품화, 바코드부착"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>수량</label>
                  <input
                    type="number"
                    value={addForm.수량}
                    onChange={(e) => setAddForm({ ...addForm, 수량: parseInt(e.target.value) || 1 })}
                    min={1}
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                    단가 <span style={{ color: 'red' }}>*</span>
                  </label>
                  <input
                    type="number"
                    value={addForm.단가}
                    onChange={(e) => setAddForm({ ...addForm, 단가: parseInt(e.target.value) || 0 })}
                    placeholder="원"
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                  />
                </div>
              </div>
              <div style={{ 
                padding: '0.5rem', 
                backgroundColor: '#f0fdf4', 
                borderRadius: '4px',
                textAlign: 'center'
              }}>
                <span style={{ fontSize: '0.875rem', color: '#666' }}>합계: </span>
                <span style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#16a34a' }}>
                  {(addForm.수량 * addForm.단가).toLocaleString()}원
                </span>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>비고</label>
                <input
                  type="text"
                  value={addForm.비고1}
                  onChange={(e) => setAddForm({ ...addForm, 비고1: e.target.value })}
                  placeholder="추가 메모 (선택)"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button
                onClick={() => setShowAddModal(false)}
                disabled={addLoading}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#6b7280',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: addLoading ? 'not-allowed' : 'pointer',
                  opacity: addLoading ? 0.6 : 1,
                }}
              >
                취소
              </button>
              <button
                onClick={handleAdd}
                disabled={addLoading}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#22c55e',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: addLoading ? 'not-allowed' : 'pointer',
                  opacity: addLoading ? 0.6 : 1,
                }}
              >
                {addLoading ? '저장 중...' : '저장'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 편집 모달 */}
      {editingLog && (
        <div style={{
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
        }}>
          <div style={{
            backgroundColor: 'white',
            padding: '1.5rem',
            borderRadius: '8px',
            maxWidth: '500px',
            width: '90%',
          }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '1rem' }}>
              작업일지 수정
            </h2>
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>날짜</label>
                <input
                  type="date"
                  value={editForm.날짜}
                  onChange={(e) => setEditForm({ ...editForm, 날짜: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>업체명</label>
                <input
                  type="text"
                  value={editForm.업체명}
                  onChange={(e) => setEditForm({ ...editForm, 업체명: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>작업 종류</label>
                <input
                  type="text"
                  value={editForm.분류}
                  onChange={(e) => setEditForm({ ...editForm, 분류: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>수량</label>
                  <input
                    type="number"
                    value={editForm.수량}
                    onChange={(e) => setEditForm({ ...editForm, 수량: parseInt(e.target.value) || 1 })}
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>단가</label>
                  <input
                    type="number"
                    value={editForm.단가}
                    onChange={(e) => setEditForm({ ...editForm, 단가: parseInt(e.target.value) || 0 })}
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                  />
                </div>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  합계: {(editForm.수량 * editForm.단가).toLocaleString()}원
                </label>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>비고</label>
                <input
                  type="text"
                  value={editForm.비고1}
                  onChange={(e) => setEditForm({ ...editForm, 비고1: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button
                onClick={() => setEditingLog(null)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#6b7280',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                취소
              </button>
              <button
                onClick={handleSaveEdit}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#2563eb',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                저장
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 삭제 확인 모달 */}
      {deletingId && (
        <div style={{
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
        }}>
          <div style={{
            backgroundColor: 'white',
            padding: '1.5rem',
            borderRadius: '8px',
            maxWidth: '400px',
            width: '90%',
          }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '1rem' }}>
              삭제 확인
            </h2>
            <p style={{ marginBottom: '1rem' }}>
              이 작업일지를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                onClick={() => setDeletingId(null)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#6b7280',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                취소
              </button>
              <button
                onClick={() => handleDelete(deletingId)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                삭제
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
