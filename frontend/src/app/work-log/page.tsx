'use client';
import PageHeader from '@/components/ui/page-header';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { DateRangeControl, FilterBar, KpiStrip, TableSummary } from '@/components/data';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
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
import { downloadWorkLogExcel } from '@/lib/workLogExcel';

export default function WorkLogPage() {
  const [logs, setLogs] = useState<WorkLog[]>([]);
  const [filters, setFilters] = useState<WorkLogFilters | null>(null);
  const [stats, setStats] = useState<WorkLogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 당월 기본값 설정
  const getDefaultDates = () => {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    return {
      from: firstDay.toISOString().split('T')[0],
      to: now.toISOString().split('T')[0],
    };
  };

  // 필터 상태 (당월 기본값)
  const defaultDates = getDefaultDates();
  const [periodFrom, setPeriodFrom] = useState(defaultDates.from);
  const [periodTo, setPeriodTo] = useState(defaultDates.to);
  const [vendor, setVendor] = useState('');
  const [workType, setWorkType] = useState('');
  const [author, setAuthor] = useState('');
  const [source, setSource] = useState('');

  // 페이징 상태
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

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

  // 편집 저장 중
  const [editSaving, setEditSaving] = useState(false);

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
  const [excelExporting, setExcelExporting] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async (page = currentPage) => {
    try {
      setLoading(true);
      setError(null);

      const limit = pageSize === 0 ? 10000 : pageSize; // 0 = 전체
      const offset = pageSize === 0 ? 0 : (page - 1) * pageSize;

      const [logsRes, statsRes] = await Promise.all([
        getWorkLogs({
          period_from: periodFrom || undefined,
          period_to: periodTo || undefined,
          vendor: vendor || undefined,
          work_type: workType || undefined,
          author: author || undefined,
          source: source || undefined,
          limit,
          offset,
        }),
        getWorkLogStats({
          period_from: periodFrom || undefined,
          period_to: periodTo || undefined,
        }),
      ]);

      setLogs(logsRes.logs);
      setFilters(logsRes.filters);
      setStats(statsRes);
      setTotalCount(logsRes.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '데이터를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    setCurrentPage(1);
    loadData(1);
  };

  const handleReset = () => {
    const defaults = getDefaultDates();
    setPeriodFrom(defaults.from);
    setPeriodTo(defaults.to);
    setVendor('');
    setWorkType('');
    setAuthor('');
    setSource('');
    setCurrentPage(1);
    setTimeout(() => loadData(1), 100);
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    loadData(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
    setTimeout(() => loadData(1), 100);
  };

  const totalPages = pageSize === 0 ? 1 : Math.ceil(totalCount / pageSize);

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

    setEditSaving(true);
    setMessage(null);
    try {
      await updateWorkLog(editingLog.id, {
        날짜: editForm.날짜 || undefined,
        업체명: editForm.업체명 || undefined,
        분류: editForm.분류 || undefined,
        단가: editForm.단가,
        수량: editForm.수량,
        비고1: editForm.비고1,
      });
      setMessage({ type: 'success', text: '작업일지가 수정되었습니다.' });
      setEditingLog(null);
      await loadData();
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : '수정에 실패했습니다.',
      });
    } finally {
      setEditSaving(false);
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
    const variant = source === 'bot' ? 'success' : source === 'excel' ? 'info' : source === 'manual' ? 'neutral' : 'neutral';
    const labels: Record<string, string> = { bot: '봇', excel: '엑셀', manual: '수동' };
    return <Badge variant={variant}>{labels[source || ''] || source || '-'}</Badge>;
  };

  return (
    <div>
      <PageHeader title="작업일지" />

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
        <KpiStrip
          items={[
            { label: '전체 건수', value: stats.total.toLocaleString() },
            { label: '전체 금액', value: <span className="tw-text-tillion-success">{stats.total_amount.toLocaleString()}원</span> },
            { label: '오늘 건수', value: stats.today.toLocaleString() },
            ...stats.by_source.slice(0, 2).map((item) => ({
              label: `출처: ${item.출처 || '미지정'}`,
              value: `${item.count.toLocaleString()}건`,
            })),
          ]}
        />
      )}

      <FilterBar>
        <DateRangeControl from={periodFrom} to={periodTo} onFrom={setPeriodFrom} onTo={setPeriodTo} />
        <Field label="업체명">
          <Select value={vendor} onChange={(e) => setVendor(e.target.value)}>
            <option value="">전체</option>
            {filters?.vendors.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </Select>
        </Field>
        <Field label="작업 종류">
          <Select value={workType} onChange={(e) => setWorkType(e.target.value)}>
            <option value="">전체</option>
            {filters?.work_types.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
        </Field>
        <Field label="작성자">
          <Select value={author} onChange={(e) => setAuthor(e.target.value)}>
            <option value="">전체</option>
            {filters?.authors.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </Select>
        </Field>
        <Field label="출처">
          <Select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">전체</option>
            <option value="bot">봇</option>
            <option value="excel">엑셀</option>
            <option value="manual">수동</option>
          </Select>
        </Field>
      </FilterBar>
      <div className="tw-mb-3 tw-flex tw-flex-wrap tw-items-center tw-gap-2">
          <Button type="button" onClick={handleSearch}>검색</Button>
          <Button type="button" variant="ghost" onClick={handleReset}>초기화</Button>
          <Button
            type="button"
            variant="secondary"
            onClick={async () => {
              if (!periodFrom || !periodTo) {
                setMessage({ type: 'error', text: '엑셀 보고를 위해 시작일과 종료일을 선택하세요.' });
                return;
              }
              setExcelExporting(true);
              setMessage(null);
              try {
                await downloadWorkLogExcel({
                  period_from: periodFrom,
                  period_to: periodTo,
                  vendor: vendor || undefined,
                  work_type: workType || undefined,
                  author: author || undefined,
                  source: source || undefined,
                });
                setMessage({ type: 'success', text: '엑셀 보고서를 저장했습니다.' });
              } catch (err) {
                setMessage({
                  type: 'error',
                  text: err instanceof Error ? err.message : '엑셀 생성 실패',
                });
              } finally {
                setExcelExporting(false);
              }
            }}
            disabled={excelExporting}
          >
            {excelExporting ? '엑셀 만드는 중...' : '엑셀 다운로드'}
          </Button>
          <Field label="페이지당" className="tw-mb-0 tw-ml-auto">
            <Select value={pageSize} onChange={(e) => handlePageSizeChange(Number(e.target.value))}>
              <option value={50}>50개</option>
              <option value={100}>100개</option>
              <option value={200}>200개</option>
              <option value={0}>전체</option>
            </Select>
          </Field>
        </div>
        <p className="caption tw-mb-3">
          엑셀은 현재 선택한 기간·업체·작업 종류·작성자·출처 필터의 작업일지를 담습니다. 화면에 보이는 페이지와 관계없이 조건에 맞는 모든 건이 들어갑니다.
        </p>

      {/* 작업일지 목록 */}
      <div className="tw-mb-2 tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2">
        <TableSummary>
          작업일지 {pageSize === 0 ? totalCount : `${logs.length}/${totalCount}`}건
          {totalPages > 1 ? ` · ${currentPage}/${totalPages}페이지` : ''}
        </TableSummary>
        <Button type="button" variant="success" onClick={() => setShowAddModal(true)}>수동 추가</Button>
      </div>
      <Card title="" style={{ marginTop: '0' }}>
        {loading ? (
          <Loading />
        ) : logs.length === 0 ? (
          <p className="caption">작업일지가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>날짜</th>
                  <th>업체명</th>
                  <th>작업</th>
                  <th className="cell-num">수량</th>
                  <th className="cell-num">단가</th>
                  <th className="cell-num">합계</th>
                  <th>작성자</th>
                  <th>출처</th>
                  <th>저장시간</th>
                  <th>수정자</th>
                  <th>수정시간</th>
                  <th className="tw-text-center">작업</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{log.날짜 || '-'}</td>
                    <td>{log.업체명 || '-'}</td>
                    <td>{log.분류 || '-'}</td>
                    <td className="cell-num">{log.수량?.toLocaleString() || '-'}</td>
                    <td className="cell-num">{formatPrice(log.단가)}</td>
                    <td className="cell-num">
                      {formatPrice(log.합계)}
                    </td>
                    <td>{log.작성자 || '-'}</td>
                    <td>{getSourceBadge(log.출처)}</td>
                    <td>
                      {formatDateTime(log.저장시간)}
                    </td>
                    <td>{log.수정자 || '-'}</td>
                    <td>
                      {formatDateTime(log.수정시간)}
                    </td>
                    <td className="tw-text-center">
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
        
        {/* 페이지네이션 */}
        {totalPages > 1 && pageSize !== 0 && (
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center', 
            gap: '0.5rem', 
            marginTop: '1rem',
            paddingTop: '1rem',
            borderTop: '1px solid #eee'
          }}>
            <button
              onClick={() => handlePageChange(1)}
              disabled={currentPage === 1}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: currentPage === 1 ? '#e5e7eb' : '#f3f4f6',
                color: currentPage === 1 ? '#9ca3af' : '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
              }}
            >
              ⟪
            </button>
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: currentPage === 1 ? '#e5e7eb' : '#f3f4f6',
                color: currentPage === 1 ? '#9ca3af' : '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
              }}
            >
              ◀
            </button>
            
            {/* 페이지 번호들 */}
            {(() => {
              const pages = [];
              const maxVisible = 5;
              let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
              let end = Math.min(totalPages, start + maxVisible - 1);
              
              if (end - start + 1 < maxVisible) {
                start = Math.max(1, end - maxVisible + 1);
              }
              
              for (let i = start; i <= end; i++) {
                pages.push(
                  <button
                    key={i}
                    onClick={() => handlePageChange(i)}
                    style={{
                      padding: '0.5rem 0.75rem',
                      backgroundColor: currentPage === i ? '#2563eb' : '#f3f4f6',
                      color: currentPage === i ? 'white' : '#374151',
                      border: '1px solid #d1d5db',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontWeight: currentPage === i ? '600' : '400',
                    }}
                  >
                    {i}
                  </button>
                );
              }
              return pages;
            })()}
            
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: currentPage === totalPages ? '#e5e7eb' : '#f3f4f6',
                color: currentPage === totalPages ? '#9ca3af' : '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
              }}
            >
              ▶
            </button>
            <button
              onClick={() => handlePageChange(totalPages)}
              disabled={currentPage === totalPages}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: currentPage === totalPages ? '#e5e7eb' : '#f3f4f6',
                color: currentPage === totalPages ? '#9ca3af' : '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
              }}
            >
              ⟫
            </button>
          </div>
        )}
      </Card>

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
                <select
                  value={addForm.업체명}
                  onChange={(e) => setAddForm({ ...addForm, 업체명: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                >
                  <option value="">업체를 선택하세요</option>
                  {filters?.vendors.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                  작업 종류 <span style={{ color: 'red' }}>*</span>
                  <span style={{ fontSize: '0.75rem', color: '#666', marginLeft: '0.5rem' }}>
                    (선택 또는 직접 입력)
                  </span>
                </label>
                <input
                  type="text"
                  list="work-type-list"
                  value={addForm.분류}
                  onChange={(e) => setAddForm({ ...addForm, 분류: e.target.value })}
                  placeholder="선택하거나 직접 입력하세요"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
                <datalist id="work-type-list">
                  {filters?.work_types.map((t) => (
                    <option key={t} value={t} />
                  ))}
                </datalist>
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
                disabled={editSaving}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#6b7280',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: editSaving ? 'not-allowed' : 'pointer',
                  opacity: editSaving ? 0.7 : 1,
                }}
              >
                취소
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={editSaving}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#2563eb',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: editSaving ? 'not-allowed' : 'pointer',
                  opacity: editSaving ? 0.7 : 1,
                }}
              >
                {editSaving ? '저장 중...' : '저장'}
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
