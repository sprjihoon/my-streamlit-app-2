'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  listInboundBatches,
  createInboundBatch,
  getInboundBatch,
  runInboundOcr,
  updateInboundItem,
  closeInboundBatch,
  deleteInboundBatch,
  listInboundVendors,
  InboundBatch,
  InboundItem,
} from '@/lib/api';

// ─────────────────────────────────────
// 상태 배지 색상
// ─────────────────────────────────────
const STATUS_COLOR: Record<string, string> = {
  ocr_pending:  'bg-gray-100 text-gray-600',
  confirming:   'bg-yellow-100 text-yellow-700',
  inbound_done: 'bg-blue-100 text-blue-700',
  grading:      'bg-purple-100 text-purple-700',
  repairing:    'bg-orange-100 text-orange-700',
  done:         'bg-green-100 text-green-700',
  cancelled:    'bg-red-100 text-red-600',
};
const ITEM_STATUS_COLOR: Record<string, string> = {
  pending:       'bg-gray-100 text-gray-500',
  confirmed:     'bg-green-100 text-green-700',
  missing:       'bg-red-100 text-red-600',
  defect:        'bg-orange-100 text-orange-700',
  repair:        'bg-yellow-100 text-yellow-700',
  unrecoverable: 'bg-red-200 text-red-800',
  done:          'bg-green-200 text-green-800',
};

// ─────────────────────────────────────
// Helpers
// ─────────────────────────────────────
function getToken(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('auth_token') || '';
}

function fmt(dt: string | null) {
  if (!dt) return '-';
  return dt.replace('T', ' ').slice(0, 16);
}

