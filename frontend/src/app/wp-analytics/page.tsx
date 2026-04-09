'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loading } from '@/components/Loading';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ── 타입 정의 ────────────────────────────────────────────────────────────
interface Summary {
  total_visits: number; unique_visitors: number;
  mobile_count: number; mobile_rate: number;
  avg_duration_seconds: number; max_duration_seconds: number;
  tracked_visit_count: number;
}
interface PageStat { page_url: string; count: number; unique_count: number; avg_duration: number }
interface SourceStat { source: string; count: number }
interface OsStat { os: string; count: number }
interface BrowserStat { browser: string; count: number }
interface DeviceStat { device: string; count: number }
interface HourlyStat { hour: string; count: number }
interface WeekdayStat { weekday: string; count: number }
interface LocationStat { location: string; count: number }
interface DailyStat { date: string; count: number }
interface UtmStat { source: string; medium: string; campaign: string; count: number }
interface DwellDist { [k: string]: number }

interface Engagement {
  milestone_10s_count: number; milestone_30s_count: number;
  milestone_10s_rate: number; milestone_30s_rate: number;
  avg_scroll_depth: number;
  scroll_50_count: number; scroll_75_count: number;
  scroll_50_rate: number; scroll_75_rate: number;
  duration_1_9: number; duration_10_29: number;
  duration_30plus: number; duration_zero: number;
}
interface RepeatStats {
  total_ips: number; repeat_ips: number; once_ips: number; avg_sessions: number;
}

interface Stats {
  summary: Summary;
  page_stats: PageStat[];
  referrer_stats: SourceStat[];
  os_stats: OsStat[];
  browser_stats: BrowserStat[];
  device_stats: DeviceStat[];
  hourly_stats: HourlyStat[];
  weekday_stats: WeekdayStat[];
  location_stats: LocationStat[];
  daily_visits: DailyStat[];
  utm_stats: UtmStat[];
  dwell_distribution: DwellDist;
  engagement: Engagement;
  repeat_stats: RepeatStats;
}

interface FlowSummary { total_sessions: number; bounce_sessions: number; bounce_rate: number }
interface DepthItem { label: string; count: number }
interface PageFlowItem { from_page: string; to_page: string; count: number }
interface ExitRateItem { page_url: string; total_views: number; exit_count: number; exit_rate: number }
interface EntryItem { page_url: string; count: number }

interface FlowData {
  summary: FlowSummary;
  session_depth: DepthItem[];
  entry_pages: EntryItem[];
  exit_pages: EntryItem[];
  page_flow: PageFlowItem[];
  exit_rate_by_page: ExitRateItem[];
}

interface IpSession {
  ip_address: string; country: string; region: string; city: string;
  page_views: number; sessions: number; max_duration: number;
  first_visit: string; last_visit: string;
  os: string; browser: string; device_type: string; is_mobile: boolean;
  source: string; utm_campaign: string;
  pages_visited: string[];
  max_scroll_depth: number; has_10s: boolean; has_30s: boolean;
  visit_days: number; is_repeat: boolean;
}

interface VisitorLog {
  id: number; ip_address: string; country: string; region: string; city: string;
  page_url: string; referrer: string; os: string; browser: string; device_type: string;
  is_mobile: boolean | null; utm_source: string | null; utm_campaign: string | null;
  duration_seconds: number; created_at: string; source: string;
  scroll_depth: number; milestone_10s: boolean; milestone_30s: boolean;
}

// ── 유틸 ─────────────────────────────────────────────────────────────────
function fmt(n: number) { return n.toLocaleString('ko-KR'); }

function fmtDuration(s: number): string {
  if (!s || s <= 0) return '-';
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60), rem = s % 60;
  if (m < 60) return rem > 0 ? `${m}분 ${rem}초` : `${m}분`;
  const h = Math.floor(m / 60), rm = m % 60;
  return rm > 0 ? `${h}시간 ${rm}분` : `${h}시간`;
}

function shortenUrl(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname.replace(/\/$/, '') || '/';
    const label = path === '/' ? '홈' : path;
    return u.search ? `${label}${u.search.slice(0, 20)}…` : label;
  } catch { return url.slice(0, 40); }
}

// 날짜 프리셋 (한국시간 KST = UTC+9 기준)
type Preset = '오늘' | '어제' | '7일' | '15일' | '30일' | '전체' | '직접입력';
function toKstDateStr(date: Date): string {
  const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
  return kst.toISOString().split('T')[0];
}
function calcPreset(p: Preset): { from: string; to: string } {
  const now = new Date();
  const ago = (n: number) => new Date(now.getTime() - n * 24 * 60 * 60 * 1000);
  switch (p) {
    case '오늘':    return { from: toKstDateStr(now), to: toKstDateStr(now) };
    case '어제':    return { from: toKstDateStr(ago(1)), to: toKstDateStr(ago(1)) };
    case '7일':     return { from: toKstDateStr(ago(6)), to: toKstDateStr(now) };
    case '15일':    return { from: toKstDateStr(ago(14)), to: toKstDateStr(now) };
    case '30일':    return { from: toKstDateStr(ago(29)), to: toKstDateStr(now) };
    default:        return { from: '', to: '' };
  }
}

