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
  getRepairBarcodes,
  lookupRepairBarcode,
  getRepairCatalog,
  getRepairCatalogPrice,
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
  return `${n.toLocaleString()}??;
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
    return <span style={{ color: '#bbb', fontSize: '0.75rem' }}>{label} ?놁쓬</span>;
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
        color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)',
      }}>
        ?섏꽑?묒뾽?쇱?
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
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '遺덈윭?ㅺ린 ?ㅽ뙣' });
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
          <Card title="議고쉶 嫄댁닔"><p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total.toLocaleString()}</p></Card>
          <Card title="議고쉶 湲덉븸"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#16a34a' }}>{stats.total_amount.toLocaleString()}??/p></Card>
          <Card title="?ㅻ뒛 嫄댁닔"><p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb' }}>{stats.today.toLocaleString()}</p></Card>
        </div>
      )}

      <Card title="寃???꾪꽣">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>?쒖옉??/label>
            <input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>醫낅즺??/label>
            <input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>?낆껜紐?/label>
            <select value={vendor} onChange={(e) => setVendor(e.target.value)} style={inputStyle}>
              <option value="">?꾩껜</option>
              {filters?.vendors.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>?묒뾽</label>
            <select value={workType} onChange={(e) => setWorkType(e.target.value)} style={inputStyle}>
              <option value="">?꾩껜</option>
              {filters?.work_types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>遺덈웾紐?/label>
            <select value={defect} onChange={(e) => setDefect(e.target.value)} style={inputStyle}>
              <option value="">?꾩껜</option>
              {filters?.defects.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>?묒꽦??/label>
            <select value={author} onChange={(e) => setAuthor(e.target.value)} style={inputStyle}>
              <option value="">?꾩껜</option>
              {filters?.authors.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button onClick={() => { setCurrentPage(1); load(); }} style={btn('#2563eb')}>寃??/button>
          <button onClick={() => {
            const r = monthRange();
            setPeriodFrom(r.from); setPeriodTo(r.to);
            setVendor(''); setWorkType(''); setDefect(''); setAuthor('');
            setCurrentPage(1);
          }} style={btn('#6b7280')}>珥덇린??/button>
          <button
            onClick={async () => {
              if (!periodFrom || !periodTo) {
                onMessage({ type: 'error', text: '?묒? 蹂닿퀬瑜??꾪빐 ?쒖옉?쇨낵 醫낅즺?쇱쓣 ?좏깮?섏꽭??' });
                return;
              }
              setExcelExporting(true);
              try {
                await downloadRepairLogExcel(currentFilters);
                onMessage({ type: 'success', text: '?ъ쭊 ?ы븿 ?묒? 蹂닿퀬?쒕? ??ν뻽?듬땲??' });
              } catch (e) {
                onMessage({ type: 'error', text: e instanceof Error ? e.message : '?묒? ?앹꽦 ?ㅽ뙣' });
              } finally {
                setExcelExporting(false);
              }
            }}
            disabled={excelExporting}
            style={btn('#0f766e')}
          >
            {excelExporting ? '?묒? 留뚮뱶??以?..' : '?묒? ?ㅼ슫濡쒕뱶 (?ъ쭊 ?ы븿)'}
          </button>
          <button
            onClick={async () => {
              try {
                const info = await getOldRepairPhotos(60);
                if (!info.files) {
                  onMessage({ type: 'success', text: `${info.cutoff} ?댁쟾 ??젣???ъ쭊???놁뒿?덈떎.` });
                  return;
                }
                if (!window.confirm(`${info.cutoff} ?댁쟾 ?ъ쭊 ${info.files}??諛붿퐫?쑣룹쟾?꽷룹뿰寃??녿뒗 ?뚯씪, ${info.logs}嫄????쒕쾭?먯꽌 ?꾩쟾????젣?좉퉴??\n?쇱? ?댁슜? 洹몃?濡??⑥뒿?덈떎. ?섎룎由????놁뒿?덈떎.`)) {
                  return;
                }
                setPurgingOld(true);
                const result = await purgeOldRepairPhotos(60);
                onMessage({ type: 'success', text: result.message });
                load();
              } catch (e) {
                onMessage({ type: 'error', text: e instanceof Error ? e.message : '?ъ쭊 ??젣 ?ㅽ뙣' });
              } finally {
                setPurgingOld(false);
              }
            }}
            disabled={purgingOld}
            style={btn('#b45309')}
          >
            {purgingOld ? '??젣 以?..' : '60???댁쟾 ?ъ쭊 ?꾩쟾 ??젣'}
          </button>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.875rem', color: '#666' }}>?섏씠吏??</span>
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }} style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}>
              <option value={50}>50媛?/option>
              <option value={100}>100媛?/option>
              <option value={200}>200媛?/option>
              <option value={0}>?꾩껜</option>
            </select>
          </div>
        </div>
        <p style={{ fontSize: '0.8rem', color: '#6b7280', margin: '0.6rem 0 0' }}>
          ?묒?? ?꾩옱 ?좏깮???낆껜쨌湲곌컙 ?꾪꽣???섏꽑?쇱?? ?묒뾽 ?ъ쭊???댁뒿?덈떎. 諛붿퐫???ъ쭊? ?ｌ? ?딆뒿?덈떎.
        </p>
      </Card>

      <div style={{ marginTop: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>
            ?섏꽑?쇱? 紐⑸줉
            <span style={{ color: '#666', fontWeight: 400, marginLeft: 8 }}>
              ({pageSize === 0 ? totalCount : `${logs.length}/${totalCount}`}嫄?
            </span>
          </h3>
          <button onClick={() => setShowAdd(true)} style={btn('#22c55e')}>???섎룞 異붽?</button>
        </div>

        <Card title="">
          {loading ? <Loading /> : logs.length === 0 ? (
            <p style={{ color: '#666' }}>?섏꽑?쇱?媛 ?놁뒿?덈떎.</p>
          ) : (
            <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    {['?좎쭨', '?낆껜紐?, '?쒗뭹紐?, '?듭뀡', '諛붿퐫??, '遺덈웾紐?, '?묒뾽', '?섎웾', '鍮꾩슜', '?묒꽦??, '?섏젙??, '?섏젙?쒓컙', '?ъ쭊', ''].map((h) => (
                      <th key={h} style={{ padding: '0.5rem', textAlign: h === '?섎웾' || h === '鍮꾩슜' ? 'right' : 'left', borderBottom: '1px solid #ddd' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.5rem' }}>{log.?좎쭨 || '-'}</td>
                      <td style={{ padding: '0.5rem', fontWeight: 500 }}>{log.?낆껜紐?|| '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.?쒗뭹紐?|| '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.?듭뀡 || '-'}</td>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{log.諛붿퐫??|| '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.遺덈웾紐?|| '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.?묒뾽 || '-'}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>{log.?섎웾?.toLocaleString() ?? '-'}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, color: '#16a34a' }}>{formatPrice(log.鍮꾩슜)}</td>
                      <td style={{ padding: '0.5rem' }}>{log.?묒꽦??|| '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{log.?섏젙??|| '-'}</td>
                      <td style={{ padding: '0.5rem', fontSize: '0.75rem', color: '#666' }}>{formatDateTime(log.?섏젙?쒓컙)}</td>
                      <td style={{ padding: '0.5rem' }}>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {[
                            ['?ъ쭊1', log.before_image],
                            ['?ъ쭊2', log.after_image],
                            ...(log.extra_images || []).map((fn, i) => [`異붽?${i + 1}`, fn] as const),
                          ].filter(([, fn]) => fn).map(([label, fn]) => (
                            <PhotoThumb key={`${label}-${fn}`} filename={fn as string} label={label as string} onClick={setPreview} />
                          ))}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                        <button onClick={() => setEditing(log)} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>?섏젙</button>
                        <button onClick={() => setDeletingId(log.id)} style={{ ...btn('#ef4444'), padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>??젣</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && pageSize !== 0 && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
                <button disabled={currentPage === 1} onClick={() => setCurrentPage((p) => p - 1)} style={btn(currentPage === 1 ? '#9ca3af' : '#6b7280')}>?댁쟾</button>
                <span style={{ alignSelf: 'center', fontSize: '0.875rem' }}>{currentPage} / {totalPages}</span>
                <button disabled={currentPage === totalPages} onClick={() => setCurrentPage((p) => p + 1)} style={btn(currentPage === totalPages ? '#9ca3af' : '#6b7280')}>?ㅼ쓬</button>
              </div>
            )}
            </>
          )}
        </Card>
      </div>

      {showAdd && (
        <LogFormModal
          title="?섏꽑?쇱? ?섎룞 異붽?"
          workTypes={catalogWorks}
          defects={catalogDefects}
          onClose={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); load(); }}
          onMessage={onMessage}
        />
      )}
      {editing && (
        <LogFormModal
          title="?섏꽑?쇱? ?섏젙"
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
          text="???섏꽑?쇱?瑜???젣?섏떆寃좎뒿?덇퉴? ?ъ쭊???④퍡 ??젣?⑸땲??"
          onCancel={() => setDeletingId(null)}
          onConfirm={async () => {
            try {
              await deleteRepairLog(deletingId);
              onMessage({ type: 'success', text: '?섏꽑?쇱?媛 ??젣?섏뿀?듬땲??' });
              setDeletingId(null);
              load();
            } catch (e) {
              onMessage({ type: 'error', text: e instanceof Error ? e.message : '??젣 ?ㅽ뙣' });
            }
          }}
        />
      )}
      {preview && (
        <div onClick={() => setPreview(null)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, cursor: 'zoom-out',
        }}>
          <img src={preview} alt="誘몃━蹂닿린" style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8 }} />
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
    ?좎쭨: initial?.?좎쭨 || todayStr(),
    諛붿퐫?? initial?.諛붿퐫??|| '',
    ?낆껜紐? initial?.?낆껜紐?|| '',
    ?쒗뭹紐? initial?.?쒗뭹紐?|| '',
    ?듭뀡: initial?.?듭뀡 || '',
    遺덈웾紐? initial?.遺덈웾紐?|| '',
    ?묒뾽: initial?.?묒뾽 || '',
    ?섎웾: initial?.?섎웾 ?? 1,
    鍮꾩슜: initial?.鍮꾩슜 ?? 0,
    鍮꾧퀬: initial?.鍮꾧퀬 || '',
  });
  const [customWork, setCustomWork] = useState(
    !!(initial?.?묒뾽 && !workTypes.some((w) => w.?묒뾽紐?=== initial.?묒뾽))
  );
  const [customDefect, setCustomDefect] = useState(
    !!(initial?.遺덈웾紐?&& !defects.some((d) => d.遺덈웾紐?=== initial.遺덈웾紐?)
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
      const p = await getRepairCatalogPrice(work, vendorName || undefined, productName || form.?쒗뭹紐?|| undefined);
      if (p.found && p.鍮꾩슜 != null) {
        setForm((f) => ({ ...f, ?묒뾽: p.?묒뾽紐?|| f.?묒뾽, 鍮꾩슜: p.鍮꾩슜 as number }));
        setPriceHint(p.message);
      } else {
        setPriceHint(p.message);
      }
    } catch {
      setPriceHint('');
    }
  }

  async function searchBarcode(raw?: string) {
    const code = (raw ?? form.諛붿퐫??.trim();
    if (!code) {
      setLookupOk(false);
      setLookupHint('諛붿퐫?쒕? ?낅젰????寃?됲븯?몄슂.');
      return;
    }
    setLookingUp(true);
    setLookupHint('寃??以?..');
    setLookupOk(false);
    try {
      const found = await lookupRepairBarcode(code);
      const vendorName = found.?낆껜紐?|| form.?낆껜紐?
      setForm((f) => ({
        ...f,
        諛붿퐫?? found.諛붿퐫??|| code,
        ?낆껜紐? found.?낆껜紐?|| f.?낆껜紐?
        ?쒗뭹紐? found.?쒗뭹紐?|| f.?쒗뭹紐?
        ?듭뀡: found.?듭뀡 || f.?듭뀡,
      }));
      const extra = [found.?곹뭹肄붾뱶 && `肄붾뱶 ${found.?곹뭹肄붾뱶}`, found.濡쒖??댁뀡 && `濡쒖??댁뀡 ${found.濡쒖??댁뀡}`]
        .filter(Boolean)
        .join(' 쨌 ');
      setLookupOk(true);
      setLookupHint(
        `?깅줉 ?뺣낫 ?낅젰?? ${found.?낆껜紐? / ${found.?쒗뭹紐?${found.?듭뀡 ? ` / ${found.?듭뀡}` : ''}${extra ? ` (${extra})` : ''}`
      );
      if (form.?묒뾽) fillPrice(form.?묒뾽, vendorName, found.?쒗뭹紐?|| form.?쒗뭹紐?;
    } catch {
      setLookupOk(false);
      setLookupHint('誘몃벑濡?諛붿퐫?쒖엯?덈떎. ?낆껜紐끒룹젣?덈챸??吏곸젒 ?낅젰?섏꽭??');
    } finally {
      setLookingUp(false);
    }
  }

  async function save() {
    if (!form.?묒뾽.trim() || !form.鍮꾩슜) {
      onMessage({ type: 'error', text: '?묒뾽怨?鍮꾩슜? ?꾩닔?낅땲??' });
      return;
    }
    if (!form.諛붿퐫??trim() && (!form.?낆껜紐?trim() || !form.?쒗뭹紐?trim())) {
      onMessage({ type: 'error', text: '諛붿퐫???먮뒗 ?낆껜紐??쒗뭹紐낆쓣 ?낅젰?섏꽭??' });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ?좎쭨: form.?좎쭨,
        諛붿퐫?? form.諛붿퐫??trim() || undefined,
        ?낆껜紐? form.?낆껜紐?trim() || undefined,
        ?쒗뭹紐? form.?쒗뭹紐?trim() || undefined,
        ?듭뀡: form.?듭뀡.trim() || undefined,
        遺덈웾紐? form.遺덈웾紐?trim() || undefined,
        ?묒뾽: form.?묒뾽.trim(),
        ?섎웾: Number(form.?섎웾) || 1,
        鍮꾩슜: Number(form.鍮꾩슜) || 0,
        鍮꾧퀬: form.鍮꾧퀬.trim() || undefined,
        異쒖쿂: 'manual',
      };
      let id = initial?.id;
      if (initial) {
        await updateRepairLog(initial.id, payload);
        onMessage({ type: 'success', text: '?섏꽑?쇱?媛 ?섏젙?섏뿀?듬땲??' });
      } else {
        const created = await createRepairLog(payload);
        id = created.id;
        onMessage({ type: 'success', text: '?섏꽑?쇱?媛 異붽??섏뿀?듬땲??' });
      }
      if (id && (beforeFile || afterFile || extraFiles.length)) {
        await uploadRepairPhotos(id, { before: beforeFile, after: afterFile, extra: extraFiles });
      }
      onSaved();
    } catch (e) {
      onMessage({ type: 'error', text: e instanceof Error ? e.message : '????ㅽ뙣' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose} maxWidth={860}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem 1.25rem' }}>
        <Field label="?좎쭨 *">
          <input type="date" value={form.?좎쭨} onChange={(e) => setForm({ ...form, ?좎쭨: e.target.value })} style={inputStyle} />
        </Field>
        <Field label="諛붿퐫??>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={form.諛붿퐫??
              onChange={(e) => { setForm({ ...form, 諛붿퐫?? e.target.value }); setLookupHint(''); setLookupOk(false); }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  searchBarcode(e.currentTarget.value);
                }
              }}
              placeholder="諛붿퐫???낅젰 ??寃??
              style={inputStyle}
            />
            <button
              type="button"
              onClick={() => searchBarcode()}
              disabled={lookingUp}
              style={{ ...btn('#0f766e'), whiteSpace: 'nowrap', opacity: lookingUp ? 0.7 : 1 }}
            >
              {lookingUp ? '寃??以?..' : '寃??}
            </button>
          </div>
          {lookupHint && (
            <p style={{ fontSize: '0.8rem', color: lookupOk ? '#16a34a' : '#b45309', margin: '0.25rem 0 0' }}>
              {lookupHint}
            </p>
          )}
        </Field>
        <Field label="?낆껜紐?>
          <input
            value={form.?낆껜紐?
            onChange={(e) => setForm({ ...form, ?낆껜紐? e.target.value })}
            onBlur={() => { if (form.?묒뾽) fillPrice(form.?묒뾽, form.?낆껜紐? form.?쒗뭹紐?; }}
            style={inputStyle}
          />
        </Field>
        <Field label="?쒗뭹紐?>
          <input
            value={form.?쒗뭹紐?
            onChange={(e) => setForm({ ...form, ?쒗뭹紐? e.target.value })}
            onBlur={() => { if (form.?묒뾽) fillPrice(form.?묒뾽, form.?낆껜紐? form.?쒗뭹紐?; }}
            style={inputStyle}
          />
        </Field>
        <Field label="?듭뀡">
          <input value={form.?듭뀡} onChange={(e) => setForm({ ...form, ?듭뀡: e.target.value })} placeholder="釉붾옓" style={inputStyle} />
        </Field>
        <Field label="遺덈웾紐?>
          <select
            value={customDefect ? '__custom__' : form.遺덈웾紐?
            onChange={(e) => {
              if (e.target.value === '__custom__') {
                setCustomDefect(true);
                setForm({ ...form, 遺덈웾紐? '' });
              } else {
                setCustomDefect(false);
                setForm({ ...form, 遺덈웾紐? e.target.value });
              }
            }}
            style={inputStyle}
          >
            <option value="">?좏깮</option>
            {defects.map((d) => <option key={d.遺덈웾紐? value={d.遺덈웾紐?>{d.遺덈웾紐?{d.蹂꾩묶 ? ` (${d.蹂꾩묶})` : ''}</option>)}
            <option value="__custom__">吏곸젒 ?낅젰</option>
          </select>
          {customDefect && (
            <input
              value={form.遺덈웾紐?
              onChange={(e) => setForm({ ...form, 遺덈웾紐? e.target.value })}
              placeholder="??遺덈웾紐?
              style={{ ...inputStyle, marginTop: 6 }}
            />
          )}
        </Field>
        <Field label="?묒뾽 *">
          <select
            value={customWork ? '__custom__' : form.?묒뾽}
            onChange={(e) => {
              if (e.target.value === '__custom__') {
                setCustomWork(true);
                setForm({ ...form, ?묒뾽: '' });
                setPriceHint('');
              } else {
                setCustomWork(false);
                setForm({ ...form, ?묒뾽: e.target.value });
                fillPrice(e.target.value, form.?낆껜紐? form.?쒗뭹紐?;
              }
            }}
            style={inputStyle}
          >
            <option value="">?좏깮</option>
            {workTypes.map((t) => <option key={t.?묒뾽紐? value={t.?묒뾽紐?>{t.?묒뾽紐? ({t.湲곕낯鍮꾩슜.toLocaleString()}??</option>)}
            <option value="__custom__">吏곸젒 ?낅젰</option>
          </select>
          {customWork && (
            <input
              value={form.?묒뾽}
              onChange={(e) => setForm({ ...form, ?묒뾽: e.target.value })}
              onBlur={() => { if (form.?묒뾽) fillPrice(form.?묒뾽, form.?낆껜紐? form.?쒗뭹紐?; }}
              placeholder="???묒뾽紐?
              style={{ ...inputStyle, marginTop: 6 }}
            />
          )}
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <Field label="?섎웾">
            <input type="number" min={1} value={form.?섎웾} onChange={(e) => setForm({ ...form, ?섎웾: Number(e.target.value) })} style={inputStyle} />
          </Field>
          <Field label="鍮꾩슜 *">
            <input type="number" min={0} value={form.鍮꾩슜} onChange={(e) => { setForm({ ...form, 鍮꾩슜: Number(e.target.value) }); setPriceHint(''); }} style={inputStyle} />
          </Field>
        </div>
        {priceHint && <p style={{ gridColumn: '1 / -1', fontSize: '0.8rem', color: '#2563eb', margin: 0 }}>{priceHint}</p>}
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="鍮꾧퀬">
            <input value={form.鍮꾧퀬} onChange={(e) => setForm({ ...form, 鍮꾧퀬: e.target.value })} style={inputStyle} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, minWidth: 0 }}>
          <Field label="?ъ쭊 1">
            <input type="file" accept="image/*" onChange={(e) => setBeforeFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
          <Field label="?ъ쭊 2">
            <input type="file" accept="image/*" onChange={(e) => setAfterFile(e.target.files?.[0] || null)} style={{ width: '100%', maxWidth: '100%' }} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="異붽? ?ъ쭊 (?щ윭 ??">
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
            <PhotoThumb filename={initial.before_image} label="?ъ쭊1" onClick={() => {}} />
            <PhotoThumb filename={initial.after_image} label="?ъ쭊2" onClick={() => {}} />
            {(initial.extra_images || []).map((fn, i) => (
              <PhotoThumb key={`${fn}-${i}`} filename={fn} label={`異붽?${i + 1}`} onClick={() => {}} />
            ))}
          </div>
        )}
        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
          <button onClick={onClose} style={btn('#6b7280')}>痍⑥냼</button>
          <button onClick={save} disabled={saving} style={btn('#2563eb')}>{saving ? '???以?..' : '???}</button>
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
    <Modal title="?뺤씤" onClose={onCancel}>
      <p style={{ marginBottom: 16 }}>{text}</p>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button onClick={onCancel} style={btn('#6b7280')}>痍⑥냼</button>
        <button onClick={onConfirm} style={btn('#ef4444')}>??젣</button>
      </div>
    </Modal>
  );
}
