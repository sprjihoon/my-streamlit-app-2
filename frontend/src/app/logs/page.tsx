'use client';

import { useEffect, useState, useCallback } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── types ───────────────────────────────────────────────────────────
interface Analytics {
  summary: {
    this_week: number;
    last_week: number;
    week_change_pct: number;
    active_users_7d: number;
  };
  daily: { date: string; count: number }[];
  by_feature: { feature: string; target_type: string; count: number }[];
  hourly: { hour: number; count: number }[];
  user_breakdown: { user_nickname: string; action_type: string; count: number }[];
}

interface LogEntry {
  log_id: number;
  action_type: string;
  target_type: string | null;
  target_id: string | null;
  target_name: string | null;
  user_nickname: string | null;
  details: string | null;
  created_at: string | null;
}

interface LogsResult {
  logs: LogEntry[];
  total: number;
  filters: { action_types: string[]; target_types: string[]; users: string[] };
}

// ─── helpers ─────────────────────────────────────────────────────────
function actionColor(action: string): string {
  if (action.includes('삭제')) return '#dc2626';
  if (action.includes('반려')) return '#f97316';
  if (action.includes('승인') || action.includes('확정')) return '#16a34a';
  if (action.includes('수정') || action.includes('업데이트')) return '#2563eb';
  if (action.includes('생성') || action.includes('등록')) return '#7c3aed';
  if (action.includes('업로드')) return '#0891b2';
  if (action.includes('로그인')) return '#4f46e5';
  if (action.includes('신청')) return '#d97706';
  return '#6b7280';
}

function fmtDt(s: string | null) {
  if (!s) return '-';
  return new Date(s).toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function Arrow({ pct }: { pct: number }) {
  if (pct > 0) return <span style={{ color: '#16a34a', fontSize: '0.8rem' }}>▲ {pct}%</span>;
  if (pct < 0) return <span style={{ color: '#dc2626', fontSize: '0.8rem' }}>▼ {Math.abs(pct)}%</span>;
  return <span style={{ color: '#6b7280', fontSize: '0.8rem' }}>— 0%</span>;
}

// ─── SVG 차트 컴포넌트 ─────────────────────────────────────────────
function BarChart({ data, keyX, keyY, color = '#2563eb', height = 120, maxBars = 30 }: {
  data: Record<string, number | string>[];
  keyX: string; keyY: string;
  color?: string; height?: number; maxBars?: number;
}) {
  const slice = data.slice(-maxBars);
  const max = Math.max(...slice.map(d => Number(d[keyY])), 1);
  const w = 100 / slice.length;
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      {slice.map((d, i) => {
        const val = Number(d[keyY]);
        const barH = (val / max) * (height - 20);
        const x = i * w + w * 0.15;
        const bw = w * 0.7;
        const y = height - 18 - barH;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={barH} fill={color} rx="1" opacity={0.85} />
            {val > 0 && barH > 12 && (
              <text x={x + bw / 2} y={y + barH / 2 + 4} textAnchor="middle" fontSize="4" fill="white">{val}</text>
            )}
          </g>
        );
      })}
      {/* x축 레이블 — 첫·중간·마지막만 */}
      {[0, Math.floor(slice.length / 2), slice.length - 1].filter((v, i, a) => a.indexOf(v) === i).map(i => {
        const d = slice[i];
        const lbl = String(d[keyX]).slice(-5);
        return (
          <text key={i} x={i * w + w / 2} y={height - 3} textAnchor="middle" fontSize="4.5" fill="#9ca3af">{lbl}</text>
        );
      })}
    </svg>
  );
}

function HeatBar({ data }: { data: { hour: number; count: number }[] }) {
  const max = Math.max(...data.map(d => d.count), 1);
  const blocks = ['00', '03', '06', '09', '12', '15', '18', '21'];
  return (
    <div style={{ display: 'flex', gap: '2px', alignItems: 'flex-end', height: 60 }}>
      {data.map(d => {
        const pct = d.count / max;
        const alpha = 0.12 + pct * 0.88;
        const h = Math.max(4, pct * 52);
        return (
          <div key={d.hour} title={`${d.hour}시: ${d.count}건`}
            style={{
              flex: 1,
              height: h,
              backgroundColor: `rgba(37,99,235,${alpha.toFixed(2)})`,
              borderRadius: '2px 2px 0 0',
              cursor: 'default',
            }}
          />
        );
      })}
    </div>
  );
}