// 유입경로 색상
const SRC_COLOR: Record<string, { bg: string; text: string }> = {
  'Instagram':       { bg: '#e4405f', text: '#fff' },
  'Instagram 광고':  { bg: '#c13584', text: '#fff' },
  'YouTube':         { bg: '#ff0000', text: '#fff' },
  'YouTube 광고':    { bg: '#cc0000', text: '#fff' },
  'Naver':           { bg: '#03c75a', text: '#fff' },
  '네이버 광고':     { bg: '#019040', text: '#fff' },
  'Google':          { bg: '#4285f4', text: '#fff' },
  'Google 광고':     { bg: '#1a73e8', text: '#fff' },
  'Facebook':        { bg: '#1877f2', text: '#fff' },
  'Facebook 광고':   { bg: '#0a5dc2', text: '#fff' },
  'KakaoTalk':       { bg: '#fee500', text: '#3c1e1e' },
  '카카오 광고':     { bg: '#f5c200', text: '#3c1e1e' },
  'TikTok':          { bg: '#111', text: '#fff' },
  'X(Twitter)':      { bg: '#000', text: '#fff' },
  '직접 접속':       { bg: '#e5e7eb', text: '#374151' },
  '사이트 내 이동':  { bg: '#dbeafe', text: '#1d4ed8' },
  'Daum':            { bg: '#4a90d9', text: '#fff' },
  '이메일':          { bg: '#7c3aed', text: '#fff' },
  '기타':            { bg: '#f3f4f6', text: '#6b7280' },
};

function SourceBadge({ source }: { source: string }) {
  const c = SRC_COLOR[source] || { bg: '#a855f7', text: '#fff' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10,
      fontSize: '0.7rem', fontWeight: 600, background: c.bg, color: c.text, whiteSpace: 'nowrap',
    }}>{source}</span>
  );
}

