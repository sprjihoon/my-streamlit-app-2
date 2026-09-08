'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import {
  getRepairLogs,
  getRepairLogStats,
  createRepairLog,
  updateRepairLog,
  deleteRepairLog,
  uploadRepairPhotos,
  getOldRepairPhotos,
  purgeOldRepairPhotos,
  lookupRepairBarcode,
  getRepairCatalog,
  getRepairCatalogPrice,
  saveRepairWorkType,
  deleteRepairWorkType,
  saveRepairDefect,
  deleteRepairDefect,
  repairImageUrl,
  RepairLog,
  RepairLogFilters,
  RepairLogStats,
  RepairWorkType,
  RepairDefect,
} from '@/lib/api';
import { downloadRepairLogExcel } from '@/lib/repairLogExcel';

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

function formatPrice(n: number | null | undefined) {
  if (n == null) return '-';
  return `${n.toLocaleString()}원`;
}

function formatDateTime(dateStr: string | null) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function PhotoThumb({
  filename,
  label,
  onClick,
}: {
  filename: string | null;
  label: string;
  onClick: (url: string) => void;
}) {
  const url = repairImageUrl(filename);
  if (!url) {
    return <span style={{ color: '#bbb', fontSize: '0.75rem' }}>{label} 없음</span>;
  }
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

export default function RepairLogPage() {
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{
        fontSize: '1.375rem', fontWeight: 700, marginBottom: '1rem',
        color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)'
      }}>
        수선작업일지
      </h1>

      {message && (
        <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />
      )}

      <LogsTab onMessage={setMessage} />
    </div>
  );
}

