'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import {
  getDefectLogs,
  getDefectLogStats,
  createDefectLog,
  updateDefectLog,
  deleteDefectLog,
  uploadDefectPhotos,
  updateDefectResult,
  defectImageUrl,
  lookupRepairBarcode,
  autoFillDefectFromBarcode,
  DefectLog,
  DefectLogFilters,
  DefectLogStats,
} from '@/lib/api';

const RESULT_OPTIONS = ['업체반송', '반품', '기타'] as const;

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.5rem',
  border: '1px solid #ddd',
  borderRadius: '4px',
};

const btn = (bg: string): React.CSSProperties => ({
  padding: '0.5rem 1rem',
  backgroundColor: bg,
  color: 'white',
  border: 'none',
  borderRadius: '4px',
  cursor: 'pointer',
  fontWeight: 500,
});

function todayStr() {
  return new Date().toISOString().split('T')[0];
}

function monthRange() {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  return { from: from.toISOString().split('T')[0], to: todayStr() };
}

function formatDateTime(dateStr: string | null) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function resultBadge(result: string | null) {
  if (!result) return <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>미처리</span>;
  const colors: Record<string, string> = {
    '업체반송': '#dc2626',
    '반품': '#d97706',
    '기타': '#6b7280',
  };
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
      backgroundColor: (colors[result] || '#6b7280') + '18',
      color: colors[result] || '#6b7280',
      border: `1px solid ${colors[result] || '#6b7280'}40`,
    }}>
      {result}
    </span>
  );
}

function PhotoThumb({ filename, label, onClick }: { filename: string | null; label: string; onClick: (url: string) => void }) {
  const url = defectImageUrl(filename);
  if (!url) return <span style={{ color: '#bbb', fontSize: '0.75rem' }}>{label} 없음</span>;
  return (
    <button
      type="button"
      onClick={() => onClick(url)}
      title={label}
      style={{ border: '1px solid #ddd', borderRadius: 4, padding: 0, cursor: 'pointer', background: '#fff' }}
    >
      <img src={url} alt={label} style={{ width: 48, height: 48, objectFit: 'cover', display: 'block', borderRadius: 4 }} />
    </button>
  );
}

export default function DefectLogPage() {
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{
        fontSize: '1.375rem', fontWeight: 700, marginBottom: '1rem',
        color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)',
      }}>
        불량일지
      </h1>
      {message && <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />}
      <LogsTab onMessage={setMessage} />
    </div>
  );
}