function BarRow({ label, count, total, color, sub }: { label: string; count: number; total: number; color: string; sub?: string }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <span style={{ fontSize: '0.82rem', color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
          {sub && <span style={{ fontSize: '0.7rem', color: '#9ca3af', flexShrink: 0 }}>{sub}</span>}
        </div>
        <span style={{ fontSize: '0.82rem', fontWeight: 600, color, flexShrink: 0 }}>
          {fmt(count)} <span style={{ color: '#9ca3af', fontWeight: 400 }}>({pct}%)</span>
        </span>
      </div>
      <div style={{ height: 6, background: '#f1f5f9', borderRadius: 4 }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 4, transition: 'width .4s' }} />
      </div>
    </div>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────
type Tab = 'overview' | 'flow' | 'pages' | 'sessions' | 'visitors';
const PRESETS: Preset[] = ['오늘', '어제', '7일', '15일', '30일', '전체', '직접입력'];

export default function WpAnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [flow, setFlow] = useState<FlowData | null>(null);
  const [sessions, setSessions] = useState<IpSession[]>([]);
  const [sessionTotal, setSessionTotal] = useState(0);
  const [sessionPage, setSessionPage] = useState(1);
  const [visitors, setVisitors] = useState<VisitorLog[]>([]);
  const [visitorTotal, setVisitorTotal] = useState(0);
  const [visitorPage, setVisitorPage] = useState(1);

  const [loading, setLoading] = useState(true);
  const [flowLoading, setFlowLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  const [preset, setPreset] = useState<Preset>('30일');
  const [dateFrom, setDateFrom] = useState(calcPreset('30일').from);
  const [dateTo, setDateTo] = useState(calcPreset('30일').to);

  const PAGE_SIZE = 30;

  // 날짜 프리셋 적용
  function applyPreset(p: Preset) {
    setPreset(p);
    if (p !== '직접입력') {
      const { from, to } = calcPreset(p);
      setDateFrom(from); setDateTo(to);
    }
  }

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (dateFrom) p.append('date_from', dateFrom);
      if (dateTo) p.append('date_to', dateTo);
      const res = await fetch(`${API_BASE}/wp-analytics/stats?${p}`);
      if (res.ok) setStats(await res.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [dateFrom, dateTo]);

  const loadFlow = useCallback(async () => {
    setFlowLoading(true);
    try {
      const p = new URLSearchParams();
      if (dateFrom) p.append('date_from', dateFrom);
      if (dateTo) p.append('date_to', dateTo);
      const res = await fetch(`${API_BASE}/wp-analytics/flow?${p}`);
      if (res.ok) setFlow(await res.json());
    } catch (e) { console.error(e); }
    finally { setFlowLoading(false); }
  }, [dateFrom, dateTo]);

  const loadSessions = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      if (dateFrom) p.append('date_from', dateFrom);
      if (dateTo) p.append('date_to', dateTo);
      p.append('page', String(sessionPage)); p.append('page_size', String(PAGE_SIZE));
      const res = await fetch(`${API_BASE}/wp-analytics/sessions?${p}`);
      if (res.ok) { const d = await res.json(); setSessions(d.items); setSessionTotal(d.total); }
    } catch (e) { console.error(e); }
  }, [dateFrom, dateTo, sessionPage]);

  const loadVisitors = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      if (dateFrom) p.append('date_from', dateFrom);
      if (dateTo) p.append('date_to', dateTo);
      p.append('page', String(visitorPage)); p.append('page_size', '20');
      const res = await fetch(`${API_BASE}/wp-analytics/visitors?${p}`);
      if (res.ok) { const d = await res.json(); setVisitors(d.items); setVisitorTotal(d.total); }
    } catch (e) { console.error(e); }
  }, [dateFrom, dateTo, visitorPage]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { if (activeTab === 'flow') loadFlow(); }, [activeTab, loadFlow]);
  useEffect(() => { if (activeTab === 'sessions') loadSessions(); }, [activeTab, loadSessions]);
  useEffect(() => { if (activeTab === 'visitors') loadVisitors(); }, [activeTab, loadVisitors]);

  // ── 스타일 ──
  const card: React.CSSProperties = { background: '#fff', borderRadius: 12, padding: '1.1rem', boxShadow: '0 1px 4px rgba(0,0,0,.07)' };
  const statCard = (color: string): React.CSSProperties => ({ ...card, textAlign: 'center', padding: '1.1rem 0.6rem', borderTop: `3px solid ${color}` });
  const tabBtn = (active: boolean): React.CSSProperties => ({
    padding: '0.5rem 1rem', border: 'none', borderRadius: 8, cursor: 'pointer',
    fontWeight: 600, fontSize: '0.83rem',
    background: active ? '#6366f1' : '#f3f4f6',
    color: active ? '#fff' : '#6b7280', transition: 'all .15s',
  });
  const presetBtn = (active: boolean): React.CSSProperties => ({
    padding: '0.35rem 0.75rem', border: '1px solid', borderRadius: 6,
    fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
    borderColor: active ? '#6366f1' : '#e5e7eb',
    background: active ? '#eef2ff' : '#fff',
    color: active ? '#6366f1' : '#6b7280',
  });
  const inputStyle: React.CSSProperties = {
    padding: '0.4rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6,
    fontSize: '0.82rem', outline: 'none', background: '#fff',
  };
  const btnStyle: React.CSSProperties = {
    padding: '0.4rem 0.8rem', border: 'none', borderRadius: 6,
    fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
  };
  const th: React.CSSProperties = { padding: '0.6rem 0.75rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap', background: '#f8fafc', fontSize: '0.82rem' };
  const td: React.CSSProperties = { padding: '0.55rem 0.75rem', borderBottom: '1px solid #f1f5f9', fontSize: '0.82rem' };

  const totalVisits = stats?.summary.total_visits || 1;
  const sessTotal = Math.max(1, Math.ceil(sessionTotal / PAGE_SIZE));
  const visTotal = Math.max(1, Math.ceil(visitorTotal / 20));

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '1rem' }}>

      {/* ── 헤더 ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '1rem' }}>
        <div style={{ width: 38, height: 38, background: '#6366f1', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.2rem' }}>🌐</div>
        <div>
          <h1 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#1f2937', margin: 0 }}>WordPress 사이트 분석</h1>
          <p style={{ fontSize: '0.73rem', color: '#9ca3af', margin: 0 }}>spring3pl.co.kr 전체 페이지 방문자 데이터</p>
        </div>
      </div>

      {/* ── 날짜 필터 + 프리셋 ── */}
      <div style={{ ...card, marginBottom: '1rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {PRESETS.map(p => (
            <button key={p} style={presetBtn(preset === p)} onClick={() => applyPreset(p)}>{p}</button>
          ))}
        </div>
        {preset === '직접입력' && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 600, color: '#6b7280', marginBottom: 2 }}>시작일</label>
              <input type="date" style={inputStyle} value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 600, color: '#6b7280', marginBottom: 2 }}>종료일</label>
              <input type="date" style={inputStyle} value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
          </div>
        )}
        {(dateFrom || dateTo) && preset !== '전체' && (
          <div style={{ marginTop: 6, fontSize: '0.75rem', color: '#6b7280' }}>
            📅 {dateFrom || '전체'} ~ {dateTo || '전체'}
          </div>
        )}
      </div>

      {/* ── 탭 ── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: '1rem', flexWrap: 'wrap' }}>
        {([['overview', '📊 개요'], ['flow', '🔀 페이지 흐름'], ['pages', '📄 페이지별'], ['sessions', '👤 방문자별'], ['visitors', '📋 방문 로그']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} style={tabBtn(activeTab === t)} onClick={() => setActiveTab(t)}>{label}</button>
        ))}
      </div>

      {loading && activeTab === 'overview' ? (
        <div style={{ padding: '4rem', textAlign: 'center' }}><Loading /></div>
      ) : (
        <>
          {/* ════════════════════════════════════════════════
              개요 탭
          ════════════════════════════════════════════════ */}
          {activeTab === 'overview' && stats && (
            <>
              {/* 요약 카드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                <div style={statCard('#6366f1')}>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>총 방문수</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#6366f1' }}>{fmt(stats.summary.total_visits)}</div>
                </div>
                <div style={statCard('#10b981')}>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>고유 방문자</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#10b981' }}>{fmt(stats.summary.unique_visitors)}</div>
                </div>
                <div style={statCard('#ec4899')}>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>모바일</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#ec4899' }}>{fmt(stats.summary.mobile_count)}</div>
                  <div style={{ fontSize: '0.68rem', color: '#9ca3af' }}>{stats.summary.mobile_rate}%</div>
                </div>
                <div style={statCard('#06b6d4')}>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>평균 체류시간</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#06b6d4' }}>{fmtDuration(stats.summary.avg_duration_seconds)}</div>
                  <div style={{ fontSize: '0.68rem', color: '#9ca3af' }}>최대 {fmtDuration(stats.summary.max_duration_seconds)}</div>
                </div>
                <div style={statCard('#f59e0b')}>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>페이지 수</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f59e0b' }}>{stats.page_stats.length}</div>
                </div>
              </div>

              {/* 인게이지먼트 + 반복유입 카드 */}
              {stats.engagement && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                  {/* 인게이지먼트 지표 */}
                  <div style={card}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>📊 방문 깊이 분석</h3>
                    <p style={{ fontSize: '0.72rem', color: '#9ca3af', margin: '0 0 0.8rem' }}>한 페이지만 보고 나간 방문자도 "얼마나 관심이 있었는지"를 측정합니다</p>

                    {/* 체류시간 구간 */}
                    <div style={{ marginBottom: '0.8rem' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', marginBottom: 6 }}>⏱ 체류시간 분포</div>
                      {[
                        { label: '즉시 이탈 (미측정)', val: stats.engagement.duration_zero, color: '#e5e7eb', textColor: '#9ca3af' },
                        { label: '1~9초 (훑어봄)', val: stats.engagement.duration_1_9, color: '#fca5a5', textColor: '#b91c1c' },
                        { label: '10~29초 (관심)', val: stats.engagement.duration_10_29, color: '#fdba74', textColor: '#92400e' },
                        { label: '30초+ (진지한 관심)', val: stats.engagement.duration_30plus, color: '#6ee7b7', textColor: '#065f46' },
                      ].map((item, i) => {
                        const pct = stats.summary.total_visits > 0 ? Math.round(item.val / stats.summary.total_visits * 100) : 0;
                        return (
                          <div key={i} style={{ marginBottom: 6 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2, fontSize: '0.75rem' }}>
                              <span style={{ color: '#374151' }}>{item.label}</span>
                              <span style={{ fontWeight: 700, color: item.textColor }}>{fmt(item.val)}명 ({pct}%)</span>
                            </div>
                            <div style={{ height: 5, background: '#f1f5f9', borderRadius: 3 }}>
                              <div style={{ height: '100%', width: `${pct}%`, background: item.color, borderRadius: 3 }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* 마일스톤 */}
                    <div style={{ display: 'flex', gap: 8, marginBottom: '0.8rem' }}>
                      <div style={{ flex: 1, background: '#eff6ff', borderRadius: 8, padding: '0.6rem', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.65rem', color: '#3b82f6', fontWeight: 700 }}>10초 이상 체류</div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#1d4ed8' }}>{stats.engagement.milestone_10s_rate}%</div>
                        <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>{fmt(stats.engagement.milestone_10s_count)}명</div>
                      </div>
                      <div style={{ flex: 1, background: '#f0fdf4', borderRadius: 8, padding: '0.6rem', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.65rem', color: '#16a34a', fontWeight: 700 }}>30초 이상 체류</div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#15803d' }}>{stats.engagement.milestone_30s_rate}%</div>
                        <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>{fmt(stats.engagement.milestone_30s_count)}명</div>
                      </div>
                    </div>

                    {/* 스크롤 깊이 */}
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', marginBottom: 6 }}>📜 스크롤 깊이</div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1, background: '#faf5ff', borderRadius: 8, padding: '0.6rem', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.65rem', color: '#7c3aed', fontWeight: 700 }}>평균 스크롤</div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#6d28d9' }}>{stats.engagement.avg_scroll_depth}%</div>
                      </div>
                      <div style={{ flex: 1, background: '#faf5ff', borderRadius: 8, padding: '0.6rem', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.65rem', color: '#7c3aed', fontWeight: 700 }}>50% 이상 스크롤</div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#6d28d9' }}>{stats.engagement.scroll_50_rate}%</div>
                        <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>{fmt(stats.engagement.scroll_50_count)}명</div>
                      </div>
                      <div style={{ flex: 1, background: '#faf5ff', borderRadius: 8, padding: '0.6rem', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.65rem', color: '#7c3aed', fontWeight: 700 }}>75% 이상 스크롤</div>
                        <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#6d28d9' }}>{stats.engagement.scroll_75_rate}%</div>
                        <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>{fmt(stats.engagement.scroll_75_count)}명</div>
                      </div>
                    </div>
                  </div>

                  {/* 반복유입 분석 */}
                  {stats.repeat_stats && (
                    <div style={card}>
                      <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.4rem' }}>🔄 반복유입 분석</h3>
                      <p style={{ fontSize: '0.72rem', color: '#9ca3af', margin: '0 0 0.8rem' }}>같은 IP가 탭을 닫고 재접속한 횟수 기준 (당일 재방문 포함, 페이지 이동은 제외)</p>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: '0.8rem' }}>
                        <div style={{ background: '#f0fdf4', borderRadius: 8, padding: '0.7rem', textAlign: 'center' }}>
                          <div style={{ fontSize: '0.68rem', color: '#16a34a', fontWeight: 700 }}>재방문자</div>
                          <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#15803d' }}>{fmt(stats.repeat_stats.repeat_ips)}</div>
                          <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>
                            {stats.repeat_stats.total_ips > 0 ? Math.round(stats.repeat_stats.repeat_ips / stats.repeat_stats.total_ips * 100) : 0}%
                          </div>
                        </div>
                        <div style={{ background: '#f8fafc', borderRadius: 8, padding: '0.7rem', textAlign: 'center' }}>
                          <div style={{ fontSize: '0.68rem', color: '#6b7280', fontWeight: 700 }}>신규방문자</div>
                          <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#374151' }}>{fmt(stats.repeat_stats.once_ips)}</div>
                          <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>
                            {stats.repeat_stats.total_ips > 0 ? Math.round(stats.repeat_stats.once_ips / stats.repeat_stats.total_ips * 100) : 0}%
                          </div>
                        </div>
                      </div>

                      <div style={{ background: '#eff6ff', borderRadius: 8, padding: '0.6rem', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.68rem', color: '#3b82f6', fontWeight: 700 }}>방문자 평균 세션 수</div>
                        <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#1d4ed8' }}>{stats.repeat_stats.avg_sessions.toFixed(1)}회</div>
                        <div style={{ fontSize: '0.65rem', color: '#9ca3af' }}>세션 기준 (당일 재방문 포함)</div>
                      </div>

                      {/* 재방문율 바 */}
                      <div style={{ marginTop: '0.8rem' }}>
                        {[
                          { label: '신규 (1회 방문)', count: stats.repeat_stats.once_ips, color: '#e5e7eb' },
                          { label: '재방문 (2회+)', count: stats.repeat_stats.repeat_ips, color: '#6366f1' },
                        ].map((item, i) => {
                          const pct = stats.repeat_stats.total_ips > 0 ? Math.round(item.count / stats.repeat_stats.total_ips * 100) : 0;
                          return (
                            <div key={i} style={{ marginBottom: 6 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: 2 }}>
                                <span style={{ color: '#374151' }}>{item.label}</span>
                                <span style={{ fontWeight: 700, color: '#6b7280' }}>{pct}%</span>
                              </div>
                              <div style={{ height: 6, background: '#f1f5f9', borderRadius: 3 }}>
                                <div style={{ height: '100%', width: `${pct}%`, background: item.color, borderRadius: 3 }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>

                {/* 유입 경로 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>유입 경로</h3>
                  {stats.referrer_stats.map((r, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                      <SourceBadge source={r.source} />
                      <div style={{ flex: 1, margin: '0 10px', height: 6, background: '#f1f5f9', borderRadius: 4 }}>
                        <div style={{ height: '100%', width: `${Math.round(r.count / totalVisits * 100)}%`, background: SRC_COLOR[r.source]?.bg || '#6366f1', borderRadius: 4 }} />
                      </div>
                      <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', minWidth: 50, textAlign: 'right' }}>
                        {fmt(r.count)} <span style={{ color: '#9ca3af', fontWeight: 400, fontSize: '0.72rem' }}>({Math.round(r.count / totalVisits * 100)}%)</span>
                      </span>
                    </div>
                  ))}
                  {stats.referrer_stats.length === 0 && <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>데이터 없음</p>}
                </div>

                {/* 체류시간 분포 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>체류시간 분포</h3>
                  {Object.entries(stats.dwell_distribution).map(([label, count], i) => {
                    const colors = ['#e5e7eb', '#fca5a5', '#fdba74', '#fde68a', '#6ee7b7', '#6366f1', '#8b5cf6'];
                    return (
                      <BarRow key={i} label={label} count={count} total={stats.summary.total_visits} color={colors[i] || '#6366f1'} />
                    );
                  })}
                </div>

                {/* 디바이스 + OS */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>디바이스</h3>
                  {stats.device_stats.map((r, i) => <BarRow key={i} label={r.device} count={r.count} total={totalVisits} color="#ec4899" />)}
                  <div style={{ borderTop: '1px solid #f1f5f9', marginTop: 12, paddingTop: 12 }}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>OS</h3>
                    {stats.os_stats.map((r, i) => <BarRow key={i} label={r.os} count={r.count} total={totalVisits} color="#8b5cf6" />)}
                  </div>
                </div>

                {/* 브라우저 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>브라우저</h3>
                  {stats.browser_stats.map((r, i) => <BarRow key={i} label={r.browser} count={r.count} total={totalVisits} color="#10b981" />)}
                </div>

                {/* 지역 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>접속 지역</h3>
                  {stats.location_stats.map((r, i) => <BarRow key={i} label={r.location} count={r.count} total={totalVisits} color="#06b6d4" />)}
                  {stats.location_stats.length === 0 && <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>데이터 없음</p>}
                </div>

                {/* 시간대 / 요일 히트맵 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>시간대별 방문 히트맵</h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                    {Array.from({ length: 24 }, (_, h) => {
                      const hs = String(h).padStart(2, '0');
                      const f = stats.hourly_stats.find(x => x.hour === hs);
                      const cnt = f?.count || 0;
                      const maxC = Math.max(...stats.hourly_stats.map(x => x.count), 1);
                      const in_ = cnt / maxC;
                      return (
                        <div key={h} title={`${h}시: ${cnt}회`}
                          style={{
                            width: 30, height: 30, borderRadius: 5,
                            background: `rgba(99,102,241,${0.07 + in_ * 0.93})`,
                            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                            fontSize: '0.6rem', fontWeight: 700,
                            color: in_ > 0.45 ? '#fff' : '#9ca3af',
                          }}>
                          {h}<br /><span style={{ fontSize: '0.55rem', fontWeight: 400 }}>{cnt}</span>
                        </div>
                      );
                    })}
                  </div>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '1rem 0 0.6rem' }}>요일별</h3>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {stats.weekday_stats.map((r, i) => {
                      const maxC = Math.max(...stats.weekday_stats.map(x => x.count), 1);
                      const in_ = r.count / maxC;
                      return (
                        <div key={i} title={`${r.weekday}요일: ${r.count}회`}
                          style={{
                            flex: 1, height: 42, borderRadius: 7,
                            background: `rgba(99,102,241,${0.07 + in_ * 0.93})`,
                            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                            fontSize: '0.68rem', fontWeight: 700,
                            color: in_ > 0.5 ? '#fff' : '#6b7280',
                          }}>
                          {r.weekday}
                          <span style={{ fontSize: '0.58rem', fontWeight: 400, marginTop: 1 }}>{r.count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* UTM 캠페인 */}
                {stats.utm_stats.length > 0 && (
                  <div style={card}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>UTM 캠페인 유입</h3>
                    {stats.utm_stats.map((r, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '0.4rem 0', borderBottom: '1px solid #f1f5f9' }}>
                        <div>
                          <SourceBadge source={r.source} />
                          {r.medium && <span style={{ fontSize: '0.7rem', color: '#6b7280', marginLeft: 4 }}>{r.medium}</span>}
                          {r.campaign && <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginTop: 1 }}>{r.campaign}</div>}
                        </div>
                        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#6366f1' }}>{fmt(r.count)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 일별 추이 */}
              <div style={card}>
                <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>일별 방문 추이</h3>
                {stats.daily_visits.length > 0 ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 70, marginBottom: 6 }}>
                      {[...stats.daily_visits].reverse().map((d, i) => {
                        const maxC = Math.max(...stats.daily_visits.map(x => x.count), 1);
                        const h = Math.max(3, (d.count / maxC) * 65);
                        return (
                          <div key={i} title={`${d.date}: ${d.count}회`}
                            style={{ flex: 1, height: h, background: '#6366f1', borderRadius: '3px 3px 0 0', opacity: 0.75, minWidth: 3 }} />
                        );
                      })}
                    </div>
                    <div style={{ maxHeight: 150, overflowY: 'auto' }}>
                      {[...stats.daily_visits].reverse().map((d, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid #f8fafc' }}>
                          <span style={{ fontSize: '0.78rem', color: '#6b7280' }}>{d.date}</span>
                          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#6366f1' }}>{fmt(d.count)}회</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>데이터 없음</p>}
              </div>
            </>
          )}

          {/* ════════════════════════════════════════════════
              페이지 흐름 탭
          ════════════════════════════════════════════════ */}
          {activeTab === 'flow' && (
            flowLoading ? <div style={{ padding: '3rem', textAlign: 'center' }}><Loading /></div> :
            flow ? (
              <>
                {/* 세션 요약 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                  <div style={statCard('#6366f1')}>
                    <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>총 세션</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#6366f1' }}>{fmt(flow.summary.total_sessions)}</div>
                  </div>
                  <div style={statCard('#f59e0b')}>
                    <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>이탈 세션</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f59e0b' }}>{fmt(flow.summary.bounce_sessions)}</div>
                    <div style={{ fontSize: '0.68rem', color: '#9ca3af' }}>바운스율</div>
                  </div>
                  <div style={statCard(flow.summary.bounce_rate > 70 ? '#ef4444' : flow.summary.bounce_rate > 50 ? '#f59e0b' : '#10b981')}>
                    <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: 3 }}>바운스율</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: flow.summary.bounce_rate > 70 ? '#ef4444' : flow.summary.bounce_rate > 50 ? '#f59e0b' : '#10b981' }}>
                      {flow.summary.bounce_rate}%
                    </div>
                    <div style={{ fontSize: '0.68rem', color: '#9ca3af' }}>1페이지만 보고 이탈</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>

                  {/* 세션 깊이 */}
                  <div style={card}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>세션 깊이 (1회 방문당 페이지 수)</h3>
                    {flow.session_depth.map((d, i) => (
                      <BarRow key={i} label={d.label} count={d.count} total={flow.summary.total_sessions} color={['#e5e7eb', '#fca5a5', '#fdba74', '#6ee7b7', '#6366f1'][i] || '#6366f1'} />
                    ))}
                  </div>

                  {/* 입장 페이지 */}
                  <div style={card}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>🚪 입장 페이지 (Landing)</h3>
                    <p style={{ fontSize: '0.72rem', color: '#9ca3af', margin: '0 0 0.6rem' }}>방문자가 가장 먼저 들어온 페이지</p>
                    {flow.entry_pages.map((r, i) => (
                      <BarRow key={i} label={shortenUrl(r.page_url)} count={r.count} total={flow.summary.total_sessions} color="#10b981" sub={i === 0 ? '(메인 유입)' : ''} />
                    ))}
                    {flow.entry_pages.length === 0 && <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>세션 데이터 없음</p>}
                  </div>

                  {/* 이탈 페이지 */}
                  <div style={card}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>🚪 이탈 페이지 (Exit)</h3>
                    <p style={{ fontSize: '0.72rem', color: '#9ca3af', margin: '0 0 0.6rem' }}>방문자가 마지막으로 떠난 페이지</p>
                    {flow.exit_pages.map((r, i) => (
                      <BarRow key={i} label={shortenUrl(r.page_url)} count={r.count} total={flow.summary.total_sessions} color="#ef4444" />
                    ))}
                    {flow.exit_pages.length === 0 && <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>세션 데이터 없음</p>}
                  </div>
                </div>

                {/* 페이지별 이탈률 */}
                <div style={{ ...card, marginBottom: '1rem' }}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.8rem' }}>페이지별 이탈률</h3>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr>
                          {['페이지', '총 조회', '이탈 수', '이탈률', ''].map((h, i) => (
                            <th key={i} style={{ ...th, textAlign: i >= 1 ? 'right' : 'left' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {flow.exit_rate_by_page.map((r, i) => (
                          <tr key={i}>
                            <td style={td}>
                              <div style={{ fontWeight: 600, fontSize: '0.82rem' }}>{shortenUrl(r.page_url)}</div>
                              <div style={{ fontSize: '0.7rem', color: '#9ca3af' }}>{r.page_url}</div>
                            </td>
                            <td style={{ ...td, textAlign: 'right' }}>{fmt(r.total_views)}</td>
                            <td style={{ ...td, textAlign: 'right', color: '#ef4444', fontWeight: 600 }}>{fmt(r.exit_count)}</td>
                            <td style={{ ...td, textAlign: 'right' }}>
                              <span style={{
                                padding: '2px 8px', borderRadius: 8, fontSize: '0.78rem', fontWeight: 700,
                                background: r.exit_rate > 70 ? '#fee2e2' : r.exit_rate > 40 ? '#fef3c7' : '#dcfce7',
                                color: r.exit_rate > 70 ? '#b91c1c' : r.exit_rate > 40 ? '#92400e' : '#166534',
                              }}>{r.exit_rate}%</span>
                            </td>
                            <td style={{ ...td, minWidth: 100 }}>
                              <div style={{ height: 6, background: '#f1f5f9', borderRadius: 4 }}>
                                <div style={{ height: '100%', width: `${r.exit_rate}%`, background: r.exit_rate > 70 ? '#ef4444' : r.exit_rate > 40 ? '#f59e0b' : '#10b981', borderRadius: 4 }} />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 페이지 전환 흐름 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.4rem' }}>페이지 전환 흐름 (A → B)</h3>
                  <p style={{ fontSize: '0.72rem', color: '#9ca3af', margin: '0 0 0.8rem' }}>동일 세션 내에서 연속으로 이동한 페이지 쌍</p>
                  {flow.page_flow.length === 0 ? (
                    <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>다중 페이지 세션 데이터 없음</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {flow.page_flow.map((r, i) => (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: 8, padding: '0.5rem 0.75rem',
                          background: '#f8fafc', borderRadius: 8, flexWrap: 'wrap',
                        }}>
                          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#374151', background: '#e0e7ff', padding: '2px 8px', borderRadius: 6 }}>
                            {shortenUrl(r.from_page)}
                          </span>
                          <span style={{ color: '#6366f1', fontWeight: 700 }}>→</span>
                          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#374151', background: '#d1fae5', padding: '2px 8px', borderRadius: 6 }}>
                            {shortenUrl(r.to_page)}
                          </span>
                          <span style={{ marginLeft: 'auto', fontSize: '0.8rem', fontWeight: 700, color: '#6366f1' }}>{fmt(r.count)}회</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : <div style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>데이터를 불러오는 중...</div>
          )}

          {/* ════════════════════════════════════════════════
              페이지별 분석 탭
          ════════════════════════════════════════════════ */}
          {activeTab === 'pages' && stats && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.07)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>페이지별 방문 현황</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>{stats.page_stats.length}개 페이지</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['#', '페이지', '방문수', '고유 방문자', '평균 체류', '비율'].map((h, i) => (
                        <th key={i} style={{ ...th, textAlign: i >= 2 ? 'right' : 'left' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {stats.page_stats.map((p, i) => {
                      const pct = Math.round((p.count / totalVisits) * 100);
                      return (
                        <tr key={i}>
                          <td style={{ ...td, color: '#9ca3af', fontWeight: 600 }}>{i + 1}</td>
                          <td style={td}>
                            <div style={{ fontWeight: 600, color: '#374151', fontSize: '0.83rem' }}>{shortenUrl(p.page_url)}</div>
                            <div style={{ fontSize: '0.7rem', color: '#9ca3af', wordBreak: 'break-all' }}>{p.page_url}</div>
                          </td>
                          <td style={{ ...td, textAlign: 'right', fontWeight: 700, color: '#6366f1' }}>{fmt(p.count)}</td>
                          <td style={{ ...td, textAlign: 'right', color: '#10b981', fontWeight: 600 }}>{fmt(p.unique_count)}</td>
                          <td style={{ ...td, textAlign: 'right', color: '#06b6d4', fontWeight: 600 }}>{fmtDuration(p.avg_duration)}</td>
                          <td style={{ ...td, minWidth: 120 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                              <div style={{ flex: 1, height: 6, background: '#f1f5f9', borderRadius: 4 }}>
                                <div style={{ height: '100%', width: `${pct}%`, background: '#6366f1', borderRadius: 4 }} />
                              </div>
                              <span style={{ fontSize: '0.72rem', color: '#9ca3af', width: 28, textAlign: 'right' }}>{pct}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {stats.page_stats.length === 0 && (
                <div style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>WordPress 방문 데이터 없음</div>
              )}
            </div>
          )}

          {/* ════════════════════════════════════════════════
              방문자별 탭 (IP별)
          ════════════════════════════════════════════════ */}
          {activeTab === 'sessions' && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.07)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>방문자별 분석 (IP 기준)</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(sessionTotal)}명</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['IP', '위치', '유입경로', '재방문', '세션', '페이지뷰', '체류', '스크롤', '기기', '첫방문', '마지막방문'].map(h => (
                        <th key={h} style={th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s, i) => (
                      <tr key={i} style={{ background: s.is_repeat ? '#fefce8' : undefined }}>
                        <td style={{ ...td, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {s.ip_address}
                        </td>
                        <td style={{ ...td, fontSize: '0.78rem' }}>
                          {s.city || s.region || s.country ? (
                            <span title={[s.country, s.region, s.city].filter(Boolean).join(', ')}>
                              {s.city || s.region || s.country}
                            </span>
                          ) : <span style={{ color: '#d1d5db' }}>-</span>}
                        </td>
                        <td style={td}><SourceBadge source={s.source} /></td>
                        <td style={{ ...td, textAlign: 'center' }}>
                          {s.is_repeat ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
                              <span style={{ background: '#fef08a', color: '#854d0e', padding: '2px 7px', borderRadius: 8, fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'nowrap' }}>
                                🔄 {s.sessions}회 방문
                              </span>
                              {s.visit_days > 1 && (
                                <span style={{ fontSize: '0.62rem', color: '#9ca3af' }}>{s.visit_days}일에 걸쳐</span>
                              )}
                            </div>
                          ) : (
                            <span style={{ fontSize: '0.72rem', color: '#9ca3af' }}>신규</span>
                          )}
                        </td>
                        <td style={{ ...td, textAlign: 'center', fontWeight: 600, color: '#6366f1' }}>{s.sessions}</td>
                        <td style={{ ...td, textAlign: 'center', fontWeight: 600 }}>{s.page_views}</td>
                        <td style={td}>
                          {s.max_duration > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                              <span style={{
                                padding: '2px 7px', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600,
                                background: s.max_duration >= 180 ? '#dcfce7' : s.max_duration >= 60 ? '#dbeafe' : '#f3f4f6',
                                color: s.max_duration >= 180 ? '#166534' : s.max_duration >= 60 ? '#1d4ed8' : '#6b7280',
                              }}>{fmtDuration(s.max_duration)}</span>
                              <div style={{ display: 'flex', gap: 2 }}>
                                {s.has_10s && <span style={{ fontSize: '0.6rem', background: '#dbeafe', color: '#1d4ed8', padding: '1px 4px', borderRadius: 4 }}>10초✓</span>}
                                {s.has_30s && <span style={{ fontSize: '0.6rem', background: '#dcfce7', color: '#166534', padding: '1px 4px', borderRadius: 4 }}>30초✓</span>}
                              </div>
                            </div>
                          ) : <span style={{ color: '#d1d5db' }}>-</span>}
                        </td>
                        <td style={{ ...td, textAlign: 'center' }}>
                          {s.max_scroll_depth > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                              <span style={{
                                fontSize: '0.75rem', fontWeight: 700,
                                color: s.max_scroll_depth >= 75 ? '#6d28d9' : s.max_scroll_depth >= 50 ? '#7c3aed' : '#a78bfa',
                              }}>{s.max_scroll_depth}%</span>
                              <div style={{ width: 30, height: 4, background: '#f1f5f9', borderRadius: 2 }}>
                                <div style={{ height: '100%', width: `${s.max_scroll_depth}%`, background: '#8b5cf6', borderRadius: 2 }} />
                              </div>
                            </div>
                          ) : <span style={{ color: '#d1d5db', fontSize: '0.72rem' }}>-</span>}
                        </td>
                        <td style={td}>
                          {s.is_mobile ? (
                            <span style={{ background: '#fce7f3', color: '#be185d', padding: '2px 7px', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600 }}>모바일</span>
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>{s.device_type}</span>
                          )}
                        </td>
                        <td style={{ ...td, fontSize: '0.75rem', color: '#9ca3af', whiteSpace: 'nowrap' }}>{s.first_visit.slice(0, 10)}</td>
                        <td style={{ ...td, fontSize: '0.75rem', color: '#9ca3af', whiteSpace: 'nowrap' }}>{s.last_visit.slice(0, 10)}</td>
                      </tr>
                    ))}
                    {sessions.length === 0 && (
                      <tr><td colSpan={11} style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>데이터 없음</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', borderTop: '1px solid #e2e8f0', fontSize: '0.82rem', color: '#6b7280' }}>
                <span>{sessionTotal}명 / {sessTotal}페이지</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button disabled={sessionPage <= 1} onClick={() => setSessionPage(p => Math.max(1, p - 1))} style={{ ...btnStyle, background: sessionPage <= 1 ? '#f3f4f6' : '#e5e7eb', color: sessionPage <= 1 ? '#d1d5db' : '#374151', cursor: sessionPage <= 1 ? 'default' : 'pointer' }}>이전</button>
                  <button disabled={sessionPage >= sessTotal} onClick={() => setSessionPage(p => Math.min(sessTotal, p + 1))} style={{ ...btnStyle, background: sessionPage >= sessTotal ? '#f3f4f6' : '#e5e7eb', color: sessionPage >= sessTotal ? '#d1d5db' : '#374151', cursor: sessionPage >= sessTotal ? 'default' : 'pointer' }}>다음</button>
                </div>
              </div>
            </div>
          )}

          {/* ════════════════════════════════════════════════
              방문 로그 탭
          ════════════════════════════════════════════════ */}
          {activeTab === 'visitors' && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.07)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>방문 로그</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(visitorTotal)}건</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['일시', 'IP', '위치', '페이지', 'OS', '브라우저', '디바이스', '체류시간', '스크롤', '유입경로'].map(h => (
                        <th key={h} style={th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visitors.map(v => (
                      <tr key={v.id}>
                        <td style={{ ...td, whiteSpace: 'nowrap', color: '#6b7280', fontSize: '0.75rem' }}>{v.created_at}</td>
                        <td style={{ ...td, fontFamily: 'monospace', fontSize: '0.75rem' }}>{v.ip_address}</td>
                        <td style={{ ...td, fontSize: '0.75rem' }}>{v.city || v.region || v.country || <span style={{ color: '#d1d5db' }}>-</span>}</td>
                        <td style={{ ...td, maxWidth: 180 }}>
                          <div style={{ fontWeight: 600, fontSize: '0.78rem', color: '#374151', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={v.page_url}>
                            {shortenUrl(v.page_url)}
                          </div>
                        </td>
                        <td style={{ ...td, fontSize: '0.78rem' }}>{v.os}</td>
                        <td style={{ ...td, fontSize: '0.78rem' }}>{v.browser}</td>
                        <td style={td}>
                          {v.is_mobile ? (
                            <span style={{ background: '#fce7f3', color: '#be185d', padding: '2px 6px', borderRadius: 8, fontSize: '0.7rem', fontWeight: 600 }}>모바일</span>
                          ) : <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>{v.device_type}</span>}
                        </td>
                        <td style={td}>
                          {v.duration_seconds > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                              <span style={{
                                padding: '2px 7px', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600,
                                background: v.duration_seconds >= 180 ? '#dcfce7' : v.duration_seconds >= 60 ? '#dbeafe' : '#f3f4f6',
                                color: v.duration_seconds >= 180 ? '#166534' : v.duration_seconds >= 60 ? '#1d4ed8' : '#6b7280',
                              }}>{fmtDuration(v.duration_seconds)}</span>
                              <div style={{ display: 'flex', gap: 2 }}>
                                {v.milestone_10s && <span style={{ fontSize: '0.58rem', background: '#dbeafe', color: '#1d4ed8', padding: '1px 3px', borderRadius: 3 }}>10s✓</span>}
                                {v.milestone_30s && <span style={{ fontSize: '0.58rem', background: '#dcfce7', color: '#166534', padding: '1px 3px', borderRadius: 3 }}>30s✓</span>}
                              </div>
                            </div>
                          ) : <span style={{ color: '#d1d5db' }}>-</span>}
                        </td>
                        <td style={{ ...td, textAlign: 'center' }}>
                          {v.scroll_depth > 0 ? (
                            <span style={{
                              fontSize: '0.75rem', fontWeight: 700,
                              color: v.scroll_depth >= 75 ? '#6d28d9' : v.scroll_depth >= 50 ? '#7c3aed' : '#a78bfa',
                            }}>{v.scroll_depth}%</span>
                          ) : <span style={{ color: '#d1d5db', fontSize: '0.72rem' }}>-</span>}
                        </td>
                        <td style={td}>
                          <SourceBadge source={v.source} />
                          {v.utm_campaign && <div style={{ fontSize: '0.68rem', color: '#9ca3af', marginTop: 1 }}>{v.utm_campaign}</div>}
                        </td>
                      </tr>
                    ))}
                    {visitors.length === 0 && (
                      <tr><td colSpan={10} style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>데이터 없음</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', borderTop: '1px solid #e2e8f0', fontSize: '0.82rem', color: '#6b7280' }}>
                <span>{visitorTotal}건 / {visTotal}페이지</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button disabled={visitorPage <= 1} onClick={() => setVisitorPage(p => Math.max(1, p - 1))} style={{ ...btnStyle, background: visitorPage <= 1 ? '#f3f4f6' : '#e5e7eb', color: visitorPage <= 1 ? '#d1d5db' : '#374151', cursor: visitorPage <= 1 ? 'default' : 'pointer' }}>이전</button>
                  <button disabled={visitorPage >= visTotal} onClick={() => setVisitorPage(p => Math.min(visTotal, p + 1))} style={{ ...btnStyle, background: visitorPage >= visTotal ? '#f3f4f6' : '#e5e7eb', color: visitorPage >= visTotal ? '#d1d5db' : '#374151', cursor: visitorPage >= visTotal ? 'default' : 'pointer' }}>다음</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
