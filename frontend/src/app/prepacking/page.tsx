'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function ppFetch<T = unknown>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers } as HeadersInit,
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `API Error ${res.status}`);
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

interface AccuracySummary {
  avg_accuracy: number;
  avg_mape: number;
  total_validated: number;
  matched_count: number;
  over_count: number;
  under_count: number;
  missed_count: number;
}

interface FailureAnalysis {
  total_failures: number;
  by_reason: Record<string, number>;
  top_failed_skus: { sku_or_name: string; error_weight: number }[];
  improvement_suggestions: string[];
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
  { key: 'recommend', label: '추천', icon: '💡' },
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
      if (!res.ok) throw new Error(await res.text());
      showToast('업로드 완료! 파일 내 공급처 정보가 자동 반영됩니다.', 'success');
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
            {uploading ? '업로드 중...' : '업로드'}
          </button>
        </div>
      </div>

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>업로드 이력</h3>
          <button onClick={loadUploads} style={btnOutline}>새로고침</button>
        </div>
        {loading ? (
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
                  <th style={thStyle}>업로더</th>
                  <th style={thStyle}>행 수</th>
                  <th style={thStyle}>적용</th>
                  <th style={thStyle}>메모</th>
                  <th style={thStyle}>업로드일</th>
                  <th style={thStyle}>작업</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((u, i) => (
                  <tr key={u.upload_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                    <td style={tdStyle}>{u.upload_id}</td>
                    <td style={tdStyle}>{u.file_name}</td>
                    <td style={tdStyle}>{u.uploaded_by}</td>
                    <td style={tdStyle}>{u.row_count?.toLocaleString()}</td>
                    <td style={tdStyle}>{u.applied_yn ? '적용' : '-'}</td>
                    <td style={tdStyle}>{u.note || '-'}</td>
                    <td style={tdStyle}>{u.uploaded_at?.slice(0, 16)}</td>
                    <td style={tdStyle}>
                      <button onClick={() => handleDelete(u.upload_id)} style={{ ...btnDanger, padding: '4px 10px', fontSize: 12 }}>삭제</button>
                    </td>
                  </tr>
                ))}
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
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [minCount, setMinCount] = useState(3);
  const [subTab, setSubTab] = useState<'skus' | 'combos' | 'weekday'>('skus');
  const [repeatSkus, setRepeatSkus] = useState<RepeatSku[]>([]);
  const [repeatCombos, setRepeatCombos] = useState<RepeatCombination[]>([]);
  const [weekday, setWeekday] = useState<WeekdayPattern[]>([]);
  const [loading, setLoading] = useState(false);

  const body = () => JSON.stringify({ supplier_name: supplierName, date_from: dateFrom, date_to: dateTo, min_count: minCount });

  const analyze = async (type: 'skus' | 'combos' | 'weekday') => {
    if (!supplierName) { showToast('업체명을 입력해주세요', 'error'); return; }
    setLoading(true);
    try {
      const ep = type === 'skus' ? '/pp/analysis/repeat-skus' : type === 'combos' ? '/pp/analysis/repeat-combinations' : '/pp/analysis/weekday-patterns';
      const data = await ppFetch<unknown>(ep, { method: 'POST', body: body() });
      if (type === 'skus') setRepeatSkus(data as RepeatSku[]);
      else if (type === 'combos') setRepeatCombos(data as RepeatCombination[]);
      else {
        const resp = data as WeekdayResponse;
        setWeekday(resp.sku_patterns || []);
      }
      setSubTab(type);
      showToast('분석 완료', 'success');
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '분석 실패', 'error');
    } finally {
      setLoading(false);
    }
  };

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
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>📊 분석 조건</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 160px' }}>
            <label style={labelStyle}>시작일</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 160px' }}>
            <label style={labelStyle}>종료일</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 100px' }}>
            <label style={labelStyle}>최소 횟수</label>
            <input type="number" value={minCount} onChange={(e) => setMinCount(Number(e.target.value))} min={1} style={inputStyle} />
          </div>
          <button onClick={() => analyze('skus')} disabled={loading} style={btnPrimary}>반복 SKU</button>
          <button onClick={() => analyze('combos')} disabled={loading} style={btnPrimary}>반복 조합</button>
          <button onClick={() => analyze('weekday')} disabled={loading} style={btnPrimary}>요일 패턴</button>
        </div>
      </div>

      {loading && <Spinner />}

      {!loading && subTab === 'skus' && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>반복 SKU 분석</h3>
          {repeatSkus.length === 0 ? <Empty message="분석 결과가 없습니다. 조건을 설정하고 분석을 실행해주세요." /> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>상품명</th>
                    <th style={thStyle}>옵션</th>
                    <th style={thStyle}>총 수량</th>
                    <th style={thStyle}>일평균</th>
                    <th style={thStyle}>첫 출고</th>
                    <th style={thStyle}>최근 출고</th>
                  </tr>
                </thead>
                <tbody>
                  {repeatSkus.map((s, i) => (
                    <tr key={`${s.sku_name}-${s.option_name}`} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>{s.sku_name}</td>
                      <td style={tdStyle}>{s.option_name || '-'}</td>
                      <td style={tdStyle}>{s.total_count.toLocaleString()}</td>
                      <td style={tdStyle}>{s.daily_avg.toFixed(1)}</td>
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

      {!loading && subTab === 'combos' && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>반복 조합 분석</h3>
          {repeatCombos.length === 0 ? <Empty message="분석 결과가 없습니다." /> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>조합 구성</th>
                    <th style={thStyle}>반복 횟수</th>
                    <th style={thStyle}>일평균</th>
                    <th style={thStyle}>첫 출고</th>
                    <th style={thStyle}>최근 출고</th>
                  </tr>
                </thead>
                <tbody>
                  {repeatCombos.map((c, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                      <td style={tdStyle}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {c.items.map((item, idx) => (
                            <span key={idx} style={{ background: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                              {item.product_name || item.sku_code} x{item.qty}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={tdStyle}>{c.total_count}</td>
                      <td style={tdStyle}>{c.daily_avg.toFixed(1)}</td>
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

      {!loading && subTab === 'weekday' && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>요일별 패턴 (히트맵)</h3>
          {weekday.length === 0 ? <Empty message="분석 결과가 없습니다." /> : (
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
                              <div
                                style={{
                                  display: 'inline-block',
                                  width: 36,
                                  height: 28,
                                  lineHeight: '28px',
                                  borderRadius: 6,
                                  fontSize: 12,
                                  fontWeight: 600,
                                  background: heatColor(v, maxVal),
                                  color: maxVal > 0 && v / maxVal > 0.6 ? '#fff' : '#374151',
                                }}
                              >
                                {v}
                              </div>
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
  );
}

// ===========================================================================
// TAB: 추천
// ===========================================================================
function RecommendTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [targetDate, setTargetDate] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const loadRecs = useCallback(async () => {
    if (!supplierName) return;
    setLoading(true);
    try {
      let q = `?supplier_name=${encodeURIComponent(supplierName)}`;
      if (targetDate) q += `&target_date=${targetDate}`;
      if (statusFilter) q += `&status=${statusFilter}`;
      const data = await ppFetch<Recommendation[]>(`/pp/recommendations/${q}`);
      setRecs(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '추천 목록 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [supplierName, targetDate, statusFilter, showToast]);

  useEffect(() => { loadRecs(); }, [loadRecs]);

  const generate = async () => {
    if (!supplierName || !targetDate) { showToast('업체명과 대상일자를 입력해주세요', 'error'); return; }
    setGenerating(true);
    try {
      await ppFetch('/pp/recommendations/generate', { method: 'POST', body: JSON.stringify({ supplier_name: supplierName, target_date: targetDate }) });
      showToast('추천 생성 완료', 'success');
      loadRecs();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '추천 생성 실패', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleAction = async (id: number, action: string) => {
    const reason = prompt(`사유를 입력해주세요 (${action})`);
    if (reason === null) return;
    try {
      await ppFetch(`/pp/recommendations/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ action_type: action, reason, by: 'user', memo: '' }),
      });
      showToast(`${action} 처리 완료`, 'success');
      loadRecs();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '처리 실패', 'error');
    }
  };

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>💡 추천 생성 및 조회</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 160px' }}>
            <label style={labelStyle}>대상 일자</label>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 140px' }}>
            <label style={labelStyle}>상태 필터</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={inputStyle}>
              <option value="">전체</option>
              <option value="recommended">추천</option>
              <option value="approved">승인</option>
              <option value="modified">수정</option>
              <option value="held">보류</option>
              <option value="rejected">거절</option>
              <option value="executed">실행됨</option>
            </select>
          </div>
          <button onClick={generate} disabled={generating} style={{ ...btnSuccess, opacity: generating ? 0.6 : 1 }}>
            {generating ? '생성 중...' : '추천 생성'}
          </button>
          <button onClick={loadRecs} style={btnOutline}>조회</button>
        </div>
      </div>

      <div style={card}>
        <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>추천 목록</h3>
        {loading ? <Spinner /> : recs.length === 0 ? <Empty message="추천 내역이 없습니다. 추천을 생성해주세요." /> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>ID</th>
                  <th style={thStyle}>SKU</th>
                  <th style={thStyle}>상품명</th>
                  <th style={thStyle}>추천 수량</th>
                  <th style={thStyle}>신뢰도</th>
                  <th style={thStyle}>리스크</th>
                  <th style={thStyle}>사유</th>
                  <th style={thStyle}>상태</th>
                  <th style={thStyle}>작업</th>
                </tr>
              </thead>
              <tbody>
                {recs.map((r, i) => (
                  <tr key={r.recommendation_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                    <td style={tdStyle}>{r.recommendation_id}</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{r.target_code}</td>
                    <td style={tdStyle}>{r.target_name}</td>
                    <td style={{ ...tdStyle, fontWeight: 700, color: '#2563eb' }}>{r.predicted_qty}</td>
                    <td style={{ ...tdStyle, minWidth: 120 }}>
                      <ConfidenceBar value={r.confidence_score} color="#16a34a" />
                    </td>
                    <td style={{ ...tdStyle, minWidth: 120 }}>
                      <ConfidenceBar value={r.risk_score} color={r.risk_score > 0.7 ? '#dc2626' : r.risk_score > 0.4 ? '#f59e0b' : '#16a34a'} />
                    </td>
                    <td style={{ ...tdStyle, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.recommendation_reason}>{r.recommendation_reason}</td>
                    <td style={tdStyle}><Badge status={r.status} /></td>
                    <td style={tdStyle}>
                      {(r.status === 'recommended' || r.status === 'pending') && (
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button onClick={() => handleAction(r.recommendation_id, 'approve')} style={{ ...btnSuccess, padding: '4px 8px', fontSize: 11 }}>승인</button>
                          <button onClick={() => handleAction(r.recommendation_id, 'hold')} style={{ ...btnWarning, padding: '4px 8px', fontSize: 11 }}>보류</button>
                          <button onClick={() => handleAction(r.recommendation_id, 'reject')} style={{ ...btnDanger, padding: '4px 8px', fontSize: 11 }}>거절</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

// ===========================================================================
// TAB: 실행
// ===========================================================================
function ExecuteTab({ supplierName, showToast }: { supplierName: string; showToast: (m: string, t: 'success' | 'error' | 'info') => void }) {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ recommendation_id: '', executed_qty: '', executed_by: '', location_code: '', memo: '' });
  const [submitting, setSubmitting] = useState(false);

  const loadExecs = useCallback(async () => {
    if (!supplierName) return;
    setLoading(true);
    try {
      const data = await ppFetch<Execution[]>(`/pp/executions/?supplier_name=${encodeURIComponent(supplierName)}`);
      setExecutions(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '실행 이력 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [supplierName, showToast]);

  useEffect(() => { loadExecs(); }, [loadExecs]);

  const handleExecute = async () => {
    if (!form.recommendation_id || !form.executed_qty) { showToast('추천 ID와 실행 수량을 입력해주세요', 'error'); return; }
    setSubmitting(true);
    try {
      await ppFetch('/pp/executions/', {
        method: 'POST',
        body: JSON.stringify({
          recommendation_id: Number(form.recommendation_id),
          executed_qty: Number(form.executed_qty),
          executed_by: form.executed_by || 'user',
          location_code: form.location_code,
          memo: form.memo,
        }),
      });
      showToast('실행 완료', 'success');
      setForm({ recommendation_id: '', executed_qty: '', executed_by: '', location_code: '', memo: '' });
      loadExecs();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '실행 실패', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>▶️ 실행 등록</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 120px' }}>
            <label style={labelStyle}>추천 ID</label>
            <input type="number" value={form.recommendation_id} onChange={(e) => setForm({ ...form, recommendation_id: e.target.value })} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 100px' }}>
            <label style={labelStyle}>실행 수량</label>
            <input type="number" value={form.executed_qty} onChange={(e) => setForm({ ...form, executed_qty: e.target.value })} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 120px' }}>
            <label style={labelStyle}>실행자</label>
            <input value={form.executed_by} onChange={(e) => setForm({ ...form, executed_by: e.target.value })} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 120px' }}>
            <label style={labelStyle}>로케이션</label>
            <input value={form.location_code} onChange={(e) => setForm({ ...form, location_code: e.target.value })} placeholder="예: A-01" style={inputStyle} />
          </div>
          <div style={{ flex: '1 1 160px' }}>
            <label style={labelStyle}>메모</label>
            <input value={form.memo} onChange={(e) => setForm({ ...form, memo: e.target.value })} style={inputStyle} />
          </div>
          <button onClick={handleExecute} disabled={submitting} style={{ ...btnPrimary, opacity: submitting ? 0.6 : 1 }}>
            {submitting ? '처리 중...' : '실행'}
          </button>
        </div>
      </div>

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>실행 이력</h3>
          <button onClick={loadExecs} style={btnOutline}>새로고침</button>
        </div>
        {loading ? <Spinner /> : executions.length === 0 ? <Empty message="실행 이력이 없습니다." /> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>ID</th>
                  <th style={thStyle}>추천 ID</th>
                  <th style={thStyle}>SKU</th>
                  <th style={thStyle}>상품명</th>
                  <th style={thStyle}>실행 수량</th>
                  <th style={thStyle}>실행자</th>
                  <th style={thStyle}>상태</th>
                  <th style={thStyle}>메모</th>
                  <th style={thStyle}>실행일</th>
                </tr>
              </thead>
              <tbody>
                {executions.map((ex, i) => (
                  <tr key={ex.execution_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                    <td style={tdStyle}>{ex.execution_id}</td>
                    <td style={tdStyle}>{ex.recommendation_id}</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{ex.target_code}</td>
                    <td style={tdStyle}>{ex.target_name}</td>
                    <td style={{ ...tdStyle, fontWeight: 700, color: '#2563eb' }}>{ex.executed_qty}</td>
                    <td style={tdStyle}>{ex.executed_by}</td>
                    <td style={tdStyle}>{ex.execution_status}</td>
                    <td style={tdStyle}>{ex.memo || '-'}</td>
                    <td style={tdStyle}>{ex.executed_at?.slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
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
  const [accuracy, setAccuracy] = useState<AccuracySummary | null>(null);
  const [failures, setFailures] = useState<FailureAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [targetDate, setTargetDate] = useState('');
  const [days, setDays] = useState(30);

  const loadData = useCallback(async () => {
    if (!supplierName) return;
    setLoading(true);
    try {
      const [acc, fail] = await Promise.all([
        ppFetch<AccuracySummary>(`/pp/validation/accuracy?supplier_name=${encodeURIComponent(supplierName)}&days=${days}`),
        ppFetch<FailureAnalysis>(`/pp/validation/failures?supplier_name=${encodeURIComponent(supplierName)}&days=${days}`),
      ]);
      setAccuracy(acc);
      setFailures(fail);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '검증 데이터 조회 실패', 'error');
    } finally {
      setLoading(false);
    }
  }, [supplierName, days, showToast]);

  useEffect(() => { loadData(); }, [loadData]);

  const runValidation = async () => {
    if (!supplierName || !targetDate) { showToast('업체명과 대상일자를 입력해주세요', 'error'); return; }
    setRunning(true);
    try {
      await ppFetch('/pp/validation/run', { method: 'POST', body: JSON.stringify({ supplier_name: supplierName, target_date: targetDate }) });
      showToast('검증 실행 완료', 'success');
      loadData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '검증 실행 실패', 'error');
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <div style={card}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>✅ 예측 검증</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: '0 0 160px' }}>
            <label style={labelStyle}>대상 일자</label>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ flex: '0 0 100px' }}>
            <label style={labelStyle}>조회 기간 (일)</label>
            <input type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} min={1} style={inputStyle} />
          </div>
          <button onClick={runValidation} disabled={running} style={{ ...btnPrimary, opacity: running ? 0.6 : 1 }}>
            {running ? '실행 중...' : '검증 실행'}
          </button>
          <button onClick={loadData} style={btnOutline}>조회</button>
        </div>
      </div>

      {loading ? <Spinner /> : (
        <>
          {accuracy && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              <div style={statCard('#2563eb')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>평균 정확도</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: accuracy.avg_accuracy >= 0.8 ? '#16a34a' : accuracy.avg_accuracy >= 0.5 ? '#f59e0b' : '#dc2626' }}>
                  {(accuracy.avg_accuracy * 100).toFixed(1)}%
                </div>
              </div>
              <div style={statCard('#16a34a')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>총 검증</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#111827' }}>{accuracy.total_validated}</div>
              </div>
              <div style={statCard('#16a34a')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>정확</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#16a34a' }}>{accuracy.matched_count}</div>
              </div>
              <div style={statCard('#f59e0b')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>과다 예측</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#f59e0b' }}>{accuracy.over_count}</div>
              </div>
              <div style={statCard('#dc2626')}>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>과소 예측</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#dc2626' }}>{accuracy.under_count}</div>
              </div>
            </div>
          )}

          <div style={card}>
            <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>실패 분석</h3>
            {!failures || failures.total_failures === 0 ? <Empty message="실패 기록이 없습니다." /> : (
              <>
                <div style={{ marginBottom: 16 }}>
                  <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 600 }}>사유별 분포</h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {Object.entries(failures.by_reason).map(([reason, count]) => (
                      <div key={reason} style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 16px', textAlign: 'center' }}>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>{reason}</div>
                        <div style={{ fontSize: 20, fontWeight: 800, color: '#111827' }}>{count}</div>
                      </div>
                    ))}
                  </div>
                </div>
                {failures.top_failed_skus.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 600 }}>실패 상위 SKU</h4>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr>
                            <th style={thStyle}>SKU/상품명</th>
                            <th style={thStyle}>오차 가중치</th>
                          </tr>
                        </thead>
                        <tbody>
                          {failures.top_failed_skus.map((f, i) => (
                            <tr key={f.sku_or_name} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
                              <td style={{ ...tdStyle, fontWeight: 600 }}>{f.sku_or_name}</td>
                              <td style={{ ...tdStyle, color: '#dc2626', fontWeight: 700 }}>{f.error_weight.toFixed(1)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                {failures.improvement_suggestions.length > 0 && (
                  <div>
                    <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 600 }}>개선 제안</h4>
                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                      {failures.improvement_suggestions.map((s, i) => (
                        <li key={i} style={{ fontSize: 13, color: '#374151', marginBottom: 4 }}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
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