// ─────────────────────────────────────
// Modal 컴포넌트
// ─────────────────────────────────────
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-10 bg-black/40 overflow-auto">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl mx-4 mb-10">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-2xl leading-none">×</button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────
// 품목 행 컴포넌트
// ─────────────────────────────────────
function ItemRow({
  item,
  token,
  onUpdated,
}: {
  item: InboundItem;
  token: string;
  onUpdated: () => void;
}) {
  const [actualQty, setActualQty] = useState(item.actual_qty);
  const [missingQty, setMissingQty] = useState(item.missing_qty);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await updateInboundItem(token, item.id, {
        actual_qty: actualQty,
        missing_qty: missingQty,
        status: actualQty > 0 ? 'confirmed' : missingQty > 0 ? 'missing' : 'pending',
      });
      onUpdated();
    } catch {
      alert('저장 실패');
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="hover:bg-gray-50 border-b">
      <td className="px-3 py-2 text-sm text-gray-500 text-center">{item.line_no}</td>
      <td className="px-3 py-2 text-sm">
        <div className="font-medium">{item.item_name || '-'}</div>
        {item.option_text && <div className="text-xs text-gray-500">{item.option_text}</div>}
      </td>
      <td className="px-3 py-2 text-sm text-center">{item.janggi_qty}</td>
      <td className="px-3 py-2 text-sm">
        {item.matched_product ? (
          <div>
            <div className="text-xs font-medium text-blue-700">{item.matched_vendor}</div>
            <div className="text-xs">{item.matched_product}</div>
            {item.matched_option && <div className="text-xs text-gray-400">{item.matched_option}</div>}
            <div className="text-xs text-gray-400 font-mono">{item.matched_barcode}</div>
          </div>
        ) : (
          <span className="text-xs text-red-500">미매칭</span>
        )}
      </td>
      <td className="px-3 py-2">
        <input
          type="number"
          min={0}
          value={actualQty}
          onChange={e => setActualQty(Number(e.target.value))}
          className="w-16 border rounded px-1 py-0.5 text-sm text-center"
        />
      </td>
      <td className="px-3 py-2">
        <input
          type="number"
          min={0}
          value={missingQty}
          onChange={e => setMissingQty(Number(e.target.value))}
          className="w-16 border rounded px-1 py-0.5 text-sm text-center"
        />
      </td>
      <td className="px-3 py-2 text-center">
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ITEM_STATUS_COLOR[item.status] || ''}`}>
          {item.status_label}
        </span>
      </td>
      <td className="px-3 py-2 text-center">
        <button
          onClick={save}
          disabled={saving}
          className="text-xs bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600 disabled:opacity-50"
        >
          {saving ? '...' : '저장'}
        </button>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────
// 배치 상세 모달
// ─────────────────────────────────────
function BatchDetailModal({ batch: initialBatch, token, onClose, onUpdated }: {
  batch: InboundBatch;
  token: string;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [batch, setBatch] = useState<InboundBatch>(initialBatch);
  const [loading, setLoading] = useState(false);
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [closeLoading, setCloseLoading] = useState(false);
  const [warning, setWarning] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getInboundBatch(token, batch.id);
      setBatch(data);
    } finally {
      setLoading(false);
    }
  }, [token, batch.id]);

  async function handleOcr() {
    if (!ocrFile) return;
    setOcrLoading(true);
    setWarning('');
    try {
      const res = await runInboundOcr(token, batch.id, ocrFile);
      await reload();
      alert(`OCR 완료: ${res.item_count}개 품목 (${res.matched_count}개 자동매칭, ${res.needs_matching_count}개 확인 필요)`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('OCR 실패: ' + msg);
    } finally {
      setOcrLoading(false);
    }
  }

  async function handleClose() {
    setCloseLoading(true);
    setWarning('');
    try {
      const res = await closeInboundBatch(token, batch.id);
      if (!res.ok && res.warning) {
        setWarning(res.warning);
      } else {
        await reload();
        onUpdated();
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('마감 실패: ' + msg);
    } finally {
      setCloseLoading(false);
    }
  }

  const items = batch.items || [];
  const canClose = ['confirming', 'inbound_done', 'grading', 'repairing'].includes(batch.status);
  const closeLabel: Record<string, string> = {
    confirming: '입고접수 완료',
    inbound_done: '양품화 시작',
    grading: '마감',
    repairing: '마감',
  };

  return (
    <Modal title={`입고 상세 — ${batch.vendor} / ${batch.inbound_date}`} onClose={onClose}>
      {/* 헤더 요약 */}
      <div className="flex flex-wrap gap-4 mb-4 text-sm">
        <div className="flex gap-2 items-center">
          <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLOR[batch.status] || ''}`}>
            {batch.status_label}
          </span>
        </div>
        <div className="text-gray-600">
          도매처: <span className="font-medium">{batch.wholesale || '-'}</span>
        </div>
        <div className="text-gray-600">
          장끼수량: <span className="font-semibold text-blue-700">{batch.total_janggi_qty}</span>
        </div>
        <div className="text-gray-600">
          실입고: <span className="font-semibold text-green-700">{batch.total_actual_qty}</span>
        </div>
        <div className="text-gray-600">
          미입고: <span className="font-semibold text-red-600">{batch.total_missing_qty}</span>
        </div>
        {batch.janggi_no && <div className="text-gray-600">장끼번호: {batch.janggi_no}</div>}
      </div>

      {/* 장끼 OCR */}
      {['ocr_pending', 'confirming'].includes(batch.status) && (
        <div className="mb-4 p-3 bg-yellow-50 rounded-lg border border-yellow-200">
          <div className="text-sm font-medium mb-2 text-yellow-800">
            {batch.status === 'ocr_pending' ? '장끼 사진을 업로드해주세요' : '장끼 재분석'}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="file"
              accept="image/*"
              onChange={e => setOcrFile(e.target.files?.[0] || null)}
              className="text-sm"
            />
            <button
              onClick={handleOcr}
              disabled={!ocrFile || ocrLoading}
              className="text-sm bg-yellow-500 text-white px-4 py-1.5 rounded hover:bg-yellow-600 disabled:opacity-50"
            >
              {ocrLoading ? 'AI 분석 중...' : 'OCR 실행'}
            </button>
          </div>
        </div>
      )}

      {/* 경고 */}
      {warning && (
        <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          ⚠️ {warning}
        </div>
      )}

      {/* 품목 테이블 */}
      {items.length > 0 ? (
        <div className="overflow-x-auto mb-4">
          <table className="w-full text-sm border border-gray-200 rounded">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-center text-xs text-gray-500">No</th>
                <th className="px-3 py-2 text-left text-xs text-gray-500">품명/옵션</th>
                <th className="px-3 py-2 text-center text-xs text-gray-500">장끼수량</th>
                <th className="px-3 py-2 text-left text-xs text-gray-500">매칭 상품</th>
                <th className="px-3 py-2 text-center text-xs text-gray-500">실입고</th>
                <th className="px-3 py-2 text-center text-xs text-gray-500">미입고</th>
                <th className="px-3 py-2 text-center text-xs text-gray-500">상태</th>
                <th className="px-3 py-2 text-center text-xs text-gray-500"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <ItemRow key={item.id} item={item} token={token} onUpdated={reload} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center text-gray-400 py-6 text-sm">
          장끼 OCR을 실행하면 품목이 표시됩니다.
        </div>
      )}

      {/* 마감 버튼 */}
      {canClose && (
        <div className="flex justify-end mt-2">
          <button
            onClick={handleClose}
            disabled={closeLoading || loading}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
          >
            {closeLoading ? '처리 중...' : closeLabel[batch.status] || '마감'}
          </button>
        </div>
      )}
    </Modal>
  );
}