function LogsTab({ onMessage }: { onMessage: (m: { type: 'success' | 'error'; text: string } | null) => void }) {
  const defaults = monthRange();
  const [logs, setLogs] = useState<DefectLog[]>([]);
  const [filters, setFilters] = useState<DefectLogFilters | null>(null);
  const [stats, setStats] = useState<DefectLogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [periodFrom, setPeriodFrom] = useState(defaults.from);
  const [periodTo, setPeriodTo] = useState(defaults.to);
  const [vendor, setVendor] = useState('');
  const [defect, setDefect] = useState('');
  const [author, setAuthor] = useState('');
  const [resultFilter, setResultFilter] = useState('');
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [preview, setPreview] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<DefectLog | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [updatingResult, setUpdatingResult] = useState<number | null>(null);
  const [fillBusy, setFillBusy] = useState(false);
  const [fillResult, setFillResult] = useState<{ updated: number; skipped: number } | null>(null);

  const totalPages = pageSize === 0 ? 1 : Math.max(1, Math.ceil(totalCount / pageSize));

  async function load() {
    setLoading(true);
    try {
      const limit = pageSize === 0 ? 2000 : pageSize;
      const offset = pageSize === 0 ? 0 : (currentPage - 1) * pageSize;
      const [list, st] = await Promise.all([
        getDefectLogs({
          period_from: periodFrom, period_to: periodTo,
          vendor: vendor || undefined, defect: defect || undefined,
          author: author || undefined, result: resultFilter || undefined,
          unresolved_only: unresolvedOnly || undefined,
          limit, offset,
        }),
        getDefectLogStats({ period_from: periodFrom, period_to: periodTo }),
      ]);
      setLogs(list.logs);
      setTotalCount(list.total);
      setFilters(list.filters);
      setStats(st);
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '불러오기 실패' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [currentPage, pageSize]);

  async function handleResultChange(id: number, value: string) {
    setUpdatingResult(id);
    try {
      await updateDefectResult(id, value || null);
      setLogs((prev) => prev.map((l) => l.id === id ? { ...l, 처리결과: value || null } : l));
      if (stats) {
        // 간단히 전체 다시 로드
        const st = await getDefectLogStats({ period_from: periodFrom, period_to: periodTo });
        setStats(st);
      }
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '처리결과 업데이트 실패' });
    } finally {
      setUpdatingResult(null);
    }
  }

  async function handleAutoFill() {
    if (!confirm('바코드가 있지만 업체명·제품명이 비어있는 항목을 repair_barcode에서 자동으로 채웁니다.\n계속하시겠습니까?')) return;
    setFillBusy(true);
    setFillResult(null);
    try {
      const r = await autoFillDefectFromBarcode();
      setFillResult({ updated: r.updated, skipped: r.skipped });
      if (r.updated > 0) {
        onMessage({ type: 'success', text: `바코드 정보 ${r.updated}건 갱신 완료 (미매칭 ${r.skipped}건)` });
        load();
      } else {
        onMessage({ type: 'success', text: `갱신 대상 없음 (미매칭 ${r.skipped}건)` });
      }
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '일괄 갱신 실패' });
    } finally {
      setFillBusy(false);
    }
  }

  return (
    <>
      {/* 통계 카드 */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <Card title="조회 건수"><p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total.toLocaleString()}</p></Card>
          <Card title="오늘 건수"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb' }}>{stats.today.toLocaleString()}</p></Card>
          <Card title="미처리"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#dc2626' }}>{stats.unresolved.toLocaleString()}</p></Card>
          <Card title="처리결과">
            <div style={{ fontSize: '0.8rem', lineHeight: 1.8 }}>
              {stats.by_result.map((r) => (
                <div key={r.처리결과} style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{r.처리결과}</span>
                  <strong>{r.count}</strong>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* 검색 필터 */}
      <Card title="검색 필터">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>시작일</label>
            <input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>종료일</label>
            <input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>업체명</label>
            <select value={vendor} onChange={(e) => setVendor(e.target.value)} style={inputStyle}>
              <option value="">전체</option>
              {filters?.vendors.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>불량명</label>
            <select value={defect} onChange={(e) => setDefect(e.target.value)} style={inputStyle}>
              <option value="">전체</option>
              {filters?.defects.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>처리결과</label>
            <select value={resultFilter} onChange={(e) => setResultFilter(e.target.value)} style={inputStyle}>
              <option value="">전체</option>
              <option value="미처리">미처리</option>
              {RESULT_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>작성자</label>
            <select value={author} onChange={(e) => setAuthor(e.target.value)} style={inputStyle}>
              <option value="">전체</option>
              {filters?.authors.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button onClick={() => { setCurrentPage(1); load(); }} style={btn('#2563eb')}>검색</button>
          <button onClick={() => {
            const r = monthRange();
            setPeriodFrom(r.from); setPeriodTo(r.to);
            setVendor(''); setDefect(''); setAuthor(''); setResultFilter(''); setUnresolvedOnly(false);
            setCurrentPage(1);
          }} style={btn('#6b7280')}>초기화</button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem', cursor: 'pointer', userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={unresolvedOnly}
              onChange={(e) => { setUnresolvedOnly(e.target.checked); setCurrentPage(1); }}
            />
            미처리만 보기
          </label>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.875rem', color: '#666' }}>페이지당:</span>
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }} style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}>
              <option value={50}>50개</option>
              <option value={100}>100개</option>
              <option value={200}>200개</option>
              <option value={0}>전체</option>
            </select>
          </div>
        </div>
      </Card>

      {/* 목록 */}
      <div style={{ marginTop: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>
            불량일지 목록
            <span style={{ color: '#666', fontWeight: 400, marginLeft: 8 }}>
              ({pageSize === 0 ? totalCount : `${logs.length}/${totalCount}`}건)
            </span>
          </h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {fillResult && (
              <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                갱신 {fillResult.updated}건 / 미매칭 {fillResult.skipped}건
              </span>
            )}
            <button
              onClick={handleAutoFill}
              disabled={fillBusy}
              style={{ ...btn('#8b5cf6'), opacity: fillBusy ? 0.6 : 1, fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
              title="바코드가 있지만 업체명·제품명이 누락된 항목을 자동으로 채웁니다"
            >
              {fillBusy ? '갱신 중…' : '🔍 바코드로 정보 갱신'}
            </button>
            <button onClick={() => setShowAdd(true)} style={btn('#22c55e')}>➕ 수동 추가</button>
          </div>
        </div>

        <Card title="">
          {loading ? <Loading /> : logs.length === 0 ? (
            <p style={{ color: '#666' }}>불량일지가 없습니다.</p>
          ) : (
            <>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      {['날짜', '업체명', '제품명', '옵션', '바코드', '불량명', '수량', '비고', '작성자', '처리결과', '수정자', '수정시간', '사진', ''].map((h) => (
                        <th key={h} style={{ padding: '0.5rem', textAlign: h === '수량' ? 'right' : 'left', borderBottom: '1px solid #ddd', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr key={log.id} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>{log.날짜 || '-'}</td>
                        <td style={{ padding: '0.5rem', fontWeight: 500 }}>{log.업체명 || '-'}</td>
                        <td style={{ padding: '0.5rem' }}>{log.제품명 || '-'}</td>
                        <td style={{ padding: '0.5rem' }}>{log.옵션 || '-'}</td>
                        <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{log.바코드 || '-'}</td>
                        <td style={{ padding: '0.5rem', fontWeight: 500, color: '#dc2626' }}>{log.불량명 || '-'}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>{log.수량?.toLocaleString() ?? '-'}</td>
                        <td style={{ padding: '0.5rem', color: '#666' }}>{log.비고 || '-'}</td>
                        <td style={{ padding: '0.5rem' }}>{log.작성자 || '-'}</td>
                        {/* 처리결과 인라인 드롭다운 */}
                        <td style={{ padding: '0.5rem', minWidth: 100 }}>
                          {updatingResult === log.id ? (
                            <span style={{ color: '#9ca3af', fontSize: '0.75rem' }}>저장 중...</span>
                          ) : (
                            <select
                              value={log.처리결과 || ''}
                              onChange={(e) => handleResultChange(log.id, e.target.value)}
                              style={{
                                fontSize: '0.8rem', padding: '2px 4px',
                                border: '1px solid #e5e7eb', borderRadius: 4,
                                backgroundColor: log.처리결과 ? '#fff' : '#fef9c3',
                                cursor: 'pointer', width: '100%',
                              }}
                            >
                              <option value="">미처리</option>
                              {RESULT_OPTIONS.map((r) => (
                                <option key={r} value={r}>{r}</option>
                              ))}
                            </select>
                          )}
                        </td>
                        <td style={{ padding: '0.5rem', color: '#666' }}>{log.수정자 || '-'}</td>
                        <td style={{ padding: '0.5rem', fontSize: '0.75rem', color: '#666', whiteSpace: 'nowrap' }}>{formatDateTime(log.수정시간)}</td>
                        <td style={{ padding: '0.5rem' }}>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {[
                              ['사진1', log.before_image],
                              ['사진2', log.after_image],
                              ...(log.extra_images || []).map((fn, i) => [`추가${i + 1}`, fn] as const),
                            ].filter(([, fn]) => fn).map(([label, fn]) => (
                              <PhotoThumb key={`${label}-${fn}`} filename={fn as string} label={label as string} onClick={setPreview} />
                            ))}
                          </div>
                        </td>
                        <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                          <button onClick={() => setEditing(log)} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
                          <button onClick={() => setDeletingId(log.id)} style={{ ...btn('#ef4444'), padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>삭제</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && pageSize !== 0 && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
                  <button disabled={currentPage === 1} onClick={() => setCurrentPage((p) => p - 1)} style={btn(currentPage === 1 ? '#9ca3af' : '#6b7280')}>이전</button>
                  <span style={{ alignSelf: 'center', fontSize: '0.875rem' }}>{currentPage} / {totalPages}</span>
                  <button disabled={currentPage === totalPages} onClick={() => setCurrentPage((p) => p + 1)} style={btn(currentPage === totalPages ? '#9ca3af' : '#6b7280')}>다음</button>
                </div>
              )}
            </>
          )}
        </Card>
      </div>

      {showAdd && (
        <DefectFormModal
          title="불량일지 수동 추가"
          onClose={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); load(); }}
          onMessage={onMessage}
        />
      )}
      {editing && (
        <DefectFormModal
          title="불량일지 수정"
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
          onMessage={onMessage}
        />
      )}
      {deletingId != null && (
        <ConfirmModal
          text="이 불량일지를 삭제하시겠습니까? 사진도 함께 삭제됩니다."
          onCancel={() => setDeletingId(null)}
          onConfirm={async () => {
            try {
              await deleteDefectLog(deletingId);
              onMessage({ type: 'success', text: '불량일지가 삭제되었습니다.' });
              setDeletingId(null);
              load();
            } catch (e) {
              onMessage({ type: 'error', text: e instanceof Error ? e.message : '삭제 실패' });
            }
          }}
        />
      )}
      {preview && (
        <div onClick={() => setPreview(null)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, cursor: 'zoom-out',
        }}>
          <img src={preview} alt="미리보기" style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8 }} />
        </div>
      )}
    </>
  );
}

function DefectFormModal({
  title, initial, onClose, onSaved, onMessage,
}: {
  title: string;
  initial?: DefectLog;
  onClose: () => void;
  onSaved: () => void;
  onMessage: (m: { type: 'success' | 'error'; text: string } | null) => void;
}) {
  const [form, setForm] = useState({
    날짜: initial?.날짜 || todayStr(),
    바코드: initial?.바코드 || '',
    업체명: initial?.업체명 || '',
    제품명: initial?.제품명 || '',
    옵션: initial?.옵션 || '',
    불량명: initial?.불량명 || '',
    수량: initial?.수량 ?? 1,
    비고: initial?.비고 || '',
    처리결과: initial?.처리결과 || '',
  });
  const [saving, setSaving] = useState(false);
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupHint, setLookupHint] = useState('');
  const [lookupOk, setLookupOk] = useState(false);
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);
  const [extraFiles, setExtraFiles] = useState<File[]>([]);

  async function searchBarcode(raw?: string) {
    const code = (raw ?? form.바코드).trim();
    if (!code) {
      setLookupOk(false);
      setLookupHint('바코드를 입력한 뒤 검색하세요.');
      return;
    }
    setLookingUp(true);
    setLookupHint('검색 중...');
    setLookupOk(false);
    try {
      const found = await lookupRepairBarcode(code);
      setForm(f => ({
        ...f,
        바코드: found.바코드 || code,
        업체명: found.업체명 || f.업체명,
        제품명: found.제품명 || f.제품명,
        옵션: found.옵션 || f.옵션,
      }));
      setLookupOk(true);
      setLookupHint(`✓ ${found.업체명 || ''} / ${found.제품명 || ''} ${found.옵션 ? `/ ${found.옵션}` : ''} 자동 입력됨`);
    } catch {
      setLookupOk(false);
      setLookupHint('미등록 바코드입니다. 업체명·제품명을 직접 입력하세요.');
    } finally {
      setLookingUp(false);
    }
  }

  async function save() {
    if (!form.바코드.trim() && (!form.업체명.trim() || !form.제품명.trim())) {
      onMessage({ type: 'error', text: '바코드 또는 업체명+제품명을 입력하세요.' });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        날짜: form.날짜,
        바코드: form.바코드.trim() || undefined,
        업체명: form.업체명.trim() || undefined,
        제품명: form.제품명.trim() || undefined,
        옵션: form.옵션.trim() || undefined,
        불량명: form.불량명.trim() || undefined,
        수량: Number(form.수량) || 1,
        비고: form.비고.trim() || undefined,
        처리결과: form.처리결과 || undefined,
        출처: 'manual',
      };
      let id = initial?.id;
      if (initial) {
        await updateDefectLog(initial.id, payload);
        onMessage({ type: 'success', text: '불량일지가 수정되었습니다.' });
      } else {
        const created = await createDefectLog(payload);
        id = created.id;
        onMessage({ type: 'success', text: '불량일지가 추가되었습니다.' });
      }
      if (id && (beforeFile || afterFile || extraFiles.length)) {
        await uploadDefectPhotos(id, { before: beforeFile, after: afterFile, extra: extraFiles });
      }
      onSaved();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose} maxWidth={820}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem 1.25rem' }}>
        <Field label="날짜 *">
          <input type="date" value={form.날짜} onChange={(e) => setForm({ ...form, 날짜: e.target.value })} style={inputStyle} />
        </Field>
        <Field label="바코드">
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={form.바코드}
              onChange={(e) => { setForm({ ...form, 바코드: e.target.value }); setLookupHint(''); setLookupOk(false); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); searchBarcode(); } }}
              placeholder="바코드 입력 후 검색"
              style={inputStyle}
            />
            <button
              type="button"
              onClick={() => searchBarcode()}
              disabled={lookingUp}
              style={{ ...btn('#0f766e'), whiteSpace: 'nowrap', opacity: lookingUp ? 0.7 : 1 }}
            >
              {lookingUp ? '검색 중...' : '검색'}
            </button>
          </div>
          {lookupHint && (
            <p style={{ fontSize: '0.8rem', color: lookupOk ? '#16a34a' : '#b45309', margin: '0.25rem 0 0' }}>
              {lookupHint}
            </p>
          )}
        </Field>
        <Field label="업체명">
          <input value={form.업체명} onChange={(e) => { setForm({ ...form, 업체명: e.target.value }); setLookupHint(''); setLookupOk(false); }} style={inputStyle} />
        </Field>
        <Field label="제품명">
          <input value={form.제품명} onChange={(e) => { setForm({ ...form, 제품명: e.target.value }); setLookupHint(''); setLookupOk(false); }} style={inputStyle} />
        </Field>
        <Field label="옵션">
          <input value={form.옵션} onChange={(e) => setForm({ ...form, 옵션: e.target.value })} placeholder="블랙" style={inputStyle} />
        </Field>
        <Field label="불량명">
          <input value={form.불량명} onChange={(e) => setForm({ ...form, 불량명: e.target.value })} placeholder="구멍, 열펜, 올풀림 등" style={inputStyle} />
        </Field>
        <Field label="수량">
          <input type="number" min={1} value={form.수량} onChange={(e) => setForm({ ...form, 수량: Number(e.target.value) })} style={inputStyle} />
        </Field>
        <Field label="처리결과">
          <select value={form.처리결과} onChange={(e) => setForm({ ...form, 처리결과: e.target.value })} style={inputStyle}>
            <option value="">미처리</option>
            {RESULT_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </Field>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="비고">
            <input value={form.비고} onChange={(e) => setForm({ ...form, 비고: e.target.value })} style={inputStyle} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <Field label="사진 1">
            <input type="file" accept="image/*" onChange={(e) => setBeforeFile(e.target.files?.[0] || null)} style={{ width: '100%' }} />
          </Field>
          <Field label="사진 2">
            <input type="file" accept="image/*" onChange={(e) => setAfterFile(e.target.files?.[0] || null)} style={{ width: '100%' }} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="추가 사진 (여러 장)">
            <input type="file" accept="image/*" multiple onChange={(e) => setExtraFiles(Array.from(e.target.files || []))} style={{ width: '100%' }} />
          </Field>
        </div>
        {initial && (
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <PhotoThumb filename={initial.before_image} label="사진1" onClick={() => {}} />
            <PhotoThumb filename={initial.after_image} label="사진2" onClick={() => {}} />
            {(initial.extra_images || []).map((fn, i) => (
              <PhotoThumb key={`${fn}-${i}`} filename={fn} label={`추가${i + 1}`} onClick={() => {}} />
            ))}
          </div>
        )}
        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
          <button onClick={onClose} style={btn('#6b7280')}>취소</button>
          <button onClick={save} disabled={saving} style={btn('#2563eb')}>{saving ? '저장 중...' : '저장'}</button>
        </div>
      </div>
    </Modal>
  );
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  );
}

function Modal({ title, onClose, children, maxWidth = 560 }: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: number;
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: 'white', padding: '1.5rem', borderRadius: 8,
        maxWidth, width: '92%', maxHeight: '90vh', overflowY: 'auto',
        boxSizing: 'border-box',
      }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '1rem' }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ConfirmModal({ text, onCancel, onConfirm }: { text: string; onCancel: () => void; onConfirm: () => void }) {
  return (
    <Modal title="확인" onClose={onCancel}>
      <p style={{ marginBottom: 16 }}>{text}</p>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button onClick={onCancel} style={btn('#6b7280')}>취소</button>
        <button onClick={onConfirm} style={btn('#ef4444')}>삭제</button>
      </div>
    </Modal>
  );
}