function DonutChart({ data, colors }: { data: { label: string; value: number }[]; colors: string[] }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  let cum = 0;
  const radius = 30;
  const cx = 40; const cy = 40;
  const paths = data.map((d, i) => {
    const frac = d.value / total;
    const start = cum * 2 * Math.PI - Math.PI / 2;
    cum += frac;
    const end = cum * 2 * Math.PI - Math.PI / 2;
    if (frac === 0) return null;
    const lx1 = cx + radius * Math.cos(start);
    const ly1 = cy + radius * Math.sin(start);
    const lx2 = cx + radius * Math.cos(end);
    const ly2 = cy + radius * Math.sin(end);
    const large = frac > 0.5 ? 1 : 0;
    return (
      <path key={i}
        d={`M${cx},${cy} L${lx1},${ly1} A${radius},${radius} 0 ${large},1 ${lx2},${ly2} Z`}
        fill={colors[i % colors.length]} opacity={0.9}
      />
    );
  });
  return (
    <svg viewBox="0 0 80 80" style={{ width: 80, height: 80, flexShrink: 0 }}>
      {paths}
      <circle cx={cx} cy={cy} r={15} fill="white" />
    </svg>
  );
}

// ─── 탭 타입 ─────────────────────────────────────────────────────────
type Tab = 'dashboard' | 'logs';

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────
export default function LogsPage() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logFilters, setLogFilters] = useState<LogsResult['filters'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // 로그 필터 상태
  const [fFrom, setFFrom] = useState('');
  const [fTo, setFTo] = useState('');
  const [fAction, setFAction] = useState('');
  const [fTarget, setFTarget] = useState('');
  const [fUser, setFUser] = useState('');

  const loadAnalytics = useCallback(async (tok: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/logs/analytics?token=${tok}&days=30`);
      if (!res.ok) throw new Error(await res.text());
      setAnalytics(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : '분석 데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLogs = useCallback(async (tok: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ token: tok, limit: '500' });
      if (fFrom) params.set('period_from', fFrom);
      if (fTo) params.set('period_to', fTo);
      if (fAction) params.set('action_type', fAction);
      if (fTarget) params.set('target_type', fTarget);
      if (fUser) params.set('user_nickname', fUser);
      const res = await fetch(`${API}/logs?${params}`);
      if (!res.ok) throw new Error(await res.text());
      const data: LogsResult = await res.json();
      setLogs(data.logs);
      setLogFilters(data.filters);
    } catch (e) {
      setError(e instanceof Error ? e.message : '로그 로드 실패');
    } finally {
      setLoading(false);
    }
  }, [fFrom, fTo, fAction, fTarget, fUser]);

  useEffect(() => {
    const tok = localStorage.getItem('token');
    const isAdmin = localStorage.getItem('isAdmin') === 'true';
    if (!tok || !isAdmin) {
      setError('관리자 권한이 필요합니다.');
      setLoading(false);
      return;
    }
    setToken(tok);
    loadAnalytics(tok);
    loadLogs(tok);
  }, []);  // eslint-disable-line

  const switchTab = (t: Tab) => {
    setTab(t);
    if (!token) return;
    if (t === 'dashboard') loadAnalytics(token);
  };

  const FEATURE_COLORS = ['#2563eb', '#16a34a', '#7c3aed', '#d97706', '#0891b2', '#dc2626', '#f97316', '#84cc16'];

  // ── 사용자별 집계 ────────────────────────────────────
  const userSummary = analytics
    ? Object.entries(
        analytics.user_breakdown.reduce<Record<string, number>>((acc, r) => {
          acc[r.user_nickname] = (acc[r.user_nickname] || 0) + r.count;
          return acc;
        }, {})
      ).sort((a, b) => b[1] - a[1]).slice(0, 8)
    : [];

  const tabStyle = (t: Tab): React.CSSProperties => ({
    padding: '0.5rem 1.25rem',
    border: 'none',
    background: tab === t ? '#2563eb' : '#f3f4f6',
    color: tab === t ? 'white' : '#374151',
    borderRadius: '6px',
    cursor: 'pointer',
    fontWeight: tab === t ? 700 : 400,
    fontSize: '0.875rem',
  });

  return (
    <div style={{ padding: '1.25rem', maxWidth: 1100, margin: '0 auto' }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h1 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#111' }}>활동 로그 분석</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button style={tabStyle('dashboard')} onClick={() => switchTab('dashboard')}>📊 대시보드</button>
          <button style={tabStyle('logs')} onClick={() => switchTab('logs')}>📋 로그 목록</button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '0.75rem 1rem', background: '#fef2f2', color: '#dc2626', borderRadius: 8, marginBottom: '1rem', fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      {/* ── 대시보드 탭 ────────────────────────────────── */}
      {tab === 'dashboard' && (
        loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#9ca3af' }}>데이터 로딩 중...</div>
        ) : analytics ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

            {/* 요약 KPI */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
              {[
                { label: '이번 주 활동', value: analytics.summary.this_week.toLocaleString(), sub: <Arrow pct={analytics.summary.week_change_pct} />, color: '#2563eb' },
                { label: '지난 주 활동', value: analytics.summary.last_week.toLocaleString(), sub: null, color: '#6b7280' },
                { label: '주간 활성 사용자', value: analytics.summary.active_users_7d + '명', sub: null, color: '#7c3aed' },
              ].map((kpi, i) => (
                <div key={i} style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: '0.25rem' }}>{kpi.label}</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 700, color: kpi.color }}>{kpi.value}</div>
                  {kpi.sub && <div style={{ marginTop: '0.2rem' }}>{kpi.sub}</div>}
                </div>
              ))}
            </div>

            {/* 일별 추이 + 시간대 */}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '0.75rem' }}>
              <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>📈 최근 30일 일별 활동량</div>
                {analytics.daily.length > 0
                  ? <BarChart data={analytics.daily} keyX="date" keyY="count" height={120} />
                  : <p style={{ color: '#9ca3af', fontSize: '0.8rem', textAlign: 'center', padding: '2rem' }}>데이터 없음</p>
                }
              </div>
              <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>🕐 시간대별 활동 분포</div>
                <HeatBar data={analytics.hourly} />
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
                  {['0시', '6시', '12시', '18시', '23시'].map(t => (
                    <span key={t} style={{ fontSize: '0.65rem', color: '#9ca3af' }}>{t}</span>
                  ))}
                </div>
                <div style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: '#6b7280' }}>
                  피크: {analytics.hourly.reduce((a, b) => a.count > b.count ? a : b, { hour: 0, count: 0 }).hour}시
                </div>
              </div>
            </div>

            {/* 기능별 + 사용자별 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              {/* 기능별 */}
              <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.75rem' }}>🏷️ 기능별 사용량</div>
                {analytics.by_feature.length > 0 ? (
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <DonutChart
                      data={analytics.by_feature.map(f => ({ label: f.feature, value: f.count }))}
                      colors={FEATURE_COLORS}
                    />
                    <div style={{ flex: 1 }}>
                      {analytics.by_feature.map((f, i) => {
                        const total = analytics.by_feature.reduce((s, x) => s + x.count, 0);
                        const pct = ((f.count / total) * 100).toFixed(0);
                        return (
                          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.3rem' }}>
                            <div style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: FEATURE_COLORS[i % FEATURE_COLORS.length], flexShrink: 0 }} />
                            <span style={{ fontSize: '0.78rem', color: '#374151', flex: 1 }}>{f.feature}</span>
                            <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>{f.count}</span>
                            <span style={{ fontSize: '0.7rem', color: '#9ca3af', width: 32, textAlign: 'right' }}>{pct}%</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</p>}
              </div>

              {/* 사용자별 */}
              <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.75rem' }}>👤 사용자별 활동량 TOP8</div>
                {userSummary.length > 0 ? (
                  <div>
                    {userSummary.map(([name, cnt], i) => {
                      const maxCnt = userSummary[0][1];
                      const pct = (cnt / maxCnt) * 100;
                      return (
                        <div key={i} style={{ marginBottom: '0.45rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '2px' }}>
                            <span style={{ color: '#374151', fontWeight: i === 0 ? 600 : 400 }}>{name}</span>
                            <span style={{ color: '#6b7280' }}>{cnt}건</span>
                          </div>
                          <div style={{ height: 6, background: '#f3f4f6', borderRadius: 3 }}>
                            <div style={{ height: 6, width: `${pct}%`, background: FEATURE_COLORS[i % FEATURE_COLORS.length], borderRadius: 3, transition: 'width 0.3s' }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</p>}
              </div>
            </div>


          </div>
        ) : null
      )}

      {/* ── 로그 목록 탭 ────────────────────────────────── */}
      {tab === 'logs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {/* 필터 */}
          <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
            <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.75rem' }}>🔍 필터</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.5rem', marginBottom: '0.75rem' }}>
              {[
                { label: '시작일', el: <input type="date" value={fFrom} onChange={e => setFFrom(e.target.value)} style={inpStyle} /> },
                { label: '종료일', el: <input type="date" value={fTo} onChange={e => setFTo(e.target.value)} style={inpStyle} /> },
                { label: '액션 유형', el: (
                  <select value={fAction} onChange={e => setFAction(e.target.value)} style={inpStyle}>
                    <option value="">전체</option>
                    {logFilters?.action_types.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                )},
                { label: '대상 유형', el: (
                  <select value={fTarget} onChange={e => setFTarget(e.target.value)} style={inpStyle}>
                    <option value="">전체</option>
                    {logFilters?.target_types.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                )},
                { label: '사용자', el: (
                  <select value={fUser} onChange={e => setFUser(e.target.value)} style={inpStyle}>
                    <option value="">전체</option>
                    {logFilters?.users.map(u => <option key={u} value={u}>{u}</option>)}
                  </select>
                )},
              ].map(({ label, el }) => (
                <div key={label}>
                  <label style={{ display: 'block', fontSize: '0.75rem', color: '#6b7280', marginBottom: '0.2rem' }}>{label}</label>
                  {el}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={() => token && loadLogs(token)} style={{ ...btnStyle, background: '#2563eb' }}>검색</button>
              <button onClick={() => { setFFrom(''); setFTo(''); setFAction(''); setFTarget(''); setFUser(''); setTimeout(() => token && loadLogs(token), 100); }} style={{ ...btnStyle, background: '#6b7280' }}>초기화</button>
            </div>
          </div>

          {/* 테이블 */}
          <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
            <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.75rem' }}>
              📋 로그 목록 <span style={{ color: '#6b7280', fontWeight: 400 }}>({logs.length}건)</span>
            </div>
            {loading ? (
              <p style={{ color: '#9ca3af', textAlign: 'center', padding: '2rem' }}>로딩 중...</p>
            ) : logs.length === 0 ? (
              <p style={{ color: '#9ca3af', textAlign: 'center', padding: '2rem' }}>로그가 없습니다.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ background: '#f9fafb' }}>
                      {['시각', '액션', '대상 유형', '대상명', '작업자', '상세'].map(h => (
                        <th key={h} style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map(log => (
                      <tr key={log.log_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '0.45rem 0.75rem', whiteSpace: 'nowrap', color: '#6b7280' }}>{fmtDt(log.created_at)}</td>
                        <td style={{ padding: '0.45rem 0.75rem' }}>
                          <span style={{ display: 'inline-block', padding: '0.15rem 0.5rem', borderRadius: 4, fontSize: '0.72rem', background: actionColor(log.action_type), color: 'white', whiteSpace: 'nowrap' }}>
                            {log.action_type}
                          </span>
                        </td>
                        <td style={{ padding: '0.45rem 0.75rem', color: '#6b7280' }}>{log.target_type || '-'}</td>
                        <td style={{ padding: '0.45rem 0.75rem', fontWeight: 500, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.target_name || '-'}</td>
                        <td style={{ padding: '0.45rem 0.75rem', color: '#374151' }}>{log.user_nickname || '-'}</td>
                        <td style={{ padding: '0.45rem 0.75rem', color: '#6b7280', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={log.details || ''}>{log.details || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const inpStyle: React.CSSProperties = {
  width: '100%', padding: '0.45rem 0.6rem', border: '1px solid #d1d5db',
  borderRadius: 6, fontSize: '0.8rem', background: 'white', boxSizing: 'border-box',
};

const btnStyle: React.CSSProperties = {
  padding: '0.45rem 1rem', border: 'none', borderRadius: 6,
  color: 'white', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600,
};
