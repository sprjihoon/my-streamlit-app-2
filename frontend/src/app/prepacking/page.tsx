'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function ppFetch<T = unknown>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers: Record<string, string> = { ...options?.headers as Record<string, string> };
  if (options?.body) headers['Content-Type'] = 'application/json';
  let res: Response;
  try {
    res = await fetch(url, { ...options, headers });
  } catch (err) {
    throw new Error(`[${endpoint}] 네트워크 오류: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`[${endpoint}] ${text || `API Error ${res.status}`}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// TypeScript interfaces
// ---------------------------------------------------------------------------
interface UploadRecord {
  upload_id: number;
  file_name: string;
  file_version: number;
  uploaded_at: string;
  uploaded_by: string;
  row_count: number;
  applied_yn: boolean;
  note: string;
  upload_status: string;
  skipped_count: number;
  total_count: number;
}

interface RepeatSku {
  sku_name: string;
  option_name: string;
  total_count: number;
  daily_avg: number;
  weekday_counts: Record<string, number>;
  first_seen: string;
  last_seen: string;
}

interface RepeatCombination {
  combination_key: string;
  items: { sku_code: string; product_name: string; option_name: string; qty: number; inner_qty: number }[];
  total_count: number;
  daily_avg: number;
  weekday_counts: Record<string, number>;
  first_seen: string;
  last_seen: string;
}

interface WeekdayPattern {
  name: string;
  weekday_counts: Record<string, number>;
  weekday_avgs: Record<string, number>;
  peak_day: number;
  variability: number;
}

interface WeekdayResponse {
  sku_patterns: WeekdayPattern[];
  combo_patterns: WeekdayPattern[];
  overall: {
    total_orders_by_weekday: Record<string, number>;
    avg_orders_by_weekday: Record<string, number>;
  };
}

interface Recommendation {
  recommendation_id: number;
  supplier_name: string;
  target_date: string;
  target_type: string;
  target_code: string;
  target_name: string;
  predicted_qty: number;
  confidence_score: number;
  risk_score: number;
  recommendation_reason: string;
  status: string;
  created_at: string;
}

interface Execution {
  execution_id: number;
  recommendation_id: number;
  target_code: string;
  target_name: string;
  executed_qty: number;
  executed_by: string;
  executed_at: string;
  execution_status: string;
  memo: string;
}

interface StockItem {
  prepack_stock_id: number;
  target_code: string;
  target_name: string;
  current_qty: number;
  available_qty: number;
  location_code: string;
  supplier_name: string;
  pack_status: string;
  packed_at: string;
  expiry_at: string;
}

interface StockSummary {
  total_packed: number;
  total_available: number;
  by_status: Record<string, number>;
  by_location: Record<string, number>;
}

interface Location {
  location_code: string;
  location_name: string;
  location_zone: string;
  location_type: string;
  max_capacity: number;
  current_capacity: number;
  is_active: number;
  note: string;
}

interface MoveRecord {
  location_history_id: number;
  prepack_stock_id: number;
  target_name: string;
  action_type: string;
  from_location: string;
  to_location: string;
  qty: number;
  action_by: string;
  action_reason: string;
  action_at: string;
}

interface BacktestItem {
  target_type: string;
  target_name: string;
  option_name: string;
  sku_code: string;
  barcode: string;
  items?: SkuDetail[];
  predicted_qty: number;
  stat_qty: number;
  ml_qty: number;
  model_type: string;
  actual_qty: number;
  error_abs: number;
  error_pct: number;
  result_type: string;
  confidence_score: number;
  frequency: number;
}

interface BacktestResult {
  target_date: string;
  weekday_name: string;
  supplier_name: string;
  summary: {
    accuracy: number;
    avg_mape: number;
    total_predicted: number;
    total_actual: number;
    total_error: number;
    item_count: number;
    matched: number;
    over: number;
    under: number;
    missed: number;
    ml_count: number;
    stat_count: number;
  };
  items: BacktestItem[];
  missed_items: BacktestItem[];
}

interface OverviewReport {
  total_recommendations: number;
  approved_count: number;
  rejected_count: number;
  executed_count: number;
  total_produced_qty: number;
  total_used_qty: number;
  utilization_rate: number;
  active_stock_count: number;
  avg_confidence: number;
}

interface ValidationReport {
  total_validated: number;
  avg_accuracy: number;
  avg_mape: number;
  by_result: Record<string, number>;
  unwrap_rate: number;
  top_accurate_skus: { sku_key: string; accuracy: number; samples: number }[];
  top_inaccurate_skus: { sku_key: string; accuracy: number; samples: number }[];
  daily_accuracy_trend: { date: string; accuracy: number }[];
}

interface AiUsageReport {
  total_calls: number;
  total_tokens: number;
  total_cost: number;
  avg_latency: number;
  success_rate: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TABS = [
  { key: 'upload', label: '업로드', icon: '📤' },
  { key: 'analysis', label: '분석', icon: '📊' },
  { key: 'recommend', label: '작업지시', icon: '📋' },
  { key: 'execute', label: '실행', icon: '▶️' },
  { key: 'stock', label: '재고', icon: '📦' },
  { key: 'location', label: '로케이션', icon: '📍' },
  { key: 'validation', label: '검증', icon: '✅' },
  { key: 'report', label: '리포트', icon: '📋' },
  { key: 'settings', label: '설정', icon: '⚙️' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  recommended: { bg: '#fef3c7', fg: '#92400e' },
  pending: { bg: '#fef3c7', fg: '#92400e' },
  approved: { bg: '#d1fae5', fg: '#065f46' },
  modified: { bg: '#e0e7ff', fg: '#3730a3' },
  held: { bg: '#e0e7ff', fg: '#3730a3' },
  rejected: { bg: '#fee2e2', fg: '#991b1b' },
  executed: { bg: '#dbeafe', fg: '#1e40af' },
  expired: { bg: '#f3f4f6', fg: '#6b7280' },
  matched: { bg: '#d1fae5', fg: '#065f46' },
  over: { bg: '#fef3c7', fg: '#92400e' },
  under: { bg: '#fee2e2', fg: '#991b1b' },
  missed: { bg: '#fee2e2', fg: '#991b1b' },
};

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------
const card: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  padding: 20,
  marginBottom: 16,
};

const btnPrimary: React.CSSProperties = {
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 8,
  padding: '8px 18px',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: 14,
};

const btnSuccess: React.CSSProperties = { ...btnPrimary, background: '#16a34a' };
const btnWarning: React.CSSProperties = { ...btnPrimary, background: '#f59e0b', color: '#000' };
const btnDanger: React.CSSProperties = { ...btnPrimary, background: '#dc2626' };
const btnOutline: React.CSSProperties = {
  ...btnPrimary,
  background: '#fff',
  color: '#2563eb',
  border: '1px solid #2563eb',
};

const inputStyle: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 8,
  padding: '8px 12px',
  fontSize: 14,
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: '#374151',
  marginBottom: 4,
  display: 'block',
};

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '10px 12px',
  fontSize: 13,
  fontWeight: 600,
  color: '#6b7280',
  borderBottom: '2px solid #e5e7eb',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: 13,
  borderBottom: '1px solid #f3f4f6',
};

const statCard = (accent: string): React.CSSProperties => ({
  ...card,
  borderLeft: `4px solid ${accent}`,
  flex: '1 1 180px',
  minWidth: 180,
});

// ---------------------------------------------------------------------------
// Toast component
// ---------------------------------------------------------------------------
function Toast({ msg, type, onClose }: { msg: string; type: 'success' | 'error' | 'info'; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);
  const bg = type === 'success' ? '#d1fae5' : type === 'error' ? '#fee2e2' : '#dbeafe';
  const fg = type === 'success' ? '#065f46' : type === 'error' ? '#991b1b' : '#1e40af';
  return (
    <div
      style={{
        position: 'fixed',
        top: 24,
        right: 24,
        zIndex: 9999,
        background: bg,
        color: fg,
        padding: '12px 24px',
        borderRadius: 10,
        fontWeight: 600,
        fontSize: 14,
        boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
        maxWidth: 420,
      }}
    >
      {msg}
      <span style={{ marginLeft: 12, cursor: 'pointer', opacity: 0.6 }} onClick={onClose}>✕</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------
function Badge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] || { bg: '#f3f4f6', fg: '#374151' };
  return (
    <span style={{ background: c.bg, color: c.fg, padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600 }}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ConfidenceBar
// ---------------------------------------------------------------------------
function ConfidenceBar({ value, color }: { value: number; color?: string }) {
  const pct = Math.min(Math.max(value * 100, 0), 100);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color || '#2563eb', borderRadius: 4 }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: '#374151', minWidth: 40 }}>{pct.toFixed(0)}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function Empty({ message }: { message: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '48px 20px', color: '#9ca3af' }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
      <div style={{ fontSize: 15 }}>{message}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading spinner
// ---------------------------------------------------------------------------
function Spinner() {
  return (
    <div style={{ textAlign: 'center', padding: '40px 0' }}>
      <div
        style={{
          display: 'inline-block',
          width: 32,
          height: 32,
          border: '3px solid #e5e7eb',
          borderTopColor: '#2563eb',
          borderRadius: '50%',
          animation: 'pp-spin 0.7s linear infinite',
        }}
      />
      <style>{`@keyframes pp-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function PrepackingPage() {
  const [tab, setTab] = useState<TabKey>('upload');
  const [supplierName, setSupplierName] = useState('');
  const [supplierList, setSupplierList] = useState<string[]>([]);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' | 'info' } | null>(null);

  const showToast = useCallback((msg: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ msg, type });
  }, []);

  const loadSuppliers = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/pp/upload/suppliers`);
      if (res.ok) {
        const data: string[] = await res.json();
        setSupplierList(data);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSuppliers(); }, [loadSuppliers]);

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif' }}>
      {toast && <Toast msg={toast.msg} type={toast.type} onClose={() => setToast(null)} />}

      {/* Header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e5e7eb', padding: '16px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#111827' }}>📦 프리패킹 관리</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#6b7280' }}>공급처</label>
            <select
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              style={{ ...inputStyle, width: 220 }}
            >
              <option value="">전체 (공급처 선택)</option>
              {supplierList.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 2, marginTop: 16, overflowX: 'auto' }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: '10px 16px',
                border: 'none',
                borderBottom: tab === t.key ? '3px solid #2563eb' : '3px solid transparent',
                background: tab === t.key ? '#eff6ff' : 'transparent',
                color: tab === t.key ? '#2563eb' : '#6b7280',
                fontWeight: tab === t.key ? 700 : 500,
                fontSize: 14,
                cursor: 'pointer',
                borderRadius: '8px 8px 0 0',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s',
              }}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1280, margin: '0 auto', padding: '20px 24px' }}>
        {tab === 'upload' && <UploadTab supplierName={supplierName} showToast={showToast} onUploadDone={loadSuppliers} />}
        {tab === 'analysis' && <AnalysisTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'recommend' && <RecommendTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'execute' && <ExecuteTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'stock' && <StockTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'location' && <LocationTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'validation' && <ValidationTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'report' && <ReportTab supplierName={supplierName} showToast={showToast} />}
        {tab === 'settings' && <SettingsTab supplierName={supplierName} showToast={showToast} />}
      </div>
    </div>
  );
}

// ===========================================================================
// TAB: 업로드
// ===========================================================================
function UploadTab({ supplierName, showToast, onUploadDone }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void; onUploadDone?: () => void }) {
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [note, setNote] = useState('');
  const [uploadedBy, setUploadedBy] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadUploads = useCallback(async () => {
    setLoading(true);
    try {
      let q = '/pp/upload/list?limit=50';
      if (supplierName) q += `&supplier_name=${encodeURIComponent(supplierName)}`;
      const data = await ppFetch<UploadRecord[]>(q);
      setUploads(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '업로드 목록 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [supplierName, showToast]);

  useEffect(() => { loadUploads(); }, [loadUploads]);

  const hasProcessing = uploads.some((u) => u.upload_status === 'processing');

  useEffect(() => {
    if (hasProcessing) {
      pollingRef.current = setInterval(() => { loadUploads(); }, 3000);
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [hasProcessing, loadUploads]);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { showToast('파일을 선택해주세요', 'error'); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('supplier_name', '');
      fd.append('uploaded_by', uploadedBy || 'unknown');
      fd.append('note', note);
      const res = await fetch(`${API_BASE}/pp/upload/upload`, { method: 'POST', body: fd });
      if (!res.ok) {
        const errText = await res.text();
        if (res.status === 409) {
          showToast(`중복 파일: ${errText.replace(/^"?detail"?:\s*"?|"$/g, '')}`, 'error');
        } else {
          throw new Error(errText);
        }
        return;
      }
      showToast('파일 업로드 완료! 서버에서 데이터 처리 중입니다...', 'info');
      if (fileRef.current) fileRef.current.value = '';
      setNote('');
      loadUploads();
      onUploadDone?.();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '업로드 실패', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('삭제하시겠습니까?')) return;
    try {
      await ppFetch(`/pp/upload/${id}`, { method: 'DELETE' });
      showToast('삭제 완료', 'success');
      loadUploads();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '삭제 실패', 'error');
    }
  };

  const statusLabel = (status: string) => {
    if (status === 'processing') return { text: '처리 중...', bg: '#fef3c7', fg: '#92400e' };
    if (status === 'failed') return { text: '실패', bg: '#fee2e2', fg: '#991b1b' };
    return { text: '완료', bg: '#d1fae5', fg: '#065f46' };
  };

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>📤 배송통계 파일 업로드</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 200px' }}>
            <label style={labelStyle}>파일 선택</label>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              style={{
                ...inputStyle,
                padding: '10px 12px',
                background: '#f9fafb',
                border: '2px dashed #d1d5db',
                cursor: 'pointer',
              }}
            />
          </div>
          <div style={{ flex: '0 0 160px' }}>
            <label style={labelStyle}>업로드 담당자</label>
            <input value={uploadedBy} onChange={(e) => setUploadedBy(e.target.value)} placeholder="이름" style={inputStyle} />
          </div>
          <div style={{ flex: '1 1 200px' }}>
            <label style={labelStyle}>메모</label>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="메모 (선택)" style={inputStyle} />
          </div>
          <button onClick={handleUpload} disabled={uploading} style={{ ...btnPrimary, opacity: uploading ? 0.6 : 1 }}>
            {uploading ? '전송 중...' : '업로드'}
          </button>
        </div>
      </div>

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
            업로드 이력
            {hasProcessing && (
              <span style={{ marginLeft: 8, fontSize: 12, color: '#92400e', fontWeight: 500 }}>
                (처리 중인 파일이 있습니다...)
              </span>
            )}
          </h3>
          <button onClick={loadUploads} style={btnOutline}>새로고침</button>
        </div>
        {loading && uploads.length === 0 ? (
          <Spinner />
        ) : uploads.length === 0 ? (
          <Empty message="업로드 이력이 없습니다. 파일을 업로드해주세요." />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>ID</th>
                  <th style={thStyle}>파일명</th>
                  <th style={thStyle}>상태</th>
                  <th style={thStyle}>업로더</th>
                  <th style={thStyle}>저장/스킵/전체</th>
                  <th style={thStyle}>메모</th>
                  <th style={thStyle}>업로드일</th>
                  <th style={thStyle}>작업</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((u, i) => {
                  const st = statusLabel(u.upload_status);
                  return (
                    <tr key={u.upload_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                      <td style={tdStyle}>{u.upload_id}</td>
                      <td style={tdStyle}>{u.file_name}</td>
                      <td style={tdStyle}>
                        <span style={{
                          background: st.bg, color: st.fg,
                          padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                        }}>
                          {u.upload_status === 'processing' && (
                            <span style={{
                              display: 'inline-block', width: 10, height: 10,
                              border: '2px solid #92400e', borderTopColor: 'transparent',
                              borderRadius: '50%', animation: 'pp-spin 0.7s linear infinite',
                            }} />
                          )}
                          {st.text}
                        </span>
                      </td>
                      <td style={tdStyle}>{u.uploaded_by}</td>
                      <td style={tdStyle}>
                        {u.upload_status === 'processing' ? (
                          <span style={{ color: '#92400e', fontSize: 12 }}>처리 중...</span>
                        ) : u.upload_status === 'failed' ? (
                          <span style={{ color: '#991b1b', fontSize: 12 }}>오류 발생</span>
                        ) : (
                          <span>
                            <span style={{ fontWeight: 700, color: '#2563eb' }}>{u.row_count?.toLocaleString()}</span>
                            {u.skipped_count > 0 && (
                              <span style={{ color: '#92400e', fontSize: 12 }}> / {u.skipped_count.toLocaleString()} 스킵</span>
                            )}
                            <span style={{ color: '#6b7280', fontSize: 12 }}> / {u.total_count?.toLocaleString()}</span>
                          </span>
                        )}
                      </td>
                      <td style={tdStyle}>{u.note || '-'}</td>
                      <td style={tdStyle}>{u.uploaded_at?.slice(0, 16)}</td>
                      <td style={tdStyle}>
                        {u.upload_status !== 'processing' && (
                          <button onClick={() => handleDelete(u.upload_id)} style={{ ...btnDanger, padding: '4px 10px', fontSize: 12 }}>삭제</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

// ===========================================================================
// TAB: 분석
// ===========================================================================
function AnalysisTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [minCount, setMinCount] = useState(3);
  const [subTab, setSubTab] = useState<'skus' | 'combos' | 'weekday'>('skus');
  const [repeatSkus, setRepeatSkus] = useState<RepeatSku[]>([]);
  const [repeatCombos, setRepeatCombos] = useState<RepeatCombination[]>([]);
  const [weekday, setWeekday] = useState<WeekdayPattern[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);

  const reqBody = () => JSON.stringify({ supplier_name: supplierName, min_count: minCount });

  const analyzeAll = useCallback(async () => {
    if (!supplierName) { showToast('공급처를 선택해주세요', 'error'); return; }
    setLoading(true);
    try {
      const [skuData, comboData, wdData] = await Promise.all([
        ppFetch<RepeatSku[]>('/pp/analysis/repeat-skus', { method: 'POST', body: JSON.stringify({ supplier_name: supplierName, min_count: minCount }) }),
        ppFetch<RepeatCombination[]>('/pp/analysis/repeat-combinations', { method: 'POST', body: JSON.stringify({ supplier_name: supplierName, min_count: minCount }) }),
        ppFetch<WeekdayResponse>('/pp/analysis/weekday-patterns', { method: 'POST', body: JSON.stringify({ supplier_name: supplierName, min_count: minCount }) }),
      ]);
      setRepeatSkus(Array.isArray(skuData) ? skuData : []);
      setRepeatCombos(Array.isArray(comboData) ? comboData : []);
      setWeekday(wdData?.sku_patterns || []);
      setAnalyzed(true);
      showToast('전체 분석 완료', 'success');
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '분석 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [supplierName, minCount, showToast]);

  void reqBody;

  const heatColor = (val: number, max: number) => {
    if (max === 0) return '#f3f4f6';
    const ratio = val / max;
    if (ratio > 0.8) return '#dc2626';
    if (ratio > 0.6) return '#f59e0b';
    if (ratio > 0.3) return '#fbbf24';
    if (ratio > 0) return '#fef3c7';
    return '#f3f4f6';
  };

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>📊 배송 데이터 분석</h3>
        <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6b7280' }}>
          업로드된 전체 데이터를 기반으로 반복 SKU, 반복 조합, 요일 패턴을 한번에 분석합니다.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 120px' }}>
            <label style={labelStyle}>최소 반복 횟수</label>
            <input type="number" value={minCount} onChange={(e) => setMinCount(Number(e.target.value))} min={1} style={inputStyle} />
          </div>
          <button onClick={analyzeAll} disabled={loading || !supplierName} style={{ ...btnPrimary, padding: '10px 24px', fontSize: 15, opacity: (loading || !supplierName) ? 0.5 : 1 }}>
            {loading ? '분석 중...' : '분석 실행'}
          </button>
        </div>
        {!supplierName && <p style={{ margin: '12px 0 0', fontSize: 13, color: '#f59e0b' }}>상단에서 공급처를 먼저 선택해주세요.</p>}
      </div>

      {loading && <Spinner />}

      {!loading && analyzed && (
        <>
          {/* Summary */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
            <div style={{ ...card, borderLeft: '4px solid #2563eb', flex: '1 1 160px', marginBottom: 0, textAlign: 'center', cursor: 'pointer', background: subTab === 'skus' ? '#eff6ff' : '#fff' }} onClick={() => setSubTab('skus')}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>반복 SKU</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#2563eb' }}>{repeatSkus.length}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #7c3aed', flex: '1 1 160px', marginBottom: 0, textAlign: 'center', cursor: 'pointer', background: subTab === 'combos' ? '#f5f3ff' : '#fff' }} onClick={() => setSubTab('combos')}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>반복 조합</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#7c3aed' }}>{repeatCombos.length}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #f59e0b', flex: '1 1 160px', marginBottom: 0, textAlign: 'center', cursor: 'pointer', background: subTab === 'weekday' ? '#fffbeb' : '#fff' }} onClick={() => setSubTab('weekday')}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>요일 패턴</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#f59e0b' }}>{weekday.length}</div>
            </div>
          </div>

          {/* Sub-tab content */}
          {subTab === 'skus' && (
            <div style={card}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>반복 SKU ({repeatSkus.length}건)</h3>
              {repeatSkus.length === 0 ? <Empty message="반복 SKU가 없습니다." /> : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th style={{ ...thStyle, width: 40 }}>#</th>
                        <th style={thStyle}>상품명</th>
                        <th style={thStyle}>옵션</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>총 수량</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>일평균</th>
                        <th style={thStyle}>첫 출고</th>
                        <th style={thStyle}>최근 출고</th>
                      </tr>
                    </thead>
                    <tbody>
                      {repeatSkus.map((s, i) => (
                        <tr key={`${s.sku_name}-${s.option_name}`} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                          <td style={{ ...tdStyle, color: '#9ca3af', fontSize: 12 }}>{i + 1}</td>
                          <td style={{ ...tdStyle, fontWeight: 600 }}>{s.sku_name}</td>
                          <td style={tdStyle}>{s.option_name || '-'}</td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#2563eb' }}>{s.total_count.toLocaleString()}</td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>{s.daily_avg.toFixed(1)}</td>
                          <td style={tdStyle}>{s.first_seen}</td>
                          <td style={tdStyle}>{s.last_seen}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {subTab === 'combos' && (
            <div style={card}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>반복 조합 ({repeatCombos.length}건)</h3>
              {repeatCombos.length === 0 ? <Empty message="반복 조합이 없습니다." /> : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th style={{ ...thStyle, width: 40 }}>#</th>
                        <th style={thStyle}>조합 구성</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>반복 횟수</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>일평균</th>
                        <th style={thStyle}>첫 출고</th>
                        <th style={thStyle}>최근 출고</th>
                      </tr>
                    </thead>
                    <tbody>
                      {repeatCombos.map((c, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                          <td style={{ ...tdStyle, color: '#9ca3af', fontSize: 12 }}>{i + 1}</td>
                          <td style={tdStyle}>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                              {c.items.map((item, idx) => (
                                <span key={idx} style={{ background: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                                  {item.product_name || item.sku_code} x{item.qty}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#7c3aed' }}>{c.total_count}</td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>{c.daily_avg.toFixed(1)}</td>
                          <td style={tdStyle}>{c.first_seen}</td>
                          <td style={tdStyle}>{c.last_seen}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {subTab === 'weekday' && (
            <div style={card}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>요일별 패턴 ({weekday.length}건)</h3>
              {weekday.length === 0 ? <Empty message="요일 패턴이 없습니다." /> : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th style={thStyle}>이름</th>
                        {[0,1,2,3,4,5,6].map((d) => <th key={d} style={{ ...thStyle, textAlign: 'center', minWidth: 50 }}>{WEEKDAYS[d]}</th>)}
                        <th style={{ ...thStyle, textAlign: 'center' }}>피크</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>합계</th>
                      </tr>
                    </thead>
                    <tbody>
                      {weekday.map((w, i) => {
                        const vals = [0,1,2,3,4,5,6].map((d) => w.weekday_counts[d] || 0);
                        const maxVal = Math.max(...vals);
                        const total = vals.reduce((a, b) => a + b, 0);
                        return (
                          <tr key={w.name} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                            <td style={{ ...tdStyle, fontWeight: 600 }}>{w.name}</td>
                            {[0,1,2,3,4,5,6].map((d) => {
                              const v = w.weekday_counts[d] || 0;
                              return (
                                <td key={d} style={{ ...tdStyle, textAlign: 'center' }}>
                                  <div style={{
                                    display: 'inline-block', width: 36, height: 28, lineHeight: '28px',
                                    borderRadius: 6, fontSize: 12, fontWeight: 600,
                                    background: heatColor(v, maxVal),
                                    color: maxVal > 0 && v / maxVal > 0.6 ? '#fff' : '#374151',
                                  }}>{v}</div>
                                </td>
                              );
                            })}
                            <td style={{ ...tdStyle, textAlign: 'center' }}>
                              <span style={{ background: '#fee2e2', color: '#dc2626', padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>{WEEKDAYS[w.peak_day]}</span>
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>{total.toLocaleString()}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!loading && !analyzed && (
        <div style={{ ...card, textAlign: 'center', padding: '48px 20px' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#374151', marginBottom: 8 }}>배송 데이터 분석</div>
          <div style={{ fontSize: 14, color: '#9ca3af' }}>
            공급처를 선택하고 &quot;분석 실행&quot; 버튼을 누르면<br />
            업로드된 전체 데이터를 기반으로 분석합니다.
          </div>
        </div>
      )}
    </>
  );
}

// ===========================================================================
// TAB: 작업지시
// ===========================================================================
interface SkuDetail {
  sku_code: string;
  barcode: string;
  product_name: string;
  option_name: string;
  qty: number;
}

interface WorkOrderItem {
  supplier_name: string;
  target_type: string;
  target_name: string;
  target_code: string;
  sku_code: string;
  barcode: string;
  combination_key: string;
  items: SkuDetail[];
  predicted_qty: number;
  stat_qty: number;
  ml_qty: number;
  model_used: string;
  ml_accuracy: number;
  gpt_reason: string;
  gpt_confidence: string;
  confidence_score: number;
  recent_7d_avg: number;
  recent_30d_avg: number;
  recent_same_weekday_avg: number;
  weekday_basis: number;
  frequency: number;
}

interface WorkOrderResult {
  target_date: string;
  weekday_name: string;
  weekday_index: number;
  supplier_filter: string;
  total_items: number;
  total_predicted_qty: number;
  combination_count: number;
  single_sku_count: number;
  items: WorkOrderItem[];
  errors?: string[];
}

function RecommendTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = tomorrow.toISOString().slice(0, 10);

  const [targetDate, setTargetDate] = useState(tomorrowStr);
  const [result, setResult] = useState<WorkOrderResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState<'all' | 'combination' | 'single_sku'>('all');

  const generate = async () => {
    if (!targetDate) { showToast('날짜를 선택해주세요', 'error'); return; }
    setLoading(true);
    try {
      const data = await ppFetch<WorkOrderResult>('/pp/recommendations/work-order', {
        method: 'POST',
        body: JSON.stringify({ target_date: targetDate, supplier_name: supplierName }),
      });
      setResult(data);
      if (data.total_items === 0) {
        const errMsg = data.errors && data.errors.length > 0
          ? `예측 실패: ${data.errors[0]}`
          : '예측 데이터가 없습니다. 배송통계 파일을 먼저 업로드해주세요.';
        showToast(errMsg, 'error');
      } else {
        showToast(`${data.weekday_name}요일 작업지시 생성 완료: ${data.total_items}건`, 'success');
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '작업지시 생성 실패', 'error');
    } finally {
      setLoading(false);
    }
  };

  const filtered = result?.items.filter((i) => {
    if (typeFilter === 'combination') return i.target_type === 'combination';
    if (typeFilter === 'single_sku') return i.target_type !== 'combination';
    return true;
  }) || [];

  const confColor = (v: number) => v >= 0.7 ? '#16a34a' : v >= 0.4 ? '#f59e0b' : '#dc2626';

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>
          📋 프리패킹 작업 지시서
        </h3>
        <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6b7280' }}>
          날짜를 선택하면 해당 요일의 과거 패턴을 분석하여 준비해야 할 조합과 수량을 예측합니다.
          {!supplierName && ' 공급처를 선택하지 않으면 전체 업체 대상으로 생성됩니다.'}
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 180px' }}>
            <label style={labelStyle}>대상 날짜</label>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} style={inputStyle} />
          </div>
          <button onClick={generate} disabled={loading} style={{ ...btnPrimary, padding: '10px 24px', fontSize: 15, opacity: loading ? 0.6 : 1 }}>
            {loading ? '분석 중...' : '작업지시 생성'}
          </button>
        </div>
      </div>

      {loading && <Spinner />}

      {!loading && result && result.total_items > 0 && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
            <div style={{ ...card, borderLeft: '4px solid #2563eb', flex: '1 1 200px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>대상일</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#111827' }}>
                {result.target_date}
                <span style={{ fontSize: 16, fontWeight: 700, color: '#2563eb', marginLeft: 8 }}>({result.weekday_name})</span>
              </div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #16a34a', flex: '1 1 140px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>총 예측 수량</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#16a34a' }}>{result.total_predicted_qty.toLocaleString()}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #7c3aed', flex: '1 1 120px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>조합</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#7c3aed' }}>{result.combination_count}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #f59e0b', flex: '1 1 120px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>단일 SKU</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#f59e0b' }}>{result.single_sku_count}</div>
            </div>
            {(() => {
              const items = result.items || [];
              const gptCount = items.filter((it: WorkOrderItem) => it.model_used?.includes('gpt')).length;
              const mlCount = items.filter((it: WorkOrderItem) => it.model_used?.includes('ml')).length;
              const statCount = items.length - mlCount;
              return (
                <div style={{ ...card, borderLeft: '4px solid #8b5cf6', flex: '1 1 200px', marginBottom: 0, textAlign: 'center' }}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>AI 예측 모델</div>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 12, fontSize: 13, fontWeight: 600 }}>
                    {gptCount > 0 && <span style={{ color: '#8b5cf6' }}>GPT {gptCount}</span>}
                    {mlCount > 0 && <span style={{ color: '#2563eb' }}>ML {mlCount}</span>}
                    {statCount > 0 && <span style={{ color: '#6b7280' }}>통계 {statCount}</span>}
                  </div>
                </div>
              );
            })()}
          </div>

          {/* Filter + table */}
          <div style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>작업 목록 ({filtered.length}건)</h3>
              <div style={{ display: 'flex', gap: 4 }}>
                {([['all', '전체'], ['combination', '조합'], ['single_sku', '단일 SKU']] as const).map(([k, label]) => (
                  <button
                    key={k}
                    onClick={() => setTypeFilter(k)}
                    style={{
                      padding: '6px 14px', border: typeFilter === k ? '1px solid #2563eb' : '1px solid #d1d5db',
                      background: typeFilter === k ? '#eff6ff' : '#fff', color: typeFilter === k ? '#2563eb' : '#6b7280',
                      borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                    }}
                  >{label}</button>
                ))}
              </div>
            </div>

            {filtered.length === 0 ? <Empty message="해당 유형의 항목이 없습니다." /> : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ ...thStyle, width: 40 }}>#</th>
                      <th style={thStyle}>유형</th>
                      {!supplierName && <th style={thStyle}>공급처</th>}
                      <th style={thStyle}>상품/조합명</th>
                      <th style={thStyle}>바코드</th>
                      <th style={{ ...thStyle, textAlign: 'center' }}>구성</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>AI 예측</th>
                      <th style={{ ...thStyle, textAlign: 'center' }}>예측 모델</th>
                      <th style={{ ...thStyle, textAlign: 'center' }}>신뢰도</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>출현</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((item, i) => {
                      const isCombo = item.target_type === 'combination';
                      const skuItems = item.items || [];
                      const hasGpt = item.model_used?.includes('gpt');
                      const hasMl = item.model_used?.includes('ml');
                      const modelLabel = hasGpt ? (hasMl ? 'ML+GPT' : 'GPT') : hasMl ? 'ML' : '통계';
                      const modelColor = hasGpt ? '#8b5cf6' : hasMl ? '#2563eb' : '#6b7280';
                      return (
                        <React.Fragment key={`${item.target_code}-${item.supplier_name}-${i}`}>
                          <tr style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb', borderTop: '1px solid #e5e7eb' }}>
                            <td style={{ ...tdStyle, color: '#9ca3af', fontSize: 12 }} rowSpan={isCombo && skuItems.length > 0 ? skuItems.length + 1 : 1}>
                              {i + 1}
                            </td>
                            <td style={tdStyle}>
                              <span style={{
                                padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                                background: isCombo ? '#ede9fe' : '#fef3c7',
                                color: isCombo ? '#7c3aed' : '#92400e',
                              }}>
                                {isCombo ? '조합' : 'SKU'}
                              </span>
                            </td>
                            {!supplierName && <td style={{ ...tdStyle, fontSize: 12, color: '#6b7280' }}>{item.supplier_name}</td>}
                            <td style={{ ...tdStyle, fontWeight: 600, maxWidth: 320 }}>
                              {isCombo
                                ? (
                                  <div>
                                    <span style={{ color: '#7c3aed' }}>📦 {skuItems.length}종 조합</span>
                                    <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                                      {skuItems.map(s => `${s.product_name?.slice(0, 12)}(x${s.qty})`).join(' + ')}
                                    </div>
                                  </div>
                                )
                                : <span title={item.target_name} style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.target_name}</span>
                              }
                            </td>
                            <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 12, color: '#374151' }}>
                              {isCombo ? '-' : (item.barcode || item.sku_code || '-')}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'center', fontSize: 13 }}>
                              {isCombo ? `${skuItems.length}종` : '1종'}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>
                              <div style={{ fontWeight: 800, fontSize: 16, color: '#2563eb' }}>
                                {item.predicted_qty.toLocaleString()}
                              </div>
                              {(item.stat_qty > 0 || item.ml_qty > 0) && item.predicted_qty !== item.stat_qty && (
                                <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 2 }}>
                                  통계:{item.stat_qty} {item.ml_qty > 0 && item.ml_qty !== item.stat_qty ? `ML:${item.ml_qty}` : ''}
                                </div>
                              )}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'center' }}>
                              <span style={{
                                display: 'inline-block', padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 700,
                                background: hasGpt ? '#f3e8ff' : hasMl ? '#dbeafe' : '#f3f4f6',
                                color: modelColor,
                              }}>
                                {modelLabel}
                              </span>
                              {item.gpt_reason && (
                                <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.gpt_reason}>
                                  {item.gpt_reason}
                                </div>
                              )}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'center' }}>
                              <span style={{
                                display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 700,
                                color: '#fff', background: confColor(item.confidence_score),
                              }}>
                                {(item.confidence_score * 100).toFixed(0)}%
                              </span>
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', fontSize: 13 }}>{item.frequency}일</td>
                          </tr>
                          {isCombo && skuItems.map((sku, si) => {
                            const needQty = (sku.qty || 1) * item.predicted_qty;
                            return (
                              <tr key={`${item.target_code}-sku-${si}`} style={{ background: i % 2 === 0 ? '#f0f4ff' : '#eef2ff' }}>
                                <td style={{ ...tdStyle, paddingLeft: 24, fontSize: 12, color: '#6b7280' }}>
                                  └
                                </td>
                                {!supplierName && <td style={tdStyle} />}
                                <td style={{ ...tdStyle, fontSize: 12, color: '#374151' }} title={`${sku.product_name} ${sku.option_name}`.trim()}>
                                  <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280 }}>
                                    {sku.product_name}{sku.option_name ? ` / ${sku.option_name}` : ''}
                                  </span>
                                </td>
                                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 12, color: '#374151' }}>
                                  {sku.barcode || sku.sku_code || '-'}
                                </td>
                                <td style={{ ...tdStyle, textAlign: 'center', fontSize: 12, color: '#6b7280' }}>
                                  x{sku.qty}
                                </td>
                                <td style={{ ...tdStyle, textAlign: 'right' }}>
                                  <span style={{ fontWeight: 700, fontSize: 14, color: '#059669' }}>
                                    {needQty.toLocaleString()}개
                                  </span>
                                  <span style={{ fontSize: 10, color: '#9ca3af', marginLeft: 4 }}>
                                    ({sku.qty}x{item.predicted_qty})
                                  </span>
                                </td>
                                <td colSpan={3} style={tdStyle} />
                              </tr>
                            );
                          })}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {!loading && result && result.total_items === 0 && (
        <Empty message="예측 데이터가 없습니다. 배송통계 파일을 업로드한 후 다시 시도해주세요." />
      )}

      {!loading && !result && (
        <div style={{ ...card, textAlign: 'center', padding: '48px 20px' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📋</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#374151', marginBottom: 8 }}>프리패킹 작업 지시서</div>
          <div style={{ fontSize: 14, color: '#9ca3af', maxWidth: 400, margin: '0 auto' }}>
            날짜를 선택하고 &quot;작업지시 생성&quot; 버튼을 누르면<br />
            해당 요일 기반으로 준비해야 할 조합과 수량을 예측합니다.
          </div>
        </div>
      )}
    </>
  );
}

// ===========================================================================
// TAB: 실행
// ===========================================================================
function ExecuteTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = tomorrow.toISOString().slice(0, 10);

  const [targetDate, setTargetDate] = useState(tomorrowStr);
  const [workItems, setWorkItems] = useState<WorkOrderItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [qtyMap, setQtyMap] = useState<Record<string, string>>({});
  const [submittingKey, setSubmittingKey] = useState('');
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [histLoading, setHistLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'work' | 'history'>('work');

  const loadWork = async () => {
    setLoading(true);
    try {
      const data = await ppFetch<WorkOrderResult>('/pp/recommendations/work-order', {
        method: 'POST',
        body: JSON.stringify({ target_date: targetDate, supplier_name: supplierName }),
      });
      setWorkItems(data.items || []);
      const initQty: Record<string, string> = {};
      (data.items || []).forEach((it, i) => {
        initQty[`${it.target_code || it.target_name}-${i}`] = String(it.predicted_qty);
      });
      setQtyMap(initQty);
      if (data.total_items === 0) showToast('예측 항목이 없습니다.', 'info');
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '작업 목록 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = useCallback(async () => {
    if (!supplierName) return;
    setHistLoading(true);
    try {
      const data = await ppFetch<Execution[]>(`/pp/executions/?supplier_name=${encodeURIComponent(supplierName)}`);
      setExecutions(Array.isArray(data) ? data : []);
    } catch { /* ignore */ } finally {
      setHistLoading(false);
    }
  }, [supplierName]);

  useEffect(() => { if (viewMode === 'history') loadHistory(); }, [viewMode, loadHistory]);

  const handleExecute = async (item: WorkOrderItem, idx: number) => {
    const key = `${item.target_code || item.target_name}-${idx}`;
    const qty = Number(qtyMap[key] || 0);
    if (qty <= 0) { showToast('수량을 입력해주세요', 'error'); return; }
    setSubmittingKey(key);
    try {
      await ppFetch('/pp/executions/', {
        method: 'POST',
        body: JSON.stringify({
          recommendation_id: 0,
          executed_qty: qty,
          executed_by: 'user',
          location_code: '',
          memo: `${item.target_name} / ${item.supplier_name} / ${targetDate}`,
        }),
      });
      showToast(`${item.target_name} ${qty}개 실행 완료`, 'success');
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '실행 실패', 'error');
    } finally {
      setSubmittingKey('');
    }
  };

  return (
    <>
      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        <button onClick={() => setViewMode('work')} style={{
          padding: '8px 20px', border: viewMode === 'work' ? '2px solid #2563eb' : '1px solid #d1d5db',
          background: viewMode === 'work' ? '#eff6ff' : '#fff', color: viewMode === 'work' ? '#2563eb' : '#6b7280',
          borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
        }}>작업 실행</button>
        <button onClick={() => setViewMode('history')} style={{
          padding: '8px 20px', border: viewMode === 'history' ? '2px solid #2563eb' : '1px solid #d1d5db',
          background: viewMode === 'history' ? '#eff6ff' : '#fff', color: viewMode === 'history' ? '#2563eb' : '#6b7280',
          borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
        }}>실행 이력</button>
      </div>

      {viewMode === 'work' && (
        <>
          <div style={card}>
            <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700 }}>▶️ 프리패킹 실행</h3>
            <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6b7280' }}>
              작업지시서를 불러온 뒤, 각 항목의 수량을 확인하고 실행 버튼을 누르세요.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
              <div style={{ flex: '0 0 160px' }}>
                <label style={labelStyle}>대상일</label>
                <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} style={inputStyle} />
              </div>
              <button onClick={loadWork} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.6 : 1 }}>
                {loading ? '조회 중...' : '작업 목록 불러오기'}
              </button>
            </div>
          </div>

          {loading && <Spinner />}

          {!loading && workItems.length > 0 && (
            <div style={card}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>작업 목록 ({workItems.length}건)</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ ...thStyle, width: 36 }}>#</th>
                      <th style={thStyle}>유형</th>
                      <th style={thStyle}>상품/조합명</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>AI 예측</th>
                      <th style={{ ...thStyle, textAlign: 'center', width: 100 }}>실행 수량</th>
                      <th style={{ ...thStyle, textAlign: 'center', width: 80 }}>실행</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workItems.map((item, i) => {
                      const key = `${item.target_code || item.target_name}-${i}`;
                      const isCombo = item.target_type === 'combination';
                      const isBusy = submittingKey === key;
                      return (
                        <tr key={key} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb', borderTop: '1px solid #e5e7eb' }}>
                          <td style={{ ...tdStyle, color: '#9ca3af', fontSize: 12 }}>{i + 1}</td>
                          <td style={tdStyle}>
                            <span style={{
                              padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                              background: isCombo ? '#ede9fe' : '#fef3c7',
                              color: isCombo ? '#7c3aed' : '#92400e',
                            }}>
                              {isCombo ? '조합' : 'SKU'}
                            </span>
                          </td>
                          <td style={{ ...tdStyle, fontWeight: 600, maxWidth: 300 }}>
                            <span title={item.target_name} style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {item.target_name}
                            </span>
                            {item.barcode && <div style={{ fontSize: 11, color: '#9ca3af', fontFamily: 'monospace' }}>{item.barcode}</div>}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 800, fontSize: 16, color: '#2563eb' }}>
                            {item.predicted_qty.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'center' }}>
                            <input
                              type="number"
                              min={0}
                              value={qtyMap[key] || ''}
                              onChange={(e) => setQtyMap({ ...qtyMap, [key]: e.target.value })}
                              style={{ ...inputStyle, width: 80, textAlign: 'center', fontWeight: 700, margin: 0 }}
                            />
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'center' }}>
                            <button
                              onClick={() => handleExecute(item, i)}
                              disabled={isBusy}
                              style={{
                                padding: '6px 14px', border: 'none', borderRadius: 6,
                                background: isBusy ? '#d1d5db' : '#16a34a', color: '#fff',
                                fontSize: 12, fontWeight: 700, cursor: isBusy ? 'default' : 'pointer',
                              }}
                            >
                              {isBusy ? '...' : '실행'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!loading && workItems.length === 0 && (
            <div style={{ ...card, textAlign: 'center', padding: '48px 20px' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>▶️</div>
              <div style={{ fontSize: 15, color: '#6b7280' }}>대상일을 선택하고 &quot;작업 목록 불러오기&quot;를 눌러주세요.</div>
            </div>
          )}
        </>
      )}

      {viewMode === 'history' && (
        <div style={card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>실행 이력</h3>
            <button onClick={loadHistory} style={btnOutline}>새로고침</button>
          </div>
          {histLoading ? <Spinner /> : executions.length === 0 ? <Empty message="실행 이력이 없습니다." /> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>ID</th>
                    <th style={thStyle}>상품명</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>실행 수량</th>
                    <th style={thStyle}>실행자</th>
                    <th style={thStyle}>메모</th>
                    <th style={thStyle}>실행일</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((ex, i) => (
                    <tr key={ex.execution_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                      <td style={{ ...tdStyle, color: '#9ca3af', fontSize: 12 }}>{ex.execution_id}</td>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>{ex.target_name || ex.target_code}</td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#2563eb' }}>{ex.executed_qty}</td>
                      <td style={tdStyle}>{ex.executed_by}</td>
                      <td style={{ ...tdStyle, fontSize: 12, color: '#6b7280', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ex.memo || '-'}</td>
                      <td style={{ ...tdStyle, fontSize: 12 }}>{ex.executed_at?.slice(0, 16)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ===========================================================================
// TAB: 재고
// ===========================================================================
function StockTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [stock, setStock] = useState<StockItem[]>([]);
  const [summary, setSummary] = useState<StockSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [useForm, setUseForm] = useState<{ id: number; qty: string } | null>(null);

  const loadStock = useCallback(async () => {
    if (!supplierName) return;
    setLoading(true);
    try {
      const [s, sum] = await Promise.all([
        ppFetch<StockItem[]>(`/pp/stock/?supplier_name=${encodeURIComponent(supplierName)}`),
        ppFetch<StockSummary>(`/pp/stock/summary?supplier_name=${encodeURIComponent(supplierName)}`),
      ]);
      setStock(Array.isArray(s) ? s : []);
      setSummary(sum);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '재고 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [supplierName, showToast]);

  useEffect(() => { loadStock(); }, [loadStock]);

  const handleUse = async () => {
    if (!useForm) return;
    try {
      await ppFetch(`/pp/stock/${useForm.id}/use`, { method: 'PATCH', body: JSON.stringify({ use_qty: Number(useForm.qty) }) });
      showToast('사용 처리 완료', 'success');
      setUseForm(null);
      loadStock();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '사용 처리 실패', 'error');
    }
  };

  return (
    <>
      {summary && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div style={statCard('#2563eb')}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 재고량</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{summary.total_packed.toLocaleString()}</div>
          </div>
          <div style={statCard('#16a34a')}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>가용 수량</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{summary.total_available.toLocaleString()}</div>
          </div>
          <div style={statCard('#f59e0b')}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>로케이션 수</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{Object.keys(summary.by_location).length}</div>
          </div>
          <div style={statCard('#dc2626')}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>상태 종류</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{Object.keys(summary.by_status).length}</div>
          </div>
        </div>
      )}

      {/* Use stock modal */}
      {useForm && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>재고 사용 (ID: {useForm.id})</h3>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: '0 0 120px' }}>
              <label style={labelStyle}>사용 수량</label>
              <input type="number" value={useForm.qty} onChange={(e) => setUseForm({ ...useForm, qty: e.target.value })} style={inputStyle} />
            </div>
            <button onClick={handleUse} style={btnPrimary}>사용 처리</button>
            <button onClick={() => setUseForm(null)} style={btnOutline}>취소</button>
          </div>
        </div>
      )}

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>📦 활성 재고</h3>
          <button onClick={loadStock} style={btnOutline}>새로고침</button>
        </div>
        {loading ? <Spinner /> : stock.length === 0 ? <Empty message="재고 데이터가 없습니다." /> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>ID</th>
                  <th style={thStyle}>SKU</th>
                  <th style={thStyle}>상품명</th>
                  <th style={thStyle}>수량</th>
                  <th style={thStyle}>로케이션</th>
                  <th style={thStyle}>만료일</th>
                  <th style={thStyle}>작업</th>
                </tr>
              </thead>
              <tbody>
                {stock.map((s, i) => (
                  <tr key={s.prepack_stock_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                    <td style={tdStyle}>{s.prepack_stock_id}</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{s.target_code}</td>
                    <td style={tdStyle}>{s.target_name}</td>
                    <td style={{ ...tdStyle, fontWeight: 700 }}>{s.current_qty}</td>
                    <td style={tdStyle}>{s.location_code}</td>
                    <td style={tdStyle}>{s.expiry_at?.slice(0, 10) || '-'}</td>
                    <td style={tdStyle}>
                      <button onClick={() => setUseForm({ id: s.prepack_stock_id, qty: '' })} style={{ ...btnWarning, padding: '4px 10px', fontSize: 12 }}>사용</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {summary && Object.keys(summary.by_location).length > 0 && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>로케이션별 재고</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(summary.by_location).map(([locCode, qty]) => (
              <div key={locCode} style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{locCode || '미지정'}</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#111827' }}>{qty}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// ===========================================================================
// TAB: 로케이션
// ===========================================================================
function LocationTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(false);
  const [zone, setZone] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ location_code: '', location_name: '', zone: '', location_type: 'shelf', max_capacity: '100' });
  const [moveForm, setMoveForm] = useState({ stock_id: '', from_location: '', to_location: '', qty: '', moved_by: '', reason: '' });
  const [showMove, setShowMove] = useState(false);

  const loadLocations = useCallback(async () => {
    setLoading(true);
    try {
      let q = '?active_only=true';
      if (zone) q += `&zone=${encodeURIComponent(zone)}`;
      const data = await ppFetch<Location[]>(`/pp/locations/${q}`);
      setLocations(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '로케이션 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [zone, showToast]);

  useEffect(() => { loadLocations(); }, [loadLocations]);

  const handleCreate = async () => {
    try {
      await ppFetch('/pp/locations/', {
        method: 'POST',
        body: JSON.stringify({ ...createForm, max_capacity: Number(createForm.max_capacity) }),
      });
      showToast('로케이션 생성 완료', 'success');
      setShowCreate(false);
      setCreateForm({ location_code: '', location_name: '', zone: '', location_type: 'shelf', max_capacity: '100' });
      loadLocations();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '생성 실패', 'error');
    }
  };

  const handleMove = async () => {
    try {
      await ppFetch('/pp/locations/move', {
        method: 'POST',
        body: JSON.stringify({
          stock_id: Number(moveForm.stock_id),
          from_location: moveForm.from_location,
          to_location: moveForm.to_location,
          qty: Number(moveForm.qty),
          moved_by: moveForm.moved_by || 'user',
          reason: moveForm.reason,
        }),
      });
      showToast('이동 완료', 'success');
      setShowMove(false);
      setMoveForm({ stock_id: '', from_location: '', to_location: '', qty: '', moved_by: '', reason: '' });
      loadLocations();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '이동 실패', 'error');
    }
  };

  void supplierName;

  return (
    <>
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>📍 로케이션 관리</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setShowCreate(!showCreate)} style={btnPrimary}>{showCreate ? '취소' : '+ 로케이션 추가'}</button>
            <button onClick={() => setShowMove(!showMove)} style={btnSuccess}>{showMove ? '취소' : '재고 이동'}</button>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 12 }}>
          <div style={{ flex: '0 0 160px' }}>
            <label style={labelStyle}>구역 필터</label>
            <input value={zone} onChange={(e) => setZone(e.target.value)} placeholder="구역명" style={inputStyle} />
          </div>
          <button onClick={loadLocations} style={btnOutline}>조회</button>
        </div>
      </div>

      {showCreate && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>로케이션 추가</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: '0 0 120px' }}>
              <label style={labelStyle}>코드</label>
              <input value={createForm.location_code} onChange={(e) => setCreateForm({ ...createForm, location_code: e.target.value })} placeholder="A-01" style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 140px' }}>
              <label style={labelStyle}>이름</label>
              <input value={createForm.location_name} onChange={(e) => setCreateForm({ ...createForm, location_name: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>구역</label>
              <input value={createForm.zone} onChange={(e) => setCreateForm({ ...createForm, zone: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 120px' }}>
              <label style={labelStyle}>유형</label>
              <select value={createForm.location_type} onChange={(e) => setCreateForm({ ...createForm, location_type: e.target.value })} style={inputStyle}>
                <option value="shelf">선반</option>
                <option value="pallet">파레트</option>
                <option value="floor">바닥</option>
                <option value="bin">빈</option>
              </select>
            </div>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>최대 용량</label>
              <input type="number" value={createForm.max_capacity} onChange={(e) => setCreateForm({ ...createForm, max_capacity: e.target.value })} style={inputStyle} />
            </div>
            <button onClick={handleCreate} style={btnPrimary}>생성</button>
          </div>
        </div>
      )}

      {showMove && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>재고 이동</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>재고 ID</label>
              <input type="number" value={moveForm.stock_id} onChange={(e) => setMoveForm({ ...moveForm, stock_id: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 120px' }}>
              <label style={labelStyle}>출발</label>
              <input value={moveForm.from_location} onChange={(e) => setMoveForm({ ...moveForm, from_location: e.target.value })} placeholder="A-01" style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 120px' }}>
              <label style={labelStyle}>도착</label>
              <input value={moveForm.to_location} onChange={(e) => setMoveForm({ ...moveForm, to_location: e.target.value })} placeholder="B-02" style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 80px' }}>
              <label style={labelStyle}>수량</label>
              <input type="number" value={moveForm.qty} onChange={(e) => setMoveForm({ ...moveForm, qty: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>이동자</label>
              <input value={moveForm.moved_by} onChange={(e) => setMoveForm({ ...moveForm, moved_by: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '1 1 140px' }}>
              <label style={labelStyle}>사유</label>
              <input value={moveForm.reason} onChange={(e) => setMoveForm({ ...moveForm, reason: e.target.value })} style={inputStyle} />
            </div>
            <button onClick={handleMove} style={btnSuccess}>이동</button>
          </div>
        </div>
      )}

      <div style={card}>
        {loading ? <Spinner /> : locations.length === 0 ? <Empty message="로케이션이 없습니다." /> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>코드</th>
                  <th style={thStyle}>이름</th>
                  <th style={thStyle}>구역</th>
                  <th style={thStyle}>유형</th>
                  <th style={thStyle}>용량</th>
                  <th style={thStyle}>현재 수량</th>
                  <th style={thStyle}>사용률</th>
                </tr>
              </thead>
              <tbody>
                {locations.map((loc, i) => {
                  const usage = loc.max_capacity > 0 ? loc.current_capacity / loc.max_capacity : 0;
                  return (
                    <tr key={loc.location_code} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>{loc.location_code}</td>
                      <td style={tdStyle}>{loc.location_name}</td>
                      <td style={tdStyle}>{loc.location_zone}</td>
                      <td style={tdStyle}>{loc.location_type}</td>
                      <td style={tdStyle}>{loc.max_capacity}</td>
                      <td style={tdStyle}>{loc.current_capacity}</td>
                      <td style={{ ...tdStyle, minWidth: 120 }}>
                        <ConfidenceBar value={usage} color={usage > 0.9 ? '#dc2626' : usage > 0.7 ? '#f59e0b' : '#16a34a'} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

// ===========================================================================
// TAB: 검증
// ===========================================================================
function ValidationTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [targetDate, setTargetDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [filterType, setFilterType] = useState<'all' | 'matched' | 'over' | 'under' | 'missed'>('all');

  const runBacktest = async () => {
    if (!supplierName) { showToast('공급처를 선택해주세요', 'error'); return; }
    if (!targetDate) { showToast('검증할 과거 날짜를 선택해주세요', 'error'); return; }
    setLoading(true);
    setResult(null);
    try {
      const data = await ppFetch<BacktestResult>('/pp/validation/backtest', {
        method: 'POST',
        body: JSON.stringify({ supplier_name: supplierName, target_date: targetDate }),
      });
      setResult(data);
      showToast(`백테스트 완료 — 정확도 ${data.summary.accuracy}%`, 'success');
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '백테스트 실패', 'error');
    } finally {
      setLoading(false);
    }
  };

  const filtered = result ? [
    ...(filterType === 'all' ? result.items : result.items.filter(it => it.result_type === filterType)),
    ...(filterType === 'all' || filterType === 'missed' ? result.missed_items : []),
  ] : [];

  const resultColor = (type: string) => {
    switch (type) {
      case 'matched': return { bg: '#d1fae5', fg: '#065f46', label: '정확' };
      case 'over': return { bg: '#fef3c7', fg: '#92400e', label: '과다' };
      case 'under': return { bg: '#fee2e2', fg: '#991b1b', label: '과소' };
      case 'missed': return { bg: '#f3f4f6', fg: '#6b7280', label: '미예측' };
      default: return { bg: '#f3f4f6', fg: '#6b7280', label: type };
    }
  };

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700 }}>🔬 예측 백테스트</h3>
        <p style={{ margin: '0 0 16px', fontSize: 13, color: '#6b7280' }}>
          과거 특정일을 선택하면, 그 날의 예측값과 실제 출하 데이터를 비교하여 예측 정확도를 검증합니다.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 180px' }}>
            <label style={labelStyle}>검증 대상일 (과거)</label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              max={new Date(Date.now() - 86400000).toISOString().slice(0, 10)}
              style={inputStyle}
            />
          </div>
          <button onClick={runBacktest} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.6 : 1 }}>
            {loading ? '분석 중...' : '백테스트 실행'}
          </button>
        </div>
      </div>

      {loading && <Spinner />}

      {!loading && result && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
            <div style={{ ...card, borderLeft: `4px solid ${result.summary.accuracy >= 80 ? '#16a34a' : result.summary.accuracy >= 50 ? '#f59e0b' : '#dc2626'}`, flex: '1 1 200px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>예측 정확도</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: result.summary.accuracy >= 80 ? '#16a34a' : result.summary.accuracy >= 50 ? '#f59e0b' : '#dc2626' }}>
                {result.summary.accuracy}%
              </div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>MAPE {result.summary.avg_mape}%</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #2563eb', flex: '1 1 140px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>{result.target_date} ({result.weekday_name})</div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 4 }}>
                <div>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>예측</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#2563eb' }}>{result.summary.total_predicted.toLocaleString()}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>실제</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#111827' }}>{result.summary.total_actual.toLocaleString()}</div>
                </div>
              </div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #16a34a', flex: '1 1 90px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>정확</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#16a34a' }}>{result.summary.matched}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #f59e0b', flex: '1 1 90px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>과다</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#f59e0b' }}>{result.summary.over}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #dc2626', flex: '1 1 90px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>과소</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#dc2626' }}>{result.summary.under}</div>
            </div>
            <div style={{ ...card, borderLeft: '4px solid #6b7280', flex: '1 1 90px', marginBottom: 0, textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>미예측</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#6b7280' }}>{result.summary.missed}</div>
            </div>
          </div>

          {/* Model usage */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, fontSize: 12 }}>
            <span style={{ padding: '4px 10px', borderRadius: 12, background: '#dbeafe', color: '#2563eb', fontWeight: 600 }}>
              ML {result.summary.ml_count}건
            </span>
            <span style={{ padding: '4px 10px', borderRadius: 12, background: '#f3f4f6', color: '#6b7280', fontWeight: 600 }}>
              통계 {result.summary.stat_count}건
            </span>
          </div>

          {/* Detail table */}
          <div style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>상세 비교 ({filtered.length}건)</h3>
              <div style={{ display: 'flex', gap: 4 }}>
                {([['all', '전체'], ['matched', '정확'], ['over', '과다'], ['under', '과소'], ['missed', '미예측']] as const).map(([k, label]) => (
                  <button
                    key={k}
                    onClick={() => setFilterType(k)}
                    style={{
                      padding: '5px 12px', border: filterType === k ? '1px solid #2563eb' : '1px solid #d1d5db',
                      background: filterType === k ? '#eff6ff' : '#fff', color: filterType === k ? '#2563eb' : '#6b7280',
                      borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    }}
                  >{label}</button>
                ))}
              </div>
            </div>

            {filtered.length === 0 ? <Empty message="해당 조건의 항목이 없습니다." /> : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ ...thStyle, width: 36 }}>#</th>
                      <th style={thStyle}>결과</th>
                      <th style={thStyle}>유형</th>
                      <th style={thStyle}>상품/조합명</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>예측</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>실제</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>오차</th>
                      <th style={{ ...thStyle, textAlign: 'center' }}>오차율</th>
                      <th style={{ ...thStyle, textAlign: 'center' }}>모델</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((item, i) => {
                      const rc = resultColor(item.result_type);
                      return (
                        <tr key={`${item.target_name}-${i}`} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb', borderTop: '1px solid #e5e7eb' }}>
                          <td style={{ ...tdStyle, color: '#9ca3af', fontSize: 12 }}>{i + 1}</td>
                          <td style={tdStyle}>
                            <span style={{ padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 700, background: rc.bg, color: rc.fg }}>
                              {rc.label}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={{
                              padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                              background: item.target_type === 'combination' ? '#ede9fe' : item.target_type === 'missed' ? '#f3f4f6' : '#fef3c7',
                              color: item.target_type === 'combination' ? '#7c3aed' : item.target_type === 'missed' ? '#6b7280' : '#92400e',
                            }}>
                              {item.target_type === 'combination' ? '조합' : item.target_type === 'missed' ? '-' : 'SKU'}
                            </span>
                          </td>
                          <td style={{ ...tdStyle, fontWeight: 600, maxWidth: 280 }}>
                            <span title={`${item.target_name} ${item.option_name || ''}`.trim()} style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {item.target_name}{item.option_name ? ` / ${item.option_name}` : ''}
                            </span>
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, fontSize: 15, color: '#2563eb' }}>
                            {item.predicted_qty.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, fontSize: 15, color: '#111827' }}>
                            {item.actual_qty.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: item.error_abs === 0 ? '#16a34a' : '#dc2626' }}>
                            {item.result_type === 'over' ? '+' : item.result_type === 'under' ? '-' : ''}{item.error_abs}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'center' }}>
                            <span style={{
                              display: 'inline-block', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 700,
                              background: item.error_pct <= 10 ? '#d1fae5' : item.error_pct <= 30 ? '#fef3c7' : '#fee2e2',
                              color: item.error_pct <= 10 ? '#065f46' : item.error_pct <= 30 ? '#92400e' : '#991b1b',
                            }}>
                              {item.error_pct}%
                            </span>
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'center' }}>
                            {item.model_type ? (
                              <span style={{
                                padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 700,
                                background: item.model_type === 'ml' ? '#dbeafe' : '#f3f4f6',
                                color: item.model_type === 'ml' ? '#2563eb' : '#6b7280',
                              }}>
                                {item.model_type === 'ml' ? 'ML' : '통계'}
                              </span>
                            ) : '-'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}

// ===========================================================================
// TAB: 리포트
// ===========================================================================
function ReportTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [subTab, setSubTab] = useState<'overview' | 'validation' | 'ai'>('overview');
  const [days, setDays] = useState(30);
  const [overview, setOverview] = useState<OverviewReport | null>(null);
  const [valReport, setValReport] = useState<ValidationReport | null>(null);
  const [aiReport, setAiReport] = useState<AiUsageReport | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (subTab === 'overview' && supplierName) {
        const data = await ppFetch<OverviewReport>(`/pp/reports/overview?supplier_name=${encodeURIComponent(supplierName)}&days=${days}`);
        setOverview(data);
      } else if (subTab === 'validation' && supplierName) {
        const data = await ppFetch<ValidationReport>(`/pp/reports/validation?supplier_name=${encodeURIComponent(supplierName)}&days=${days}`);
        setValReport(data);
      } else if (subTab === 'ai') {
        const data = await ppFetch<AiUsageReport>(`/pp/reports/ai-usage?days=${days}`);
        setAiReport(data);
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '리포트 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [subTab, supplierName, days, showToast]);

  useEffect(() => { load(); }, [load]);

  const subTabs: { key: 'overview' | 'validation' | 'ai'; label: string }[] = [
    { key: 'overview', label: '종합 리포트' },
    { key: 'validation', label: '검증 리포트' },
    { key: 'ai', label: 'AI 사용량' },
  ];

  return (
    <>
      <div style={card}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>📋 리포트</h3>
          <div style={{ display: 'flex', gap: 4 }}>
            {subTabs.map((st) => (
              <button
                key={st.key}
                onClick={() => setSubTab(st.key)}
                style={{
                  padding: '6px 14px',
                  border: subTab === st.key ? '1px solid #2563eb' : '1px solid #d1d5db',
                  background: subTab === st.key ? '#eff6ff' : '#fff',
                  color: subTab === st.key ? '#2563eb' : '#6b7280',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {st.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#6b7280' }}>기간</label>
            <input type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} min={1} style={{ ...inputStyle, width: 80 }} />
            <span style={{ fontSize: 13, color: '#6b7280' }}>일</span>
          </div>
        </div>
      </div>

      {loading ? <Spinner /> : (
        <>
          {subTab === 'overview' && overview && (
            <>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                <div style={statCard('#2563eb')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 추천</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{overview.total_recommendations}</div>
                </div>
                <div style={statCard('#16a34a')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>승인</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{overview.approved_count}</div>
                </div>
                <div style={statCard('#dc2626')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>거절</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#dc2626' }}>{overview.rejected_count}</div>
                </div>
                <div style={statCard('#f59e0b')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>실행</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{overview.executed_count}</div>
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                <div style={statCard('#2563eb')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>생산 수량</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{overview.total_produced_qty.toLocaleString()}</div>
                </div>
                <div style={statCard('#16a34a')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>사용 수량</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{overview.total_used_qty.toLocaleString()}</div>
                </div>
                <div style={statCard('#f59e0b')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>활용률</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{(overview.utilization_rate * 100).toFixed(1)}%</div>
                </div>
                <div style={statCard('#16a34a')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>평균 신뢰도</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{(overview.avg_confidence * 100).toFixed(1)}%</div>
                </div>
              </div>
            </>
          )}

          {subTab === 'validation' && valReport && (
            <>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                <div style={statCard('#2563eb')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>평균 정확도</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: valReport.avg_accuracy >= 0.8 ? '#16a34a' : '#f59e0b' }}>
                    {(valReport.avg_accuracy * 100).toFixed(1)}%
                  </div>
                </div>
                <div style={statCard('#16a34a')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 검증</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{valReport.total_validated}</div>
                </div>
                <div style={statCard('#f59e0b')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>MAPE</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{(valReport.avg_mape * 100).toFixed(1)}%</div>
                </div>
                <div style={statCard('#dc2626')}>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>해체율</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#dc2626' }}>{(valReport.unwrap_rate * 100).toFixed(1)}%</div>
                </div>
              </div>

              <div style={card}>
                <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>결과별 분포</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                  {Object.entries(valReport.by_result).map(([result, count]) => (
                    <div key={result} style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 20px', textAlign: 'center' }}>
                      <Badge status={result} />
                      <div style={{ fontSize: 24, fontWeight: 800, marginTop: 8 }}>{count}</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {subTab === 'ai' && aiReport && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              <div style={statCard('#2563eb')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 호출</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{aiReport.total_calls.toLocaleString()}</div>
              </div>
              <div style={statCard('#16a34a')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 토큰</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{aiReport.total_tokens.toLocaleString()}</div>
              </div>
              <div style={statCard('#f59e0b')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 비용 (USD)</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>${aiReport.total_cost.toFixed(4)}</div>
              </div>
              <div style={statCard('#dc2626')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>평균 지연 (ms)</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{aiReport.avg_latency.toFixed(0)}</div>
              </div>
              <div style={statCard('#16a34a')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>성공률</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{(aiReport.success_rate * 100).toFixed(1)}%</div>
              </div>
            </div>
          )}

          {!loading && !overview && subTab === 'overview' && <Empty message="업체명을 입력하고 조회해주세요." />}
          {!loading && !valReport && subTab === 'validation' && <Empty message="업체명을 입력하고 조회해주세요." />}
          {!loading && !aiReport && subTab === 'ai' && <Empty message="AI 사용량 데이터가 없습니다." />}
        </>
      )}
    </>
  );
}

// ===========================================================================
// TAB: 설정
// ===========================================================================
function SettingsTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [newExclusion, setNewExclusion] = useState('');
  const [expiringDays, setExpiringDays] = useState(2);
  const [expiring, setExpiring] = useState<StockItem[]>([]);
  const [loadingExpiring, setLoadingExpiring] = useState(false);

  const [unwrapForm, setUnwrapForm] = useState({ stock_id: '', unwrap_qty: '', reason: '', return_to_stock: true, return_location: '', unwrap_by: '' });
  const [showUnwrap, setShowUnwrap] = useState(false);

  const addExclusion = () => {
    if (!newExclusion.trim()) return;
    if (exclusions.includes(newExclusion.trim())) { showToast('이미 등록된 SKU입니다', 'error'); return; }
    setExclusions([...exclusions, newExclusion.trim()]);
    setNewExclusion('');
    showToast('제외 SKU 추가됨 (로컬)', 'info');
  };

  const removeExclusion = (sku: string) => {
    setExclusions(exclusions.filter((e) => e !== sku));
    showToast('제외 SKU 제거됨 (로컬)', 'info');
  };

  const loadExpiring = async () => {
    setLoadingExpiring(true);
    try {
      const data = await ppFetch<StockItem[]>(`/pp/stock/expiring?days_ahead=${expiringDays}`);
      setExpiring(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '만료 임박 조회 실패', 'error');
    } finally {
      setLoadingExpiring(false);
    }
  };

  const handleUnwrap = async () => {
    try {
      await ppFetch('/pp/unwrap/', {
        method: 'POST',
        body: JSON.stringify({
          stock_id: Number(unwrapForm.stock_id),
          unwrap_qty: Number(unwrapForm.unwrap_qty),
          reason: unwrapForm.reason,
          return_to_stock: unwrapForm.return_to_stock,
          return_location: unwrapForm.return_location,
          unwrap_by: unwrapForm.unwrap_by || 'user',
        }),
      });
      showToast('언팩 처리 완료', 'success');
      setShowUnwrap(false);
      setUnwrapForm({ stock_id: '', unwrap_qty: '', reason: '', return_to_stock: true, return_location: '', unwrap_by: '' });
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '언팩 실패', 'error');
    }
  };

  void supplierName;

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>⚙️ 예외 관리 (제외 SKU)</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16 }}>
          <div style={{ flex: '1 1 200px' }}>
            <label style={labelStyle}>SKU 코드</label>
            <input value={newExclusion} onChange={(e) => setNewExclusion(e.target.value)} placeholder="제외할 SKU 입력" style={inputStyle}
              onKeyDown={(e) => { if (e.key === 'Enter') addExclusion(); }}
            />
          </div>
          <button onClick={addExclusion} style={btnPrimary}>추가</button>
        </div>
        {exclusions.length === 0 ? (
          <Empty message="등록된 제외 SKU가 없습니다." />
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {exclusions.map((sku) => (
              <div key={sku} style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#fef3c7', padding: '6px 12px', borderRadius: 20 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#92400e' }}>{sku}</span>
                <button
                  onClick={() => removeExclusion(sku)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', fontWeight: 700, fontSize: 14, padding: 0 }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>⏰ 만료 임박 재고</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16 }}>
          <div style={{ flex: '0 0 100px' }}>
            <label style={labelStyle}>기간 (일)</label>
            <input type="number" value={expiringDays} onChange={(e) => setExpiringDays(Number(e.target.value))} min={1} style={inputStyle} />
          </div>
          <button onClick={loadExpiring} style={btnWarning}>조회</button>
        </div>
        {loadingExpiring ? <Spinner /> : expiring.length === 0 ? (
          <Empty message="만료 임박 재고가 없습니다." />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>ID</th>
                  <th style={thStyle}>SKU</th>
                  <th style={thStyle}>상품명</th>
                  <th style={thStyle}>수량</th>
                  <th style={thStyle}>로케이션</th>
                  <th style={thStyle}>만료일</th>
                </tr>
              </thead>
              <tbody>
                {expiring.map((s, i) => (
                  <tr key={s.prepack_stock_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                    <td style={tdStyle}>{s.prepack_stock_id}</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{s.target_code}</td>
                    <td style={tdStyle}>{s.target_name}</td>
                    <td style={tdStyle}>{s.current_qty}</td>
                    <td style={tdStyle}>{s.location_code}</td>
                    <td style={{ ...tdStyle, color: '#dc2626', fontWeight: 600 }}>{s.expiry_at?.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>📦 언팩 (프리패킹 해제)</h3>
          <button onClick={() => setShowUnwrap(!showUnwrap)} style={btnDanger}>{showUnwrap ? '취소' : '언팩 등록'}</button>
        </div>
        {showUnwrap && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>재고 ID</label>
              <input type="number" value={unwrapForm.stock_id} onChange={(e) => setUnwrapForm({ ...unwrapForm, stock_id: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>수량</label>
              <input type="number" value={unwrapForm.unwrap_qty} onChange={(e) => setUnwrapForm({ ...unwrapForm, unwrap_qty: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '1 1 160px' }}>
              <label style={labelStyle}>사유</label>
              <input value={unwrapForm.reason} onChange={(e) => setUnwrapForm({ ...unwrapForm, reason: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 120px' }}>
              <label style={labelStyle}>반환 로케이션</label>
              <input value={unwrapForm.return_location} onChange={(e) => setUnwrapForm({ ...unwrapForm, return_location: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 100px' }}>
              <label style={labelStyle}>처리자</label>
              <input value={unwrapForm.unwrap_by} onChange={(e) => setUnwrapForm({ ...unwrapForm, unwrap_by: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ flex: '0 0 100px', display: 'flex', alignItems: 'center', gap: 6, paddingBottom: 2 }}>
              <input type="checkbox" checked={unwrapForm.return_to_stock} onChange={(e) => setUnwrapForm({ ...unwrapForm, return_to_stock: e.target.checked })} />
              <label style={{ fontSize: 13, color: '#374151' }}>재고 반환</label>
            </div>
            <button onClick={handleUnwrap} style={btnDanger}>언팩 실행</button>
          </div>
        )}
      </div>
    </>
  );
}
