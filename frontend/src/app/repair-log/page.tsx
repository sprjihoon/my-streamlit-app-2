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
  getRepairLogExportUrl,
  getRepairBarcodes,
  lookupRepairBarcode,
  createRepairBarcode,
  updateRepairBarcode,
  deleteRepairBarcode,
  uploadRepairBarcodes,
  getRepairBarcodeTemplateUrl,
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
  RepairBarcode,
  RepairWorkType,
  RepairDefect,
} from '@/lib/api';

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
  const [tab, setTab] = useState<'logs' | 'barcodes' | 'catalog'>('logs');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{
        fontSize: '1.375rem', fontWeight: 700, marginBottom: '1rem',
        color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)',
      }}>
        수선작업일지
      </h1>

      {message && (
        <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />
      )}

      <div style={{ display: 'flex', gap: 0, marginBottom: '1rem', borderBottom: '1px solid #e5e7eb' }}>
        {([
          ['logs', '수선일지 목록'],
          ['barcodes', '바코드 등록'],
          ['catalog', '작업/불량 설정'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              padding: '0.65rem 1.25rem',
              border: 'none',
              borderBottom: tab === key ? '2px solid #2563eb' : '2px solid transparent',
              background: 'transparent',
              color: tab === key ? '#2563eb' : '#6b7280',
              fontWeight: tab === key ? 700 : 500,
              cursor: 'pointer',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: tab === 'logs' ? 'block' : 'none' }}>
        <LogsTab onMessage={setMessage} />
      </div>
      <div style={{ display: tab === 'barcodes' ? 'block' : 'none' }}>
        <BarcodesTab onMessage={setMessage} />
      </div>
      <div style={{ display: tab === 'catalog' ? 'block' : 'none' }}>
        <CatalogTab onMessage={setMessage} />
      </div>
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
        getRepairLogStats({ period_from: periodFrom, period_to: periodTo }),
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
          <Card title="전체 건수"><p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total.toLocaleString()}</p></Card>
          <Card title="전체 금액"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#16a34a' }}>{stats.total_amount.toLocaleString()}원</p></Card>
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
          <a href={getRepairLogExportUrl(periodFrom, periodTo)} style={{ ...btn('#0f766e'), textDecoration: 'none' }}>
            엑셀 다운로드
          </a>
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
                    {['날짜', '업체명', '제품명', '옵션', '바코드', '불량명', '작업', '수량', '비용', '작성자', '전', '후', ''].map((h) => (
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
                      <td style={{ padding: '0.5rem' }}><PhotoThumb filename={log.before_image} label="전" onClick={setPreview} /></td>
                      <td style={{ padding: '0.5rem' }}><PhotoThumb filename={log.after_image} label="후" onClick={setPreview} /></td>
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
  const [barcodeFile, setBarcodeFile] = useState<File | null>(null);

  async function fillPrice(work: string, vendorName: string) {
    if (!work.trim()) return;
    try {
      const p = await getRepairCatalogPrice(work, vendorName || undefined);
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
      if (form.작업) fillPrice(form.작업, vendorName);
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
      if (id && (beforeFile || afterFile || barcodeFile)) {
        await uploadRepairPhotos(id, { before: beforeFile, after: afterFile, barcode: barcodeFile });
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
            onBlur={() => { if (form.작업) fillPrice(form.작업, form.업체명); }}
            style={inputStyle}
          />
        </Field>
        <Field label="제품명">
          <input value={form.제품명} onChange={(e) => setForm({ ...form, 제품명: e.target.value })} style={inputStyle} />
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
                fillPrice(e.target.value, form.업체명);
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
              onBlur={() => { if (form.작업) fillPrice(form.작업, form.업체명); }}
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
        <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, minWidth: 0 }}>
          <Field label="수선 전">
            <input type="file" accept="image/*" onChange={(e) => setBeforeFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
          <Field label="수선 후">
            <input type="file" accept="image/*" onChange={(e) => setAfterFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
          <Field label="바코드 사진">
            <input type="file" accept="image/*" onChange={(e) => setBarcodeFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
        </div>
        {initial && (
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8 }}>
            <PhotoThumb filename={initial.before_image} label="전" onClick={() => {}} />
            <PhotoThumb filename={initial.after_image} label="후" onClick={() => {}} />
            <PhotoThumb filename={initial.barcode_image} label="바코드" onClick={() => {}} />
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

function BarcodesTab({ onMessage }: { onMessage: (m: { type: 'success' | 'error'; text: string } | null) => void }) {
  const [items, setItems] = useState<RepairBarcode[]>([]);
  const [vendors, setVendors] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [vendor, setVendor] = useState('');
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState<RepairBarcode | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const emptyForm = { 바코드: '', 업체명: '', 제품명: '', 옵션: '', 상품코드: '', 로케이션: '', 상품명: '' };
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const res = await getRepairBarcodes({ q: q || undefined, vendor: vendor || undefined, limit: 200 });
      setItems(res.items);
      setTotal(res.total);
      setVendors(res.filters.vendors);
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '바코드 목록 실패' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function saveManual() {
    if (!form.바코드.trim() || !form.업체명.trim() || !form.제품명.trim()) {
      onMessage({ type: 'error', text: '바코드, 업체명, 제품명은 필수입니다.' });
      return;
    }
    try {
      if (editing) {
        await updateRepairBarcode(editing.바코드, {
          업체명: form.업체명, 제품명: form.제품명, 옵션: form.옵션,
          상품코드: form.상품코드, 로케이션: form.로케이션, 상품명: form.상품명,
        });
        onMessage({ type: 'success', text: '바코드가 수정되었습니다.' });
      } else {
        await createRepairBarcode({
          바코드: form.바코드.trim(),
          업체명: form.업체명.trim(),
          제품명: form.제품명.trim(),
          옵션: form.옵션 || undefined,
          상품코드: form.상품코드 || undefined,
          로케이션: form.로케이션 || undefined,
          상품명: form.상품명 || undefined,
        });
        onMessage({ type: 'success', text: '바코드가 등록되었습니다.' });
      }
      setForm(emptyForm);
      setEditing(null);
      load();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' });
    }
  }

  async function onExcel(file: File) {
    setUploading(true);
    try {
      const res = await uploadRepairBarcodes(file);
      onMessage({ type: 'success', text: res.message });
      load();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '업로드 실패' });
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <Card title="수동 등록">
        <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: 12 }}>
          필수: 바코드, 업체명, 제품명. 옵션(색상)은 권장.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
          <Field label="바코드 *">
            <input value={form.바코드} disabled={!!editing} onChange={(e) => setForm({ ...form, 바코드: e.target.value })} style={inputStyle} placeholder="ON56S152917" />
          </Field>
          <Field label="업체명 *">
            <input value={form.업체명} onChange={(e) => setForm({ ...form, 업체명: e.target.value })} style={inputStyle} placeholder="자체제작_베으" />
          </Field>
          <Field label="제품명 *">
            <input value={form.제품명} onChange={(e) => setForm({ ...form, 제품명: e.target.value })} style={inputStyle} placeholder="릴리프T" />
          </Field>
          <Field label="옵션">
            <input value={form.옵션} onChange={(e) => setForm({ ...form, 옵션: e.target.value })} style={inputStyle} placeholder="블랙" />
          </Field>
          <Field label="상품코드">
            <input value={form.상품코드} onChange={(e) => setForm({ ...form, 상품코드: e.target.value })} style={inputStyle} />
          </Field>
          <Field label="로케이션">
            <input value={form.로케이션} onChange={(e) => setForm({ ...form, 로케이션: e.target.value })} style={inputStyle} />
          </Field>
        </div>
        <Field label="상품명(긴 이름)">
          <input value={form.상품명} onChange={(e) => setForm({ ...form, 상품명: e.target.value })} style={{ ...inputStyle, marginTop: 8 }} />
        </Field>
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button onClick={saveManual} style={btn('#2563eb')}>{editing ? '수정 저장' : '등록'}</button>
          {editing && (
            <button onClick={() => { setEditing(null); setForm(emptyForm); }} style={btn('#6b7280')}>취소</button>
          )}
        </div>
      </Card>

      <div style={{ marginTop: '1rem' }}>
        <Card title="엑셀 일괄 업로드">
          <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: 12 }}>
            창고용 전체상품목록(13열, 마지막 열이 공급처=업체명) 또는 간단 양식을 올리면 됩니다. 같은 바코드는 덮어씁니다.
          </p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="file"
              accept=".xls,.xlsx,.html"
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onExcel(f);
                e.target.value = '';
              }}
            />
            {uploading && <span style={{ color: '#666' }}>업로드 중...</span>}
            <a href={getRepairBarcodeTemplateUrl()} style={{ ...btn('#0f766e'), textDecoration: 'none', fontSize: '0.85rem' }}>
              간단 양식 다운로드
            </a>
          </div>
        </Card>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Card title={`등록된 바코드 (${total}건)`}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="바코드·제품명 검색" style={{ ...inputStyle, maxWidth: 240 }} />
            <select value={vendor} onChange={(e) => setVendor(e.target.value)} style={{ ...inputStyle, maxWidth: 200 }}>
              <option value="">전체 업체</option>
              {vendors.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <button onClick={load} style={btn('#2563eb')}>검색</button>
          </div>
          {loading ? <Loading /> : items.length === 0 ? (
            <p style={{ color: '#666' }}>등록된 바코드가 없습니다.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    {['바코드', '업체명', '제품명', '옵션', '상품코드', '로케이션', '출처', ''].map((h) => (
                      <th key={h} style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((row) => (
                    <tr key={row.바코드} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{row.바코드}</td>
                      <td style={{ padding: '0.5rem' }}>{row.업체명}</td>
                      <td style={{ padding: '0.5rem' }}>{row.제품명}</td>
                      <td style={{ padding: '0.5rem' }}>{row.옵션 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.상품코드 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.로케이션 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.출처 || '-'}</td>
                      <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                        <button onClick={() => { setEditing(row); setForm({
                          바코드: row.바코드, 업체명: row.업체명, 제품명: row.제품명,
                          옵션: row.옵션 || '', 상품코드: row.상품코드 || '',
                          로케이션: row.로케이션 || '', 상품명: row.상품명 || '',
                        }); }} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
                        <button onClick={() => setDeleting(row.바코드)} style={{ ...btn('#ef4444'), padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>삭제</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {deleting && (
        <ConfirmModal
          text={`바코드 ${deleting} 을 삭제할까요?`}
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            try {
              await deleteRepairBarcode(deleting);
              onMessage({ type: 'success', text: '바코드가 삭제되었습니다.' });
              setDeleting(null);
              load();
            } catch (e) {
              onMessage({ type: 'error', text: e instanceof Error ? e.message : '삭제 실패' });
            }
          }}
        />
      )}
    </>
  );
}

function CatalogTab({ onMessage }: { onMessage: (m: { type: 'success' | 'error'; text: string } | null) => void }) {
  const [workTypes, setWorkTypes] = useState<RepairWorkType[]>([]);
  const [defects, setDefects] = useState<RepairDefect[]>([]);
  const [loading, setLoading] = useState(true);
  const emptyWork = { 작업명: '', 기본비용: 0, 별칭: '' };
  const emptyDefect = { 불량명: '', 별칭: '' };
  const [workForm, setWorkForm] = useState(emptyWork);
  const [defectForm, setDefectForm] = useState(emptyDefect);
  const [editingWork, setEditingWork] = useState<string | null>(null);
  const [editingDefect, setEditingDefect] = useState<string | null>(null);
  const [deletingWork, setDeletingWork] = useState<string | null>(null);
  const [deletingDefect, setDeletingDefect] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const c = await getRepairCatalog();
      setWorkTypes(c.work_types);
      setDefects(c.defects);
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '설정 불러오기 실패' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function saveWork() {
    if (!workForm.작업명.trim()) {
      onMessage({ type: 'error', text: '작업명은 필수입니다.' });
      return;
    }
    try {
      await saveRepairWorkType({
        작업명: workForm.작업명.trim(),
        기본비용: Number(workForm.기본비용) || 0,
        별칭: workForm.별칭.trim() || undefined,
      });
      onMessage({ type: 'success', text: editingWork ? '작업이 수정되었습니다.' : '작업이 추가되었습니다.' });
      setWorkForm(emptyWork);
      setEditingWork(null);
      load();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' });
    }
  }

  async function saveDefect() {
    if (!defectForm.불량명.trim()) {
      onMessage({ type: 'error', text: '불량명은 필수입니다.' });
      return;
    }
    try {
      await saveRepairDefect({
        불량명: defectForm.불량명.trim(),
        별칭: defectForm.별칭.trim() || undefined,
      });
      onMessage({ type: 'success', text: editingDefect ? '불량명이 수정되었습니다.' : '불량명이 추가되었습니다.' });
      setDefectForm(emptyDefect);
      setEditingDefect(null);
      load();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' });
    }
  }

  return (
    <>
      <Card title="작업 설정">
        <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: 12 }}>
          봇·웹 수동 입력이 같은 목록을 씁니다. 별칭은 쉼표로 구분합니다. 예: 바느질,바느질작업
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 2fr auto auto', gap: 8, alignItems: 'end', marginBottom: 16 }}>
          <Field label="작업명 *">
            <input
              value={workForm.작업명}
              disabled={!!editingWork}
              onChange={(e) => setWorkForm({ ...workForm, 작업명: e.target.value })}
              placeholder="스팀작업"
              style={inputStyle}
            />
          </Field>
          <Field label="기본비용 *">
            <input
              type="number"
              min={0}
              value={workForm.기본비용}
              onChange={(e) => setWorkForm({ ...workForm, 기본비용: Number(e.target.value) })}
              style={inputStyle}
            />
          </Field>
          <Field label="별칭">
            <input
              value={workForm.별칭}
              onChange={(e) => setWorkForm({ ...workForm, 별칭: e.target.value })}
              placeholder="스팀"
              style={inputStyle}
            />
          </Field>
          <button onClick={saveWork} style={btn('#2563eb')}>{editingWork ? '수정 저장' : '추가'}</button>
          {editingWork && (
            <button onClick={() => { setEditingWork(null); setWorkForm(emptyWork); }} style={btn('#6b7280')}>취소</button>
          )}
        </div>
        {loading ? <Loading /> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  {['작업명', '기본비용', '별칭', ''].map((h) => (
                    <th key={h} style={{ padding: '0.5rem', textAlign: h === '기본비용' ? 'right' : 'left', borderBottom: '1px solid #ddd' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {workTypes.map((w) => (
                  <tr key={w.작업명} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '0.5rem', fontWeight: 500 }}>{w.작업명}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>{w.기본비용.toLocaleString()}원</td>
                    <td style={{ padding: '0.5rem', color: '#666' }}>{w.별칭 || '-'}</td>
                    <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                      <button onClick={() => {
                        setEditingWork(w.작업명);
                        setWorkForm({ 작업명: w.작업명, 기본비용: w.기본비용, 별칭: w.별칭 || '' });
                      }} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
                      <button onClick={() => setDeletingWork(w.작업명)} style={{ ...btn('#ef4444'), padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>삭제</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div style={{ marginTop: '1rem' }}>
        <Card title="불량명 설정">
          <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: 12 }}>
            채팅에서 구멍수선처럼 별칭이 와도 마스터 불량명으로 맞춥니다.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr auto auto', gap: 8, alignItems: 'end', marginBottom: 16 }}>
            <Field label="불량명 *">
              <input
                value={defectForm.불량명}
                disabled={!!editingDefect}
                onChange={(e) => setDefectForm({ ...defectForm, 불량명: e.target.value })}
                placeholder="구멍"
                style={inputStyle}
              />
            </Field>
            <Field label="별칭">
              <input
                value={defectForm.별칭}
                onChange={(e) => setDefectForm({ ...defectForm, 별칭: e.target.value })}
                placeholder="구멍수선"
                style={inputStyle}
              />
            </Field>
            <button onClick={saveDefect} style={btn('#2563eb')}>{editingDefect ? '수정 저장' : '추가'}</button>
            {editingDefect && (
              <button onClick={() => { setEditingDefect(null); setDefectForm(emptyDefect); }} style={btn('#6b7280')}>취소</button>
            )}
          </div>
          {loading ? <Loading /> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    {['불량명', '별칭', ''].map((h) => (
                      <th key={h} style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {defects.map((d) => (
                    <tr key={d.불량명} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.5rem', fontWeight: 500 }}>{d.불량명}</td>
                      <td style={{ padding: '0.5rem', color: '#666' }}>{d.별칭 || '-'}</td>
                      <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                        <button onClick={() => {
                          setEditingDefect(d.불량명);
                          setDefectForm({ 불량명: d.불량명, 별칭: d.별칭 || '' });
                        }} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
                        <button onClick={() => setDeletingDefect(d.불량명)} style={{ ...btn('#ef4444'), padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>삭제</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {deletingWork && (
        <ConfirmModal
          text={`작업 "${deletingWork}" 을 삭제할까요? 기존 수선일지는 그대로 남습니다.`}
          onCancel={() => setDeletingWork(null)}
          onConfirm={async () => {
            try {
              await deleteRepairWorkType(deletingWork);
              onMessage({ type: 'success', text: '작업이 삭제되었습니다.' });
              setDeletingWork(null);
              load();
            } catch (e) {
              onMessage({ type: 'error', text: e instanceof Error ? e.message : '삭제 실패' });
            }
          }}
        />
      )}
      {deletingDefect && (
        <ConfirmModal
          text={`불량명 "${deletingDefect}" 을 삭제할까요? 기존 수선일지는 그대로 남습니다.`}
          onCancel={() => setDeletingDefect(null)}
          onConfirm={async () => {
            try {
              await deleteRepairDefect(deletingDefect);
              onMessage({ type: 'success', text: '불량명이 삭제되었습니다.' });
              setDeletingDefect(null);
              load();
            } catch (e) {
              onMessage({ type: 'error', text: e instanceof Error ? e.message : '삭제 실패' });
            }
          }}
        />
      )}
    </>
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
