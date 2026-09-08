'use client';

import { useEffect, useRef, useState } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import {
  getRepairBarcodes,
  createRepairBarcode,
  updateRepairBarcode,
  deleteRepairBarcode,
  uploadRepairBarcodes,
  getRepairBarcodeTemplateUrl,
  getRepairCatalog,
  saveRepairWorkType,
  deleteRepairWorkType,
  saveRepairDefect,
  deleteRepairDefect,
  getVendorAliases,
  upsertVendorAlias,
  deleteVendorAlias,
  listInboundVendors,
  ocrPreview,
  OcrPreviewItem,
  OcrPreviewReceipt,
  RepairBarcode,
  RepairWorkType,
  RepairDefect,
  VendorAlias,
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  );
}

function Modal({ title, onClose, children, maxWidth = 400 }: {
  title: string; onClose: () => void; children: React.ReactNode; maxWidth?: number;
}) {
  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: 8, maxWidth, width: '92%' }}>
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

// ─── 업체명 멀티셀렉 컴포넌트 ────────────────────────────────────────
function VendorMultiSelect({
  selected,
  onChange,
  options,
  placeholder,
}: {
  selected: string[];
  onChange: (v: string[]) => void;
  options: string[];
  placeholder?: string;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  const filtered = options.filter(
    (o) => !selected.includes(o) && o.toLowerCase().includes(query.toLowerCase()),
  );
  // 직접 입력(DB에 없는 이름)도 추가 가능
  const canAddCustom = query.trim() && !selected.includes(query.trim()) && !options.includes(query.trim());

  function add(v: string) {
    onChange([...selected, v]);
    setQuery('');
  }
  function remove(v: string) {
    onChange(selected.filter((x) => x !== v));
  }

  const containerStyle: React.CSSProperties = {
    border: '1px solid #ddd',
    borderRadius: 4,
    padding: '4px 6px',
    minHeight: 40,
    cursor: 'text',
    backgroundColor: '#fff',
    position: 'relative',
  };
  const tagStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    background: '#ede9fe', color: '#7c3aed',
    borderRadius: 12, padding: '2px 8px', fontSize: '0.8rem', fontWeight: 500,
    margin: '2px',
  };
  const dropStyle: React.CSSProperties = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 999,
    background: '#fff', border: '1px solid #ddd', borderRadius: 4,
    maxHeight: 220, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
    marginTop: 2,
  };
  const optStyle = (hover: boolean): React.CSSProperties => ({
    padding: '0.45rem 0.75rem', cursor: 'pointer', fontSize: '0.875rem',
    backgroundColor: hover ? '#f3f0ff' : 'transparent',
    borderBottom: '1px solid #f5f5f5',
  });

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <div style={containerStyle} onClick={() => { setOpen(true); }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
          {selected.map((v) => (
            <span key={v} style={tagStyle}>
              {v}
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); remove(v); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', padding: 0, lineHeight: 1, fontSize: '0.9rem' }}
              >×</button>
            </span>
          ))}
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && query.trim()) { e.preventDefault(); add(query.trim()); }
              if (e.key === 'Backspace' && !query && selected.length > 0) remove(selected[selected.length - 1]);
            }}
            placeholder={selected.length === 0 ? (placeholder ?? '업체명 검색 또는 입력…') : ''}
            style={{ border: 'none', outline: 'none', flex: 1, minWidth: 120, fontSize: '0.875rem', padding: '2px 4px' }}
          />
        </div>
      </div>
      {open && (filtered.length > 0 || canAddCustom) && (
        <div style={dropStyle}>
          {filtered.map((o) => (
            <HoverItem key={o} label={o} onSelect={() => add(o)} style={optStyle} />
          ))}
          {canAddCustom && (
            <HoverItem
              label={`+ "${query.trim()}" 직접 추가`}
              onSelect={() => add(query.trim())}
              style={(h) => ({ ...optStyle(h), color: '#2563eb', fontStyle: 'italic' })}
            />
          )}
        </div>
      )}
    </div>
  );
}