// ─────────────────────────────────────
// 신규 배치 생성 모달
// ─────────────────────────────────────
function CreateBatchModal({ token, onClose, onCreated }: {
  token: string;
  onClose: () => void;
  onCreated: (batch: InboundBatch) => void;
}) {
  const [vendor, setVendor] = useState('');
  const [inboundDate, setInboundDate] = useState(new Date().toISOString().slice(0, 10));
  const [memo, setMemo] = useState('');
  const [vendors, setVendors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listInboundVendors(token).then(r => setVendors(r.vendors)).catch(() => {});
  }, [token]);

  async function handleCreate() {
    if (!vendor.trim()) { alert('화주사를 입력해주세요.'); return; }
    setSaving(true);
    try {
      const res = await createInboundBatch(token, { vendor: vendor.trim(), inbound_date: inboundDate, memo: memo.trim() || undefined });
      // 생성된 배치 상세 조회
      const { getInboundBatch: getBatch } = await import('@/lib/api');
      const newBatch = await getBatch(token, res.id);
      onCreated(newBatch);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('생성 실패: ' + msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="신규 입고 등록" onClose={onClose}>
      <div className="space-y-4 max-w-md">
        <div>
          <label className="block text-sm font-medium mb-1">화주사 *</label>
          <input
            list="vendor-list"
            value={vendor}
            onChange={e => setVendor(e.target.value)}
            placeholder="예: 틸리언"
            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          <datalist id="vendor-list">
            {vendors.map(v => <option key={v} value={v} />)}
          </datalist>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">입고일 *</label>
          <input
            type="date"
            value={inboundDate}
            onChange={e => setInboundDate(e.target.value)}
            className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">메모</label>
          <input
            value={memo}
            onChange={e => setMemo(e.target.value)}
            placeholder="선택 사항"
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">취소</button>
          <button
            onClick={handleCreate}
            disabled={saving}
            className="px-5 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? '생성 중...' : '입고 시작'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────
export default function InboundLogPage() {
  const [token, setToken] = useState('');
  const [batches, setBatches] = useState<InboundBatch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState<InboundBatch | null>(null);

  // 필터
  const [filterVendor, setFilterVendor] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  useEffect(() => {
    setToken(localStorage.getItem('auth_token') || '');
  }, []);

  const load = useCallback(async (tok: string) => {
    if (!tok) return;
    setLoading(true);
    try {
      const res = await listInboundBatches(tok, {
        vendor: filterVendor || undefined,
        status: filterStatus || undefined,
        dateFrom: filterDateFrom || undefined,
        dateTo: filterDateTo || undefined,
      });
      setBatches(res.items);
      setTotal(res.total);
    } catch {
      //
    } finally {
      setLoading(false);
    }
  }, [filterVendor, filterStatus, filterDateFrom, filterDateTo]);

  useEffect(() => {
    if (token) load(token);
  }, [token, load]);

  async function handleDelete(id: string) {
    if (!confirm('이 입고건을 삭제하시겠습니까?')) return;
    try {
      await deleteInboundBatch(token, id);
      load(token);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('삭제 실패: ' + msg);
    }
  }

  async function openDetail(batch: InboundBatch) {
    const detail = await getInboundBatch(token, batch.id);
    setSelectedBatch(detail);
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">📦 입고일지</h1>
          <p className="text-gray-500 text-sm mt-1">장끼 OCR → 상품 매칭 → 실수량 확인 → 양품화 → 마감</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          + 입고 등록
        </button>
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap gap-3 mb-4 bg-gray-50 p-3 rounded-lg">
        <input
          placeholder="화주사"
          value={filterVendor}
          onChange={e => setFilterVendor(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm w-32"
        />
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm"
        >
          <option value="">전체 상태</option>
          <option value="ocr_pending">장끼 확인 중</option>
          <option value="confirming">수량 확인 중</option>
          <option value="inbound_done">입고접수 완료</option>
          <option value="grading">양품화 중</option>
          <option value="repairing">수선 중</option>
          <option value="done">최종완료</option>
        </select>
        <input type="date" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        <span className="self-center text-gray-400">~</span>
        <input type="date" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        <button
          onClick={() => load(token)}
          className="bg-blue-500 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-600"
        >
          조회
        </button>
        <button
          onClick={() => { setFilterVendor(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo(''); }}
          className="text-gray-500 px-3 py-1.5 rounded text-sm border hover:bg-gray-100"
        >
          초기화
        </button>
      </div>

      {/* 총 건수 */}
      <div className="text-sm text-gray-500 mb-2">총 {total}건</div>

      {/* 목록 테이블 */}
      {loading ? (
        <div className="text-center text-gray-400 py-16 text-sm">불러오는 중...</div>
      ) : batches.length === 0 ? (
        <div className="text-center text-gray-300 py-16">
          <div className="text-5xl mb-3">📦</div>
          <div className="text-sm">입고 데이터가 없습니다.</div>
          <button onClick={() => setShowCreate(true)} className="mt-4 text-blue-500 text-sm underline">
            첫 입고 등록하기
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">입고일</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">화주사</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">도매처</th>
                <th className="px-4 py-3 text-center text-xs text-gray-500 font-medium">상태</th>
                <th className="px-4 py-3 text-center text-xs text-gray-500 font-medium">장끼수량</th>
                <th className="px-4 py-3 text-center text-xs text-gray-500 font-medium">실입고</th>
                <th className="px-4 py-3 text-center text-xs text-gray-500 font-medium">미입고</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">등록자</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">등록일시</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {batches.map(b => (
                <tr key={b.id} className="hover:bg-blue-50 cursor-pointer" onClick={() => openDetail(b)}>
                  <td className="px-4 py-3 font-medium">{b.inbound_date}</td>
                  <td className="px-4 py-3">{b.vendor}</td>
                  <td className="px-4 py-3 text-gray-500">{b.wholesale || '-'}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLOR[b.status] || ''}`}>
                      {b.status_label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-blue-700 font-medium">{b.total_janggi_qty}</td>
                  <td className="px-4 py-3 text-center text-green-700 font-medium">{b.total_actual_qty}</td>
                  <td className="px-4 py-3 text-center text-red-600 font-medium">
                    {b.total_missing_qty > 0 ? b.total_missing_qty : '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{b.created_by || '-'}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{fmt(b.created_at)}</td>
                  <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                    <button
                      onClick={() => handleDelete(b.id)}
                      className="text-xs text-red-400 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50"
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

      {/* 신규 등록 모달 */}
      {showCreate && (
        <CreateBatchModal
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={batch => {
            setShowCreate(false);
            setSelectedBatch(batch);
            load(token);
          }}
        />
      )}

      {/* 상세 모달 */}
      {selectedBatch && (
        <BatchDetailModal
          batch={selectedBatch}
          token={token}
          onClose={() => setSelectedBatch(null)}
          onUpdated={() => load(token)}
        />
      )}
    </div>
  );
}