function LogsTab({ onMessage }: { onMessage: (m: { type: 'success' | 'error'; text: string } | null) => void }) {
  const defaults = monthRange();
  const [logs, setLogs] = useState<RepairLog[]>([]);
  const [filters, setFilters] = useState<RepairLogFilters | null>(null);
  const [stats, setStats] = useState<RepairLogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [periodFrom, setPeriodFrom] = useState(defaults.from);
  const [periodTo, setPeriodTo] = useState(defaults.to);
  const [vendor, setVendor] = useState('');
  const [workType, setWorkType] = useState('');
  const [defect, setDefect] = useState('');
  const [author, setAuthor] = useState('');
  const [catalogWorks, setCatalogWorks] = useState<RepairWorkType[]>([]);
  const [catalogDefects, setCatalogDefects] = useState<RepairDefect[]>([]);
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [preview, setPreview] = useState<string | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<RepairLog | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [purgingOld, setPurgingOld] = useState(false);
  const [excelExporting, setExcelExporting] = useState(false);

  const currentFilters = {
    period_from: periodFrom,
    period_to: periodTo,
    vendor: vendor || undefined,
    work_type: workType || undefined,
    defect: defect || undefined,
    author: author || undefined,
  };

  const totalPages = pageSize === 0 ? 1 : Math.max(1, Math.ceil(totalCount / pageSize));

  async function load() {
    setLoading(true);
    try {
      const limit = pageSize === 0 ? 2000 : pageSize;
      const offset = pageSize === 0 ? 0 : (currentPage - 1) * pageSize;
      const [list, st] = await Promise.all([
        getRepairLogs({
          period_from: periodFrom, period_to: periodTo,
          vendor: vendor || undefined, work_type: workType || undefined,
          defect: defect || undefined,
          author: author || undefined, limit, offset,
        }),
        getRepairLogStats(currentFilters),
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

  useEffect(() => {
    getRepairCatalog()
      .then((c) => {
        setCatalogWorks(c.work_types);
        setCatalogDefects(c.defects);
      })
      .catch(() => {});
  }, []);

  return (
    <>
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <Card title="조회 건수"><p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total.toLocaleString()}</p></Card>
          <Card title="조회 금액"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#16a34a' }}>{stats.total_amount.toLocaleString()}원</p></Card>
          <Card title="오늘 건수"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb' }}>{stats.today.toLocaleString()}</p></Card>
        </div>
      )}

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
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>작업</label>
            <select value={workType} onChange={(e) => setWorkType(e.target.value)} style={inputStyle}>
              <option value="">전체</option>
              {filters?.work_types.map((t) => <option key={t} value={t}>{t}</option>)}
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
            setVendor(''); setWorkType(''); setDefect(''); setAuthor('');
            setCurrentPage(1);
          }} style={btn('#6b7280')}>초기화</button>
          <button
            onClick={async () => {
              if (!periodFrom || !periodTo) {
                onMessage({ type: 'error', text: '엑셀 보고를 위해 시작일과 종료일을 선택하세요.' });
                return;
              }
              setExcelExporting(true);
              try {
                await downloadRepairLogExcel(currentFilters);
                onMessage({ type: 'success', text: '사진 포함 엑셀 보고서를 저장했습니다.' });
              } catch (e) {
                onMessage({ type: 'error', text: e instanceof Error ? e.message : '엑셀 생성 실패' });
              } finally {
                setExcelExporting(false);
              }
            }}
            disabled={excelExporting}
            style={btn('#0f766e')}
          >
            {excelExporting ? '엑셀 만드는 중...' : '엑셀 다운로드 (사진 포함)'}
          </button>
          <button
            onClick={async () => {
              try {
                const info = await getOldRepairPhotos(60);
                if (!info.files) {
                  onMessage({ type: 'success', text: `${info.cutoff} 이전 삭제할 사진이 없습니다.` });
                  return;
                }
                if (!window.confirm(`${info.cutoff} 이전 사진 ${info.files}장(바코드·전후·연결 없는 파일, ${info.logs}건)을 서버에서 완전히 삭제할까요?\n일지 내용은 그대로 남습니다. 되돌릴 수 없습니다.`)) {
                  return;
                }
                setPurgingOld(true);
                const result = await purgeOldRepairPhotos(60);
                onMessage({ type: 'success', text: result.message });
                load();
              } catch (e) {
                onMessage({ type: 'error', text: e instanceof Error ? e.message : '사진 삭제 실패' });
              } finally {
                setPurgingOld(false);
              }
            }}
            disabled={purgingOld}
            style={btn('#b45309')}
          >
            {purgingOld ? '삭제 중...' : '60일 이전 사진 완전 삭제'}
          </button>
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
        <p style={{ fontSize: '0.8rem', color: '#6b7280', margin: '0.6rem 0 0' }}>
          엑셀은 현재 선택한 업체·기간 필터의 수선일지와 작업 사진을 담습니다. 바코드 사진은 넣지 않습니다.
        </p>
      </Card>

      <div style={{ marginTop: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>
            수선일지 목록
            <span style={{ color: '#666', fontWeight: 400, marginLeft: 8 }}>
              ({pageSize === 0 ? totalCount : `${logs.length}/${totalCount}`}건)
            </span>
          </h3>
          <button onClick={() => setShowAdd(true)} style={btn('#22c55e')}>➕ 수동 추가</button>
        </div>

        <Card title="">
          {loading ? <Loading /> : logs.length === 0 ? (
            <p style={{ color: '#666' }}>수선일지가 없습니다.</p>
          ) : (
            <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    {['날짜', '업체명', '제품명', '옵션', '바코드', '불량명', '작업', '수량', '비용', '작성자', '수정자', '수정시간', '사진', ''].map((h) => (
                      <th key={h} style={{ padding: '0.5rem', textAlign: h === '수량' || h === '비용' ? 'right' : 'left', borderBottom: '1px solid #ddd' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.5rem' }}>{log.날짜 || '-'}</td>
                      <td style={{ padding: '0.5rem', fontWeight: 500 }}>{log.업체명 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.제품명 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.옵션 || '-'}</td>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{log.바코드 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.불량명 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.작업 || '-'}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>{log.수량?.toLocaleString() ?? '-'}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, color: '#16a34a' }}>{formatPrice(log.비용)}</td>
                      <td style={{ padding: '0.5rem' }}>{log.작성자 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.수정자 || '-'}</td>
                      <td style={{ padding: '0.5rem', fontSize: '0.75rem', color: '#666' }}>{formatDateTime(log.수정시간)}</td>
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
        <LogFormModal
          title="수선일지 수동 추가"
          workTypes={catalogWorks}
          defects={catalogDefects}
          onClose={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); load(); }}
          onMessage={onMessage}
        />
      )}
      {editing && (
        <LogFormModal
          title="수선일지 수정"
          initial={editing}
          workTypes={catalogWorks}
          defects={catalogDefects}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
          onMessage={onMessage}
        />
      )}
      {deletingId != null && (
        <ConfirmModal
          text="이 수선일지를 삭제하시겠습니까? 사진도 함께 삭제됩니다."
          onCancel={() => setDeletingId(null)}
          onConfirm={async () => {
            try {
              await deleteRepairLog(deletingId);
              onMessage({ type: 'success', text: '수선일지가 삭제되었습니다.' });
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

function LogFormModal({
  title, initial, workTypes, defects, onClose, onSaved, onMessage,
}: {
  title: string;
  initial?: RepairLog;
  workTypes: RepairWorkType[];
  defects: RepairDefect[];
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
    작업: initial?.작업 || '',
    수량: initial?.수량 ?? 1,
    비용: initial?.비용 ?? 0,
    비고: initial?.비고 || '',
  });
  const [customWork, setCustomWork] = useState(
    !!(initial?.작업 && !workTypes.some((w) => w.작업명 === initial.작업))
  );
  const [customDefect, setCustomDefect] = useState(
    !!(initial?.불량명 && !defects.some((d) => d.불량명 === initial.불량명))
  );
  const [lookupHint, setLookupHint] = useState('');
  const [lookupOk, setLookupOk] = useState(false);
  const [lookingUp, setLookingUp] = useState(false);
  const [priceHint, setPriceHint] = useState('');
  const [saving, setSaving] = useState(false);
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);
  const [extraFiles, setExtraFiles] = useState<File[]>([]);

  async function fillPrice(work: string, vendorName: string, productName?: string) {
    if (!work.trim()) return;
    try {
      const p = await getRepairCatalogPrice(work, vendorName || undefined, productName || form.제품명 || undefined);
      if (p.found && p.비용 != null) {
        setForm((f) => ({ ...f, 작업: p.작업명 || f.작업, 비용: p.비용 as number }));
        setPriceHint(p.message);
      } else {
        setPriceHint(p.message);
      }
    } catch {
      setPriceHint('');
    }
  }

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
      const vendorName = found.업체명 || form.업체명;
      setForm((f) => ({
        ...f,
        바코드: found.바코드 || code,
        업체명: found.업체명 || f.업체명,
        제품명: found.제품명 || f.제품명,
        옵션: found.옵션 || f.옵션,
      }));
      const extra = [found.상품코드 && `코드 ${found.상품코드}`, found.로케이션 && `로케이션 ${found.로케이션}`]
        .filter(Boolean)
        .join(' · ');
      setLookupOk(true);
      setLookupHint(
        `등록 정보 입력됨: ${found.업체명} / ${found.제품명}${found.옵션 ? ` / ${found.옵션}` : ''}${extra ? ` (${extra})` : ''}`
      );
      if (form.작업) fillPrice(form.작업, vendorName, found.제품명 || form.제품명);
    } catch {
      setLookupOk(false);
      setLookupHint('미등록 바코드입니다. 업체명·제품명을 직접 입력하세요.');
    } finally {
      setLookingUp(false);
    }
  }

  async function save() {
    if (!form.작업.trim() || !form.비용) {
      onMessage({ type: 'error', text: '작업과 비용은 필수입니다.' });
      return;
    }
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
        작업: form.작업.trim(),
        수량: Number(form.수량) || 1,
        비용: Number(form.비용) || 0,
        비고: form.비고.trim() || undefined,
        출처: 'manual',
      };
      let id = initial?.id;
      if (initial) {
        await updateRepairLog(initial.id, payload);
        onMessage({ type: 'success', text: '수선일지가 수정되었습니다.' });
      } else {
        const created = await createRepairLog(payload);
        id = created.id;
        onMessage({ type: 'success', text: '수선일지가 추가되었습니다.' });
      }
      if (id && (beforeFile || afterFile || extraFiles.length)) {
        await uploadRepairPhotos(id, { before: beforeFile, after: afterFile, extra: extraFiles });
      }
      onSaved();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose} maxWidth={860}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem 1.25rem' }}>
        <Field label="날짜 *">
          <input type="date" value={form.날짜} onChange={(e) => setForm({ ...form, 날짜: e.target.value })} style={inputStyle} />
        </Field>
        <Field label="바코드">
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={form.바코드}
              onChange={(e) => { setForm({ ...form, 바코드: e.target.value }); setLookupHint(''); setLookupOk(false); }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  searchBarcode(e.currentTarget.value);
                }
              }}
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
          <input
            value={form.업체명}
            onChange={(e) => setForm({ ...form, 업체명: e.target.value })}
            onBlur={() => { if (form.작업) fillPrice(form.작업, form.업체명, form.제품명); }}
            style={inputStyle}
          />
        </Field>
        <Field label="제품명">
          <input
            value={form.제품명}
            onChange={(e) => setForm({ ...form, 제품명: e.target.value })}
            onBlur={() => { if (form.작업) fillPrice(form.작업, form.업체명, form.제품명); }}
            style={inputStyle}
          />
        </Field>
        <Field label="옵션">
          <input value={form.옵션} onChange={(e) => setForm({ ...form, 옵션: e.target.value })} placeholder="블랙" style={inputStyle} />
        </Field>
        <Field label="불량명">
          <select
            value={customDefect ? '__custom__' : form.불량명}
            onChange={(e) => {
              if (e.target.value === '__custom__') {
                setCustomDefect(true);
                setForm({ ...form, 불량명: '' });
              } else {
                setCustomDefect(false);
                setForm({ ...form, 불량명: e.target.value });
              }
            }}
            style={inputStyle}
          >
            <option value="">선택</option>
            {defects.map((d) => <option key={d.불량명} value={d.불량명}>{d.불량명}{d.별칭 ? ` (${d.별칭})` : ''}</option>)}
            <option value="__custom__">직접 입력</option>
          </select>
          {customDefect && (
            <input
              value={form.불량명}
              onChange={(e) => setForm({ ...form, 불량명: e.target.value })}
              placeholder="새 불량명"
              style={{ ...inputStyle, marginTop: 6 }}
            />
          )}
        </Field>
        <Field label="작업 *">
          <select
            value={customWork ? '__custom__' : form.작업}
            onChange={(e) => {
              if (e.target.value === '__custom__') {
                setCustomWork(true);
                setForm({ ...form, 작업: '' });
                setPriceHint('');
              } else {
                setCustomWork(false);
                setForm({ ...form, 작업: e.target.value });
                fillPrice(e.target.value, form.업체명, form.제품명);
              }
            }}
            style={inputStyle}
          >
            <option value="">선택</option>
            {workTypes.map((t) => <option key={t.작업명} value={t.작업명}>{t.작업명} ({t.기본비용.toLocaleString()}원)</option>)}
            <option value="__custom__">직접 입력</option>
          </select>
          {customWork && (
            <input
              value={form.작업}
              onChange={(e) => setForm({ ...form, 작업: e.target.value })}
              onBlur={() => { if (form.작업) fillPrice(form.작업, form.업체명, form.제품명); }}
              placeholder="새 작업명"
              style={{ ...inputStyle, marginTop: 6 }}
            />
          )}
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <Field label="수량">
            <input type="number" min={1} value={form.수량} onChange={(e) => setForm({ ...form, 수량: Number(e.target.value) })} style={inputStyle} />
          </Field>
          <Field label="비용 *">
            <input type="number" min={0} value={form.비용} onChange={(e) => { setForm({ ...form, 비용: Number(e.target.value) }); setPriceHint(''); }} style={inputStyle} />
          </Field>
        </div>
        {priceHint && <p style={{ gridColumn: '1 / -1', fontSize: '0.8rem', color: '#2563eb', margin: 0 }}>{priceHint}</p>}
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="비고">
            <input value={form.비고} onChange={(e) => setForm({ ...form, 비고: e.target.value })} style={inputStyle} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, minWidth: 0 }}>
          <Field label="사진 1">
            <input type="file" accept="image/*" onChange={(e) => setBeforeFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
          <Field label="사진 2">
            <input type="file" accept="image/*" onChange={(e) => setAfterFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="추가 사진 (여러 장)">
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => setExtraFiles(Array.from(e.target.files || []))}
              style={{ width: '100%', maxWidth: '100%' }}
            />
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
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
        maxWidth, width: '92%', maxHeight: '90vh', overflowY: 'auto', overflowX: 'hidden',
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