function HoverItem({ label, onSelect, style }: {
  label: string;
  onSelect: () => void;
  style: (hover: boolean) => React.CSSProperties;
}) {
  const [hover, setHover] = useState(false);
  return (
    <div
      style={style(hover)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onMouseDown={(e) => { e.preventDefault(); onSelect(); }}
    >{label}</div>
  );
}

// ─── 바코드 등록 탭 ───────────────────────────────────────────────
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
  const emptyForm = { 바코드: '', 업체명: '', 제품명: '', 옵션: '', 도매처: '', 상품코드: '', 로케이션: '', 상품명: '' };
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
          도매처: form.도매처,
          상품코드: form.상품코드, 로케이션: form.로케이션, 상품명: form.상품명,
        });
        onMessage({ type: 'success', text: '바코드가 수정되었습니다.' });
      } else {
        await createRepairBarcode({
          바코드: form.바코드.trim(),
          업체명: form.업체명.trim(),
          제품명: form.제품명.trim(),
          옵션: form.옵션 || undefined,
          도매처: form.도매처 || undefined,
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
          <Field label="도매처">
            <input value={form.도매처} onChange={(e) => setForm({ ...form, 도매처: e.target.value })} style={inputStyle} placeholder="줄리" />
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
                    {['바코드', '업체명', '도매처', '제품명', '옵션', '상품코드', '로케이션', '출처', ''].map((h) => (
                      <th key={h} style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((row) => (
                    <tr key={row.바코드} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{row.바코드}</td>
                      <td style={{ padding: '0.5rem' }}>{row.업체명}</td>
                      <td style={{ padding: '0.5rem', color: '#7c3aed' }}>{row.도매처 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.제품명}</td>
                      <td style={{ padding: '0.5rem' }}>{row.옵션 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.상품코드 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.로케이션 || '-'}</td>
                      <td style={{ padding: '0.5rem' }}>{row.출처 || '-'}</td>
                      <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                        <button onClick={() => {
                          setEditing(row);
                          setForm({ 바코드: row.바코드, 업체명: row.업체명, 제품명: row.제품명, 옵션: row.옵션 || '', 도매처: row.도매처 || '', 상품코드: row.상품코드 || '', 로케이션: row.로케이션 || '', 상품명: row.상품명 || '' });
                        }} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
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

// ─── 작업/불량 설정 탭 ────────────────────────────────────────────
// ─────────────────────────────────────
// 화주사 별칭 관리 탭
// ─────────────────────────────────────

function VendorAliasTab({ onMessage }: { onMessage: (m: { type: 'success' | 'error'; text: string } | null) => void }) {
  const [token, setToken] = useState('');
  const [aliases, setAliases] = useState<VendorAlias[]>([]);
  const [loading, setLoading] = useState(true);
  const [vendorOptions, setVendorOptions] = useState<string[]>([]);
  const [editing, setEditing] = useState<VendorAlias | null>(null);
  const [newCanonical, setNewCanonical] = useState('');
  const [newSelectedVendors, setNewSelectedVendors] = useState<string[]>([]);
  const [newMemo, setNewMemo] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    setToken(tok);
    if (tok) {
      load(tok);
      loadVendorOptions(tok);
    }
  }, []);

  async function load(tok: string) {
    setLoading(true);
    try {
      const r = await getVendorAliases(tok);
      setAliases(r.aliases);
    } catch {
      onMessage({ type: 'error', text: '별칭 목록 불러오기 실패' });
    } finally {
      setLoading(false);
    }
  }

  async function loadVendorOptions(tok: string) {
    try {
      const r = await listInboundVendors(tok);
      setVendorOptions(r.registered.map((v) => v.name));
    } catch {
      // 실패해도 직접 입력 가능
    }
  }

  async function handleSave(canonical: string, vendors: string[], memo: string) {
    if (!canonical.trim()) { onMessage({ type: 'error', text: '별칭명을 입력하세요.' }); return; }
    setSaving(true);
    try {
      await upsertVendorAlias(token, canonical, vendors, memo || undefined);
      onMessage({ type: 'success', text: `"${canonical}" 별칭 저장됨` });
      setEditing(null);
      setNewCanonical(''); setNewSelectedVendors([]); setNewMemo('');
      load(token);
    } catch {
      onMessage({ type: 'error', text: '저장 실패' });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(canonical: string) {
    if (!confirm(`"${canonical}" 별칭을 삭제할까요?`)) return;
    try {
      await deleteVendorAlias(token, canonical);
      onMessage({ type: 'success', text: '삭제됨' });
      load(token);
    } catch {
      onMessage({ type: 'error', text: '삭제 실패' });
    }
  }

  const thStyle: React.CSSProperties = {
    padding: '0.5rem 0.75rem', textAlign: 'left',
    borderBottom: '2px solid #e5e7eb', fontSize: '0.82rem',
    color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap',
  };
  const tdStyle: React.CSSProperties = {
    padding: '0.6rem 0.75rem', borderBottom: '1px solid #f3f4f6',
    fontSize: '0.875rem', verticalAlign: 'middle',
  };

  return (
    <div>
      {/* 설명 */}
      <Card title="화주사 별칭이란?">
        <p style={{ fontSize: '0.875rem', color: '#374151', lineHeight: 1.7, margin: 0 }}>
          <strong>별칭명</strong>을 만들고, 그 별칭에 포함할 <strong>업체명</strong>을 선택해서 묶어 등록합니다.<br />
          예: 별칭 <code>베으그룹</code> → 업체명 <code>자체제작_베으</code>, <code>베으샵</code>, <code>BEEU공식</code><br />
          하나의 별칭에 여러 업체를 담을 수 있으며, 입고 OCR 매칭 시 별칭 → 소속 업체 전체를 검색합니다.
        </p>
      </Card>

      {/* 신규 등록 폼 */}
      <Card title="+ 별칭 새로 등록">
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 180px auto', gap: 12, alignItems: 'end' }}>
          <Field label="별칭명 *">
            <input
              value={newCanonical}
              onChange={e => setNewCanonical(e.target.value)}
              placeholder="예) 베으그룹"
              style={inputStyle}
            />
          </Field>
          <Field label="포함 업체명 (DB에서 선택하거나 직접 입력)">
            <VendorMultiSelect
              selected={newSelectedVendors}
              onChange={setNewSelectedVendors}
              options={vendorOptions}
              placeholder="업체명 검색 또는 입력…"
            />
          </Field>
          <Field label="메모">
            <input
              value={newMemo}
              onChange={e => setNewMemo(e.target.value)}
              placeholder="선택 메모"
              style={inputStyle}
            />
          </Field>
          <button
            onClick={() => handleSave(newCanonical.trim(), newSelectedVendors, newMemo)}
            disabled={saving || !newCanonical.trim()}
            style={{ ...btn('#2563eb'), opacity: (saving || !newCanonical.trim()) ? 0.5 : 1, whiteSpace: 'nowrap' }}
          >
            {saving ? '저장 중…' : '등록'}
          </button>
        </div>
      </Card>

      {/* 목록 */}
      <Card title="등록된 별칭 목록">
        {loading ? <Loading /> : aliases.length === 0 ? (
          <p style={{ color: '#9ca3af', fontSize: '0.875rem' }}>등록된 별칭이 없습니다. 위에서 추가하세요.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ background: '#f9fafb' }}>
                  <th style={thStyle}>별칭명</th>
                  <th style={thStyle}>포함 업체명</th>
                  <th style={thStyle}>메모</th>
                  <th style={thStyle}></th>
                </tr>
              </thead>
              <tbody>
                {aliases.map(a => (
                  <tr key={a.canonical}>
                    <td style={{ ...tdStyle, fontWeight: 700, color: '#1d4ed8', whiteSpace: 'nowrap' }}>{a.canonical}</td>
                    <td style={tdStyle}>
                      {a.aliases.length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {a.aliases.map(al => (
                            <span key={al} style={{
                              background: '#ede9fe', color: '#7c3aed',
                              borderRadius: 12, padding: '2px 10px', fontSize: '0.78rem', fontWeight: 500,
                            }}>{al}</span>
                          ))}
                        </div>
                      ) : <span style={{ color: '#9ca3af' }}>업체 없음</span>}
                    </td>
                    <td style={{ ...tdStyle, color: '#6b7280' }}>{a.memo || '-'}</td>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                      <button
                        onClick={() => setEditing({ ...a })}
                        style={{ ...btn('#6b7280'), padding: '0.25rem 0.6rem', fontSize: '0.78rem', marginRight: 4 }}
                      >수정</button>
                      <button
                        onClick={() => handleDelete(a.canonical)}
                        style={{ ...btn('#dc2626'), padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
                      >삭제</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 수정 모달 */}
      {editing && (
        <EditAliasModal
          initial={editing}
          vendorOptions={vendorOptions}
          saving={saving}
          onClose={() => setEditing(null)}
          onSave={(vendors, memo) => handleSave(editing.canonical, vendors, memo)}
        />
      )}
    </div>
  );
}

function EditAliasModal({ initial, vendorOptions, saving, onClose, onSave }: {
  initial: VendorAlias;
  vendorOptions: string[];
  saving: boolean;
  onClose: () => void;
  onSave: (vendors: string[], memo: string) => void;
}) {
  const [selectedVendors, setSelectedVendors] = useState<string[]>(initial.aliases);
  const [memo, setMemo] = useState(initial.memo || '');

  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, zIndex: 500,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'rgba(0,0,0,0.45)',
  };
  const box: React.CSSProperties = {
    background: '#fff', borderRadius: 10, padding: '1.5rem',
    width: 520, maxWidth: '96vw', boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
  };

  return (
    <div style={overlay} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={box} onMouseDown={e => e.stopPropagation()}>
        <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '1rem' }}>
          ✎ &quot;{initial.canonical}&quot; 포함 업체 수정
        </div>
        <Field label="포함 업체명 (DB에서 선택하거나 직접 입력)">
          <VendorMultiSelect
            selected={selectedVendors}
            onChange={setSelectedVendors}
            options={vendorOptions}
            placeholder="업체명 검색 또는 입력…"
          />
        </Field>
        <div style={{ marginTop: 10 }}>
          <Field label="메모">
            <input value={memo} onChange={e => setMemo(e.target.value)} style={inputStyle} />
          </Field>
        </div>
        <div style={{ fontSize: '0.78rem', color: '#9ca3af', marginTop: 8 }}>
          별칭 <strong>{initial.canonical}</strong>으로 입고 시 위에 선택된 업체들의 바코드 전체를 매칭합니다.
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button onClick={onClose} style={{ ...btn('#9ca3af') }}>취소</button>
          <button
            onClick={() => onSave(selectedVendors, memo)}
            disabled={saving}
            style={{ ...btn('#2563eb'), opacity: saving ? 0.6 : 1 }}
          >{saving ? '저장 중…' : '저장'}</button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 작업/불량 설정 탭
// ─────────────────────────────────────

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
    if (!workForm.작업명.trim()) { onMessage({ type: 'error', text: '작업명은 필수입니다.' }); return; }
    try {
      await saveRepairWorkType({ 작업명: workForm.작업명.trim(), 기본비용: Number(workForm.기본비용) || 0, 별칭: workForm.별칭.trim() || undefined });
      onMessage({ type: 'success', text: editingWork ? '작업이 수정되었습니다.' : '작업이 추가되었습니다.' });
      setWorkForm(emptyWork); setEditingWork(null); load();
    } catch (e) { onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' }); }
  }

  async function saveDefect() {
    if (!defectForm.불량명.trim()) { onMessage({ type: 'error', text: '불량명은 필수입니다.' }); return; }
    try {
      await saveRepairDefect({ 불량명: defectForm.불량명.trim(), 별칭: defectForm.별칭.trim() || undefined });
      onMessage({ type: 'success', text: editingDefect ? '불량명이 수정되었습니다.' : '불량명이 추가되었습니다.' });
      setDefectForm(emptyDefect); setEditingDefect(null); load();
    } catch (e) { onMessage({ type: 'error', text: e instanceof Error ? e.message : '저장 실패' }); }
  }

  return (
    <>
      <Card title="작업 설정">
        <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: 12 }}>봇·웹 수동 입력이 같은 목록을 씁니다. 별칭은 쉼표로 구분합니다. 예: 바느질,바느질작업</p>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 2fr auto auto', gap: 8, alignItems: 'end', marginBottom: 16 }}>
          <Field label="작업명 *">
            <input value={workForm.작업명} disabled={!!editingWork} onChange={(e) => setWorkForm({ ...workForm, 작업명: e.target.value })} placeholder="스팀작업" style={inputStyle} />
          </Field>
          <Field label="기본비용 *">
            <input type="number" min={0} value={workForm.기본비용} onChange={(e) => setWorkForm({ ...workForm, 기본비용: Number(e.target.value) })} style={inputStyle} />
          </Field>
          <Field label="별칭">
            <input value={workForm.별칭} onChange={(e) => setWorkForm({ ...workForm, 별칭: e.target.value })} placeholder="스팀" style={inputStyle} />
          </Field>
          <button onClick={saveWork} style={btn('#2563eb')}>{editingWork ? '수정 저장' : '추가'}</button>
          {editingWork && <button onClick={() => { setEditingWork(null); setWorkForm(emptyWork); }} style={btn('#6b7280')}>취소</button>}
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
                      <button onClick={() => { setEditingWork(w.작업명); setWorkForm({ 작업명: w.작업명, 기본비용: w.기본비용, 별칭: w.별칭 || '' }); }} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
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
          <p style={{ fontSize: '0.8rem', color: '#666', marginBottom: 12 }}>채팅에서 구멍수선처럼 별칭이 와도 마스터 불량명으로 맞춥니다.</p>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr auto auto', gap: 8, alignItems: 'end', marginBottom: 16 }}>
            <Field label="불량명 *">
              <input value={defectForm.불량명} disabled={!!editingDefect} onChange={(e) => setDefectForm({ ...defectForm, 불량명: e.target.value })} placeholder="구멍" style={inputStyle} />
            </Field>
            <Field label="별칭">
              <input value={defectForm.별칭} onChange={(e) => setDefectForm({ ...defectForm, 별칭: e.target.value })} placeholder="구멍수선" style={inputStyle} />
            </Field>
            <button onClick={saveDefect} style={btn('#2563eb')}>{editingDefect ? '수정 저장' : '추가'}</button>
            {editingDefect && <button onClick={() => { setEditingDefect(null); setDefectForm(emptyDefect); }} style={btn('#6b7280')}>취소</button>}
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
                        <button onClick={() => { setEditingDefect(d.불량명); setDefectForm({ 불량명: d.불량명, 별칭: d.별칭 || '' }); }} style={{ ...btn('#3b82f6'), padding: '0.25rem 0.5rem', fontSize: '0.75rem', marginRight: 4 }}>수정</button>
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
              setDeletingWork(null); load();
            } catch (e) { onMessage({ type: 'error', text: e instanceof Error ? e.message : '삭제 실패' }); }
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
              setDeletingDefect(null); load();
            } catch (e) { onMessage({ type: 'error', text: e instanceof Error ? e.message : '삭제 실패' }); }
          }}
        />
      )}
    </>
  );
}

// ─────────────────────────────────────
// OCR 테스트 탭
// ─────────────────────────────────────

function OcrTestTab() {
  const [token, setToken] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ receipt: OcrPreviewReceipt; items: OcrPreviewItem[] } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setToken(localStorage.getItem('token') || '');
  }, []);

  function handleFile(f: File) {
    setFile(f);
    setResult(null);
    setError('');
    const reader = new FileReader();
    reader.onload = e => setPreview(e.target?.result as string);
    reader.readAsDataURL(f);
  }

  async function handleAnalyze() {
    if (!file || !token) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const r = await ocrPreview(token, file);
      setResult({ receipt: r.receipt, items: r.items });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'GPT 분석 실패');
    } finally {
      setLoading(false);
    }
  }

  const confColor = (c: number) => c >= 0.9 ? '#15803d' : c >= 0.7 ? '#a16207' : '#dc2626';
  const confLabel = (c: number) => `${Math.round(c * 100)}%`;

  return (
    <div>
      <Card title="GPT 장끼 분석 테스트">
        <p style={{ fontSize: '0.85rem', color: '#6b7280', marginBottom: 12 }}>
          장끼(영수증) 사진을 올리면 GPT-4o가 품목을 읽어 결과를 보여줍니다. DB에 저장하지 않습니다.
        </p>

        {/* 파일 선택 */}
        <label style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '0.75rem 1rem', border: '2px dashed #d1d5db', borderRadius: 8,
          cursor: loading ? 'not-allowed' : 'pointer', backgroundColor: '#f9fafb', marginBottom: 12,
        }}>
          <span style={{ fontSize: '1.5rem' }}>📷</span>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
              {file ? file.name : '장끼 사진 선택 (클릭 또는 드래그)'}
            </div>
            {file && <div style={{ fontSize: '0.78rem', color: '#9ca3af' }}>{(file.size / 1024).toFixed(0)} KB</div>}
          </div>
          <input
            type="file" accept="image/*" style={{ display: 'none' }} disabled={loading}
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
        </label>

        {/* 미리보기 이미지 */}
        {preview && (
          <div style={{ marginBottom: 12 }}>
            <img src={preview} alt="미리보기" style={{ maxWidth: '100%', maxHeight: 280, borderRadius: 8, border: '1px solid #e5e7eb', objectFit: 'contain' }} />
          </div>
        )}

        <button
          onClick={handleAnalyze}
          disabled={!file || loading}
          style={{
            ...btn('#7c3aed'),
            opacity: (!file || loading) ? 0.5 : 1,
            fontSize: '1rem',
            padding: '0.65rem 1.5rem',
          }}
        >
          {loading ? '⏳ GPT 분석 중… (10~40초)' : '🤖 GPT로 분석하기'}
        </button>
      </Card>

      {/* 오류 */}
      {error && (
        <div style={{ marginTop: 12, padding: '0.75rem 1rem', borderRadius: 8, background: '#fee2e2', color: '#991b1b', fontSize: '0.875rem' }}>
          ❌ {error}
        </div>
      )}

      {/* 결과 */}
      {result && (
        <>
          {/* 영수증 정보 */}
          <Card title="📋 영수증 정보">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, fontSize: '0.875rem' }}>
              {[
                ['거래처명', result.receipt.storeName ?? '인식 불가'],
                ['영수증번호', result.receipt.receiptNo ?? '-'],
                ['날짜', result.receipt.orderDate ?? '-'],
                ['합계금액', result.receipt.totalAmount != null ? result.receipt.totalAmount.toLocaleString() + '원' : '-'],
                ['수기여부', result.receipt.isHandwritten ? '✋ 수기' : '🖨 인쇄'],
                ['신뢰도', confLabel(result.receipt.confidence)],
              ].map(([label, value]) => (
                <div key={label} style={{ background: '#f9fafb', padding: '0.5rem 0.75rem', borderRadius: 6 }}>
                  <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginBottom: 2 }}>{label}</div>
                  <div style={{ fontWeight: 600 }}>{value}</div>
                </div>
              ))}
            </div>
            {result.receipt.warnings?.length > 0 && (
              <div style={{ marginTop: 8, fontSize: '0.8rem', color: '#a16207' }}>
                ⚠️ {result.receipt.warnings.join(' / ')}
              </div>
            )}
            {result.receipt.needsReview && (
              <div style={{ marginTop: 6, fontSize: '0.8rem', color: '#dc2626', fontWeight: 600 }}>
                🔴 검토 필요 — 신뢰도가 낮거나 필수값이 없습니다.
              </div>
            )}
          </Card>

          {/* 품목 목록 */}
          <Card title={`📦 인식된 품목 (${result.items.length}개)`}>
            {result.items.length === 0 ? (
              <p style={{ color: '#9ca3af', fontSize: '0.875rem' }}>인식된 품목이 없습니다.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr style={{ background: '#f9fafb' }}>
                      {['#', '품명', '색상/옵션', '단가', '수량', '금액', '신뢰도', '검토'].map(h => (
                        <th key={h} style={{ padding: '0.5rem 0.6rem', textAlign: 'left', borderBottom: '2px solid #e5e7eb', fontSize: '0.8rem', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map(item => (
                      <tr key={item.lineNo} style={{ borderBottom: '1px solid #f3f4f6', background: item.needsReview ? '#fffbeb' : 'transparent' }}>
                        <td style={{ padding: '0.5rem 0.6rem', color: '#9ca3af' }}>{item.lineNo}</td>
                        <td style={{ padding: '0.5rem 0.6rem', fontWeight: 600 }}>{item.itemName || '-'}</td>
                        <td style={{ padding: '0.5rem 0.6rem', color: '#7c3aed' }}>{[item.color, item.optionText].filter(Boolean).join(' / ') || '-'}</td>
                        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right' }}>{item.unitPrice != null ? item.unitPrice.toLocaleString() : '-'}</td>
                        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'center', fontWeight: 700 }}>{item.quantity ?? '-'}</td>
                        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right' }}>{item.amount != null ? item.amount.toLocaleString() : '-'}</td>
                        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'center' }}>
                          <span style={{ color: confColor(item.confidence), fontWeight: 600 }}>{confLabel(item.confidence)}</span>
                        </td>
                        <td style={{ padding: '0.5rem 0.6rem', textAlign: 'center' }}>
                          {item.needsReview
                            ? <span style={{ color: '#dc2626', fontSize: '0.78rem' }}>🔴 요망</span>
                            : <span style={{ color: '#15803d', fontSize: '0.78rem' }}>✅ OK</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

// ─── 메인 페이지 ──────────────────────────────────────────────────
export default function JournalSettingsPage() {
  const [tab, setTab] = useState<'barcodes' | 'catalog' | 'vendor-aliases' | 'ocr-test'>('barcodes');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const tabs: [string, string][] = [
    ['barcodes', '바코드 등록'],
    ['catalog', '작업/불량 설정'],
    ['vendor-aliases', '화주사 별칭 관리'],
    ['ocr-test', '🤖 OCR 정확도 테스트'],
  ];

  return (
    <div style={{ padding: '1rem', maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '1rem' }}>일지 설정</h1>

      {message && (
        <div style={{
          marginBottom: 12, padding: '0.75rem 1rem', borderRadius: 6,
          backgroundColor: message.type === 'success' ? '#dcfce7' : '#fee2e2',
          color: message.type === 'success' ? '#166534' : '#991b1b',
          fontSize: '0.9rem',
        }}>
          {message.text}
          <button onClick={() => setMessage(null)} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}>×</button>
        </div>
      )}

      {/* 탭 헤더 */}
      <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', marginBottom: '1rem' }}>
        {tabs.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key as typeof tab)}
            style={{
              padding: '0.6rem 1.2rem',
              background: 'none',
              border: 'none',
              borderBottom: tab === key ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              color: tab === key ? '#2563eb' : '#6b7280',
              fontWeight: tab === key ? 700 : 500,
              fontSize: '0.95rem',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: tab === 'barcodes' ? 'block' : 'none' }}>
        <BarcodesTab onMessage={setMessage} />
      </div>
      <div style={{ display: tab === 'catalog' ? 'block' : 'none' }}>
        <CatalogTab onMessage={setMessage} />
      </div>
      <div style={{ display: tab === 'vendor-aliases' ? 'block' : 'none' }}>
        <VendorAliasTab onMessage={setMessage} />
      </div>
      <div style={{ display: tab === 'ocr-test' ? 'block' : 'none' }}>
        <OcrTestTab />
      </div>
    </div>
  );
}
