'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { FilterBar, KpiStrip, TableSummary } from '@/components/data';
import { EmptyState } from '@/components/operational/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import PageHeader from '@/components/ui/page-header';
import { Select } from '@/components/ui/select';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ReceiptItem {
  id: string;
  line_no: number;
  raw_text: string | null;
  item_name: string | null;
  color: string | null;
  size: string | null;
  option_text: string | null;
  unit_price: number | null;
  quantity: number | null;
  amount: number | null;
  confidence: number;
  needs_review: boolean;
  warnings: string[];
}

interface Receipt {
  id: string;
  image_filename: string | null;
  store_name: string | null;
  receipt_type: string;
  receipt_no: string | null;
  order_date: string | null;
  phone: string | null;
  total_amount: number | null;
  bank_info: string | null;
  memo: string | null;
  is_handwritten: boolean;
  needs_review: boolean;
  warnings: string[];
  created_at: string;
  processor_name: string | null;
  items?: ReceiptItem[];
}

function fmtDatetime(dt: string) {
  if (!dt) return '-';
  const d = new Date(dt);
  if (isNaN(d.getTime())) return dt;
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function fmt(n: number | null | undefined) {
  if (n == null) return '-';
  return n.toLocaleString('ko-KR') + '원';
}

// ─────────────────────────────────────
// 업로드 드롭존
// ─────────────────────────────────────
function UploadZone({ onUpload }: { onUpload: (file: File) => void }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files[0];
    if (file) onUpload(file);
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${drag ? '#0d6efd' : '#dee2e6'}`,
        borderRadius: '12px',
        padding: '2.5rem',
        textAlign: 'center',
        cursor: 'pointer',
        backgroundColor: drag ? '#f0f6ff' : '#fafafa',
        transition: 'all 0.2s',
      }}
    >
      <input ref={inputRef} type="file" accept="image/*" style={{ display: 'none' }}
        onChange={e => { if (e.target.files?.[0]) onUpload(e.target.files[0]); }} />
      <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>📸</div>
      <p style={{ margin: 0, fontWeight: 600, color: '#495057' }}>
        장끼 / 영수증 사진을 여기에 드래그하거나 클릭하여 업로드
      </p>
      <p style={{ margin: '0.5rem 0 0', fontSize: '0.82rem', color: '#6c757d' }}>
        JPG, PNG, WEBP 지원 · GPT-4o Vision으로 자동 분석
      </p>
    </div>
  );
}

// ─────────────────────────────────────
// 품목 편집 행
// ─────────────────────────────────────
function ItemRow({
  item,
  onSave,
}: {
  item: ReceiptItem;
  onSave: (id: string, data: Partial<ReceiptItem>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ ...item });

  async function handleSave() {
    await onSave(item.id, {
      item_name: draft.item_name,
      color: draft.color,
      size: draft.size,
      option_text: draft.option_text,
      unit_price: draft.unit_price,
      quantity: draft.quantity,
      amount: draft.amount,
    });
    setEditing(false);
  }

  const needsReview = item.needs_review;
  const rowBg = needsReview ? '#fffbea' : 'white';

  if (editing) {
    const inp: React.CSSProperties = {
      width: '100%', padding: '0.3rem', border: '1px solid #dee2e6',
      borderRadius: '4px', fontSize: '0.82rem',
    };
    return (
      <tr>
        <td>
          <input style={inp} value={draft.item_name ?? ''} onChange={e => setDraft(d => ({ ...d, item_name: e.target.value }))} placeholder="품명" />
        </td>
        <td>
          <input style={inp} value={draft.option_text ?? ''} onChange={e => setDraft(d => ({ ...d, option_text: e.target.value }))} placeholder="옵션" />
        </td>
        <td>
          <input style={{ ...inp, width: '80px' }} type="number" value={draft.unit_price ?? ''} onChange={e => setDraft(d => ({ ...d, unit_price: e.target.value ? Number(e.target.value) : null }))} />
        </td>
        <td>
          <input style={{ ...inp, width: '60px' }} type="number" value={draft.quantity ?? ''} onChange={e => setDraft(d => ({ ...d, quantity: e.target.value ? Number(e.target.value) : null }))} />
        </td>
        <td>
          <input style={{ ...inp, width: '90px' }} type="number" value={draft.amount ?? ''} onChange={e => setDraft(d => ({ ...d, amount: e.target.value ? Number(e.target.value) : null }))} />
        </td>
        <td colSpan={2}>
          <button onClick={handleSave} style={{ padding: '0.3rem 0.7rem', backgroundColor: '#198754', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.78rem', marginRight: '4px' }}>저장</button>
          <button onClick={() => { setDraft({ ...item }); setEditing(false); }} style={{ padding: '0.3rem 0.6rem', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.78rem' }}>취소</button>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>
        {item.item_name || <span style={{ color: '#dc3545' }}>미추출</span>}
        {needsReview && <span style={{ marginLeft: '0.4rem', fontSize: '0.7rem', backgroundColor: '#fff3cd', color: '#856404', padding: '1px 5px', borderRadius: '3px' }}>확인필요</span>}
      </td>
      <td>
        {[item.option_text, item.color, item.size].filter(Boolean).join(' / ') || '-'}
      </td>
      <td className="cell-num">{fmt(item.unit_price)}</td>
      <td className="cell-num">{item.quantity ?? '-'}</td>
      <td className="cell-num">{fmt(item.amount)}</td>
      <td>
        {item.warnings.join(', ') || ''}
      </td>
      <td>
        <button onClick={() => setEditing(true)} style={{ padding: '0.2rem 0.6rem', backgroundColor: '#ff9800', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>수정</button>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────
// 영수증 상세 패널
// ─────────────────────────────────────
function ReceiptDetail({
  receipt,
  token,
  onClose,
  onDeleted,
  apiUrl,
}: {
  receipt: Receipt;
  token: string;
  onClose: () => void;
  onDeleted: () => void;
  apiUrl: string;
}) {
  const [detail, setDetail] = useState<Receipt>(receipt);
  const [saving, setSaving] = useState(false);

  const loadDetail = useCallback(async () => {
    const res = await fetch(`${apiUrl}/receipt/${receipt.id}?token=${token}`);
    if (res.ok) setDetail(await res.json());
  }, [receipt.id, token, apiUrl]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  async function handleItemSave(itemId: string, data: Partial<ReceiptItem>) {
    setSaving(true);
    try {
      await fetch(`${apiUrl}/receipt/items/${itemId}?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      await loadDetail();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm('이 영수증을 삭제하시겠습니까?')) return;
    await fetch(`${apiUrl}/receipt/${receipt.id}?token=${token}`, { method: 'DELETE' });
    onDeleted();
  }

  const totalCalc = (detail.items || []).reduce((s, i) => s + (i.amount || 0), 0);
  const hasReviewItems = (detail.items || []).some(i => i.needs_review);

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      zIndex: 1000, overflowY: 'auto', padding: '2rem 1rem',
    }} onClick={onClose}>
      <div style={{
        backgroundColor: 'white', borderRadius: '12px', width: '100%', maxWidth: '900px',
        padding: '2rem', boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
      }} onClick={e => e.stopPropagation()}>
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.2rem' }}>
              {detail.store_name || '(거래처 미추출)'}
              <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: '#6c757d', fontWeight: 400 }}>
                {detail.receipt_type}
              </span>
            </h3>
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem', color: '#6c757d' }}>
            {detail.order_date || '-'} {detail.phone ? `· ${detail.phone}` : ''}
          </p>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.78rem', color: '#adb5bd' }}>
            처리자: <strong style={{ color: '#495057' }}>{detail.processor_name || '-'}</strong>
            &nbsp;·&nbsp;처리시간: <strong style={{ color: '#495057' }}>{fmtDatetime(detail.created_at)}</strong>
          </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
            <a
              href={`${apiUrl}/receipt/${detail.id}/excel?token=${token}`}
              download
              style={{ padding: '0.4rem 0.9rem', backgroundColor: '#198754', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'none' }}
            >
              📥 엑셀
            </a>
            <button onClick={handleDelete} style={{ padding: '0.4rem 0.9rem', backgroundColor: '#dc3545', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}>삭제</button>
            <button onClick={onClose} style={{ padding: '0.4rem 0.9rem', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}>닫기</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          {/* 이미지 */}
          {detail.image_filename && (
            <div>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.8rem', color: '#6c757d', fontWeight: 600 }}>원본 이미지</p>
              <img
                src={`${apiUrl}/receipt/image/${detail.image_filename}?token=${token}`}
                alt="영수증"
                style={{ width: '100%', borderRadius: '8px', border: '1px solid #dee2e6', objectFit: 'contain', maxHeight: '400px' }}
              />
            </div>
          )}

          {/* 정보 */}
          <div>
            {/* 경고 */}
            {(detail.needs_review || hasReviewItems) && (
              <div style={{ padding: '0.75rem 1rem', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '8px', marginBottom: '1rem', fontSize: '0.85rem', color: '#856404' }}>
                ⚠️ 확인이 필요한 항목이 있습니다.
                {detail.warnings.length > 0 && (
                  <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem' }}>
                    {detail.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                )}
              </div>
            )}

            {/* 요약 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
              {[
                { label: '영수증 합계', value: fmt(detail.total_amount) },
                { label: '품목 합계 (계산)', value: fmt(totalCalc), highlight: detail.total_amount != null && Math.abs(totalCalc - detail.total_amount) > 1 },
                { label: '계좌 정보', value: detail.bank_info || '-' },
                { label: '메모', value: detail.memo || '-' },
              ].map(({ label, value, highlight }) => (
                <div key={label} style={{ padding: '0.6rem 0.75rem', backgroundColor: highlight ? '#fff3cd' : '#f8f9fa', borderRadius: '6px' }}>
                  <p style={{ margin: 0, fontSize: '0.75rem', color: '#6c757d' }}>{label}</p>
                  <p style={{ margin: '0.2rem 0 0', fontWeight: 600, fontSize: '0.9rem', color: highlight ? '#856404' : '#212529' }}>{value}</p>
                </div>
              ))}
            </div>

            {/* 수기 뱃지 */}
            {detail.is_handwritten && (
              <span style={{ padding: '0.3rem 0.75rem', backgroundColor: '#e2e3e5', color: '#41464b', borderRadius: '20px', fontSize: '0.78rem' }}>
                ✍️ 수기 영수증
              </span>
            )}
          </div>
        </div>

        {/* 품목 테이블 */}
        <div style={{ marginTop: '1.5rem' }}>
          <h4 style={{ margin: '0 0 0.75rem' }}>
            품목 목록 ({detail.items?.length || 0}개)
            {saving && <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: '#6c757d' }}>저장 중...</span>}
          </h4>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  {['품명', '옵션', '단가', '수량', '금액', '경고', ''].map(h => (
                    <th key={h} className="cell-num">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(detail.items || []).map(item => (
                  <ItemRow key={item.id} item={item} onSave={handleItemSave} />
                ))}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: '2px solid #dee2e6', backgroundColor: '#f8f9fa' }}>
                  <td colSpan={4} className="cell-num">합계</td>
                  <td className="cell-num">{fmt(totalCalc)}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────
export default function ReceiptsPage() {
  const [token, setToken] = useState('');
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [selected, setSelected] = useState<Receipt | null>(null);
  const [filterYear, setFilterYear] = useState(new Date().getFullYear());
  const [filterMonth, setFilterMonth] = useState(0); // 0 = 전체

  useEffect(() => {
    const t = localStorage.getItem('token') || '';
    setToken(t);
  }, []);

  const loadReceipts = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      let url = `${API_URL}/receipt/list?token=${token}&year=${filterYear}`;
      if (filterMonth) url += `&month=${filterMonth}`;
      const res = await fetch(url);
      if (res.ok) setReceipts(await res.json());
    } finally {
      setLoading(false);
    }
  }, [token, filterYear, filterMonth]);

  useEffect(() => { if (token) loadReceipts(); }, [token, loadReceipts]);

  async function handleUpload(file: File) {
    if (!token) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_URL}/receipt/upload?token=${token}`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '분석 실패');
      setUploadMsg({ text: `✅ 분석 완료! ${data.needs_review ? '확인 필요 항목이 있습니다.' : ''}`, ok: true });
      loadReceipts();
    } catch (err) {
      setUploadMsg({ text: `❌ ${err instanceof Error ? err.message : '오류'}`, ok: false });
    } finally {
      setUploading(false);
    }
  }

  const monthlyTotal = receipts.reduce((s, r) => s + (r.total_amount || 0), 0);
  const reviewCount = receipts.filter(r => r.needs_review).length;

  return (
    <div>
      <PageHeader
        title="영수증 처리"
        subtitle="장끼 / 영수증 사진을 업로드하면 GPT-4o Vision이 자동으로 분석합니다."
      />

      <Card>
        {uploading ? (
          <div className="tw-py-4 tw-text-center">
            <p className="tw-m-0 tw-font-semibold">GPT-4o Vision 분석 중...</p>
            <p className="caption tw-mt-1">잠시만 기다려주세요 (10~20초)</p>
          </div>
        ) : (
          <UploadZone onUpload={handleUpload} />
        )}
        {uploadMsg && (
          <Alert type={uploadMsg.ok ? 'success' : 'error'} message={uploadMsg.text} />
        )}
      </Card>

      <KpiStrip
        items={[
          { label: '이번 달 합계', value: `${monthlyTotal.toLocaleString('ko-KR')}원` },
          { label: '총 건수', value: `${receipts.length}건` },
          { label: '확인 필요', value: <span className={reviewCount > 0 ? 'tw-text-tillion-warning' : 'tw-text-tillion-success'}>{reviewCount}건</span> },
        ]}
      />

      <FilterBar
        trailing={
          <a
            className="btn btn-success"
            href={`${API_URL}/receipt/bulk-excel?token=${token}&year=${filterYear}${filterMonth ? `&month=${filterMonth}` : ''}`}
            download
          >
            엑셀 다운로드 ({receipts.length}건)
          </a>
        }
      >
        <Field label="연도">
          <Select value={filterYear} onChange={e => setFilterYear(Number(e.target.value))}>
            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>{y}년</option>)}
          </Select>
        </Field>
        <Field label="월">
          <Select value={filterMonth} onChange={e => setFilterMonth(Number(e.target.value))}>
            <option value={0}>전체 월</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
              <option key={m} value={m}>{m}월</option>
            ))}
          </Select>
        </Field>
      </FilterBar>
      <TableSummary>{receipts.length}건</TableSummary>

      {/* 목록 */}
      <Card>
        {loading ? (
          <p className="caption tw-py-6 tw-text-center">로딩 중...</p>
        ) : receipts.length === 0 ? (
          <EmptyState title="등록된 영수증이 없습니다." description="위에서 사진을 업로드해 보세요." />
        ) : (
          <table>
            <thead>
              <tr>
            {['거래처', '종류', '거래일', '금액', '처리자', '처리시간', '수기', '상태', ''].map(h => (
                    <th key={h}>{h}</th>
                  ))}
              </tr>
            </thead>
            <tbody>
              {receipts.map(r => (
                <tr key={r.id}>
                  <td>
                    {r.store_name || <span style={{ color: '#aaa' }}>미추출</span>}
                  </td>
                  <td>{r.receipt_type}</td>
                  <td>{r.order_date || '-'}</td>
                  <td>{fmt(r.total_amount)}</td>
                  <td>
                    {r.processor_name || '-'}
                  </td>
                  <td>
                    {fmtDatetime(r.created_at)}
                  </td>
                  <td className="tw-text-center">
                    {r.is_handwritten ? '✍️' : ''}
                  </td>
                  <td>
                    <Badge variant={r.needs_review ? 'warning' : 'success'}>{r.needs_review ? '확인필요' : '정상'}</Badge>
                  </td>
                  <td>
                    <Button type="button" variant="secondary" onClick={() => setSelected(r)}>상세</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* 상세 모달 */}
      {selected && (
        <ReceiptDetail
          receipt={selected}
          token={token}
          apiUrl={API_URL}
          onClose={() => setSelected(null)}
          onDeleted={() => { setSelected(null); loadReceipts(); }}
        />
      )}
    </div>
  );
}
