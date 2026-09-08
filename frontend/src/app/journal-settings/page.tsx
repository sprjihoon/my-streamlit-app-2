'use client';

import { useEffect, useState } from 'react';
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

// ─── 메인 페이지 ──────────────────────────────────────────────────
export default function JournalSettingsPage() {
  const [tab, setTab] = useState<'barcodes' | 'catalog'>('barcodes');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const tabs: [string, string][] = [
    ['barcodes', '바코드 등록'],
    ['catalog', '작업/불량 설정'],
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
    </div>
  );
}
