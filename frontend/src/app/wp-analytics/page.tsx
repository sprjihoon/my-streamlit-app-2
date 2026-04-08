'use client';

import { useState, useEffect } from 'react';
import { Loading } from '@/components/Loading';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Summary {
  total_visits: number;
  unique_visitors: number;
  mobile_count: number;
  touch_count: number;
  mobile_rate: number;
  avg_duration_seconds: number;
  max_duration_seconds: number;
  tracked_visit_count: number;
}

interface PageStat {
  page_url: string;
  count: number;
  unique_count: number;
  avg_duration: number;
}

interface ReferrerStat { source: string; count: number }
interface OsStat { os: string; count: number }
interface BrowserStat { browser: string; count: number }
interface DeviceStat { device: string; count: number }
interface HourlyStat { hour: string; count: number }
interface WeekdayStat { weekday: string; count: number }
interface LocationStat { location: string; count: number }
interface DailyStat { date: string; count: number }
interface UtmStat { source: string; medium: string; campaign: string; count: number }

interface Stats {
  summary: Summary;
  page_stats: PageStat[];
  referrer_stats: ReferrerStat[];
  os_stats: OsStat[];
  browser_stats: BrowserStat[];
  device_stats: DeviceStat[];
  hourly_stats: HourlyStat[];
  weekday_stats: WeekdayStat[];
  location_stats: LocationStat[];
  daily_visits: DailyStat[];
  utm_stats: UtmStat[];
}

interface VisitorLog {
  id: number;
  ip_address: string;
  country: string;
  region: string;
  city: string;
  page_url: string;
  referrer: string;
  os: string;
  browser: string;
  device_type: string;
  is_touch_device: boolean | null;
  is_mobile: boolean | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  duration_seconds: number;
  created_at: string;
}

function fmt(n: number) { return n.toLocaleString('ko-KR'); }

function fmtDuration(s: number): string {
  if (!s || s <= 0) return '-';
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return rem > 0 ? `${m}분 ${rem}초` : `${m}분`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}시간 ${rm}분` : `${h}시간`;
}

function shortenUrl(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname === '/' ? '홈' : u.pathname;
    return path;
  } catch {
    return url;
  }
}

const SOURCE_COLORS: Record<string, { bg: string; text: string }> = {
  'Instagram': { bg: '#e4405f', text: '#fff' },
  'YouTube': { bg: '#ff0000', text: '#fff' },
  'Naver': { bg: '#03c75a', text: '#fff' },
  'Google': { bg: '#4285f4', text: '#fff' },
  'Facebook': { bg: '#1877f2', text: '#fff' },
  'KakaoTalk': { bg: '#fee500', text: '#3c1e1e' },
  'TikTok': { bg: '#111', text: '#fff' },
  'X(Twitter)': { bg: '#000', text: '#fff' },
  '직접 접속': { bg: '#e5e7eb', text: '#374151' },
  '사이트 내 이동': { bg: '#dbeafe', text: '#1d4ed8' },
  'Daum': { bg: '#4a90d9', text: '#fff' },
  '기타': { bg: '#f3f4f6', text: '#6b7280' },
};

function SourceBadge({ source }: { source: string }) {
  const c = SOURCE_COLORS[source] || { bg: '#a855f7', text: '#fff' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10,
      fontSize: '0.72rem', fontWeight: 600, background: c.bg, color: c.text,
      whiteSpace: 'nowrap',
    }}>{source}</span>
  );
}

function BarRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: '0.82rem', color: '#374151', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        <span style={{ fontSize: '0.82rem', fontWeight: 600, color, flexShrink: 0, marginLeft: 8 }}>{fmt(count)} <span style={{ color: '#9ca3af', fontWeight: 400 }}>({pct}%)</span></span>
      </div>
      <div style={{ height: 6, background: '#f1f5f9', borderRadius: 4 }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 4, transition: 'width .3s' }} />
      </div>
    </div>
  );
}

type Tab = 'overview' | 'pages' | 'visitors';

export default function WpAnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [visitors, setVisitors] = useState<VisitorLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [visitorPage, setVisitorPage] = useState(1);
  const [visitorTotal, setVisitorTotal] = useState(0);
  const pageSize = 20;

  useEffect(() => { loadStats(); }, [dateFrom, dateTo]);

  useEffect(() => {
    if (activeTab === 'visitors') loadVisitors();
  }, [activeTab, visitorPage, dateFrom, dateTo]);

  async function loadStats() {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (dateFrom) p.append('date_from', dateFrom);
      if (dateTo) p.append('date_to', dateTo);
      const res = await fetch(`${API_BASE}/wp-analytics/stats?${p}`);
      if (!res.ok) throw new Error('stats failed');
      setStats(await res.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }

  async function loadVisitors() {
    try {
      const p = new URLSearchParams();
      if (dateFrom) p.append('date_from', dateFrom);
      if (dateTo) p.append('date_to', dateTo);
      p.append('page', String(visitorPage));
      p.append('page_size', String(pageSize));
      const res = await fetch(`${API_BASE}/wp-analytics/visitors?${p}`);
      if (!res.ok) throw new Error('visitors failed');
      const data = await res.json();
      setVisitors(data.items);
      setVisitorTotal(data.total);
    } catch (e) { console.error(e); }
  }

  const card: React.CSSProperties = {
    background: '#fff', borderRadius: 12, padding: '1.1rem',
    boxShadow: '0 1px 4px rgba(0,0,0,.07)',
  };
  const statCard: React.CSSProperties = { ...card, textAlign: 'center', padding: '1.25rem 0.75rem' };
  const tab = (active: boolean): React.CSSProperties => ({
    padding: '0.55rem 1.1rem', border: 'none', borderRadius: 8, cursor: 'pointer',
    fontWeight: 600, fontSize: '0.85rem',
    background: active ? '#6366f1' : '#f3f4f6',
    color: active ? '#fff' : '#6b7280',
    transition: 'all .15s',
  });
  const inputStyle: React.CSSProperties = {
    padding: '0.45rem 0.65rem', border: '1px solid #d1d5db', borderRadius: 8,
    fontSize: '0.85rem', outline: 'none', background: '#fff',
  };
  const btn: React.CSSProperties = {
    padding: '0.45rem 0.9rem', border: 'none', borderRadius: 8,
    fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer',
  };

  const totalVisits = stats?.summary.total_visits || 0;
  const visitorTotalPages = Math.max(1, Math.ceil(visitorTotal / pageSize));

  const getSource = (v: VisitorLog) => {
    if (v.utm_source) {
      const s = v.utm_source.toLowerCase();
      if (s === 'instagram') return 'Instagram';
      if (s === 'youtube') return 'YouTube';
      if (s === 'naver') return 'Naver';
      if (s === 'google') return 'Google';
      if (s === 'facebook') return 'Facebook';
      if (s === 'kakao' || s === 'kakaotalk') return 'KakaoTalk';
      if (s === 'tiktok') return 'TikTok';
      if (s === 'twitter' || s === 'x') return 'X(Twitter)';
      return v.utm_source;
    }
    if (v.referrer) {
      const r = v.referrer.toLowerCase();
      if (r.includes('instagram')) return 'Instagram';
      if (r.includes('youtube')) return 'YouTube';
      if (r.includes('naver')) return 'Naver';
      if (r.includes('google')) return 'Google';
      if (r.includes('facebook')) return 'Facebook';
      if (r.includes('kakao')) return 'KakaoTalk';
      if (r.includes('tiktok')) return 'TikTok';
      if (r.includes('twitter') || r.includes('x.com')) return 'X(Twitter)';
      if (r.includes('spring3pl')) return '사이트 내 이동';
      return '기타';
    }
    return '직접 접속';
  };

  return (
    <div style={{ maxWidth: 1040, margin: '0 auto', padding: '1rem' }}>

      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: '1rem' }}>
        <div style={{
          width: 36, height: 36, background: '#6366f1', borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.1rem',
        }}>🌐</div>
        <div>
          <h1 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#1f2937', margin: 0 }}>
            WordPress 사이트 분석
          </h1>
          <p style={{ fontSize: '0.75rem', color: '#9ca3af', margin: 0 }}>spring3pl.co.kr 전체 페이지 방문자 데이터</p>
        </div>
      </div>

      {/* 필터 */}
      <div style={{ ...card, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end', marginBottom: '1rem' }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: '#6b7280', marginBottom: 3 }}>시작일</label>
          <input type="date" style={inputStyle} value={dateFrom} onChange={e => { setDateFrom(e.target.value); setVisitorPage(1); }} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: '#6b7280', marginBottom: 3 }}>종료일</label>
          <input type="date" style={inputStyle} value={dateTo} onChange={e => { setDateTo(e.target.value); setVisitorPage(1); }} />
        </div>
        {(dateFrom || dateTo) && (
          <button onClick={() => { setDateFrom(''); setDateTo(''); setVisitorPage(1); }}
            style={{ ...btn, background: '#e5e7eb', color: '#374151' }}>초기화</button>
        )}
      </div>

      {/* 탭 */}
      <div style={{ display: 'flex', gap: 6, marginBottom: '1rem' }}>
        <button style={tab(activeTab === 'overview')} onClick={() => setActiveTab('overview')}>개요</button>
        <button style={tab(activeTab === 'pages')} onClick={() => setActiveTab('pages')}>페이지별 분석</button>
        <button style={tab(activeTab === 'visitors')} onClick={() => { setActiveTab('visitors'); }}>방문자 로그</button>
      </div>

      {loading && activeTab === 'overview' ? (
        <div style={{ padding: '4rem', textAlign: 'center' }}><Loading /></div>
      ) : (
        <>
          {/* ── 개요 탭 ─────────────────────────────────── */}
          {activeTab === 'overview' && stats && (
            <>
              {/* 요약 카드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                <div style={statCard}>
                  <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 4 }}>총 방문수</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#6366f1' }}>{fmt(stats.summary.total_visits)}</div>
                </div>
                <div style={statCard}>
                  <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 4 }}>고유 방문자</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#10b981' }}>{fmt(stats.summary.unique_visitors)}</div>
                </div>
                <div style={statCard}>
                  <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 4 }}>모바일</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#ec4899' }}>{fmt(stats.summary.mobile_count)}</div>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af' }}>{stats.summary.mobile_rate}%</div>
                </div>
                <div style={statCard}>
                  <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 4 }}>평균 체류시간</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#06b6d4' }}>{fmtDuration(stats.summary.avg_duration_seconds)}</div>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af' }}>최대 {fmtDuration(stats.summary.max_duration_seconds)}</div>
                </div>
                <div style={statCard}>
                  <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 4 }}>페이지 수</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f59e0b' }}>{stats.page_stats.length}</div>
                </div>
              </div>

              {/* 통계 그리드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>

                {/* 접속 경로 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>유입 경로</h3>
                  {stats.referrer_stats.map((r, i) => (
                    <BarRow key={i} label={r.source} count={r.count} total={totalVisits} color="#6366f1" />
                  ))}
                  {stats.referrer_stats.length === 0 && <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>데이터 없음</p>}
                </div>

                {/* 디바이스 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>디바이스</h3>
                  {stats.device_stats.map((r, i) => (
                    <BarRow key={i} label={r.device} count={r.count} total={totalVisits} color="#ec4899" />
                  ))}
                  <div style={{ borderTop: '1px solid #f1f5f9', marginTop: 10, paddingTop: 10 }}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>OS</h3>
                    {stats.os_stats.map((r, i) => (
                      <BarRow key={i} label={r.os} count={r.count} total={totalVisits} color="#8b5cf6" />
                    ))}
                  </div>
                </div>

                {/* 브라우저 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>브라우저</h3>
                  {stats.browser_stats.map((r, i) => (
                    <BarRow key={i} label={r.browser} count={r.count} total={totalVisits} color="#10b981" />
                  ))}
                </div>

                {/* 지역 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>접속 지역</h3>
                  {stats.location_stats.map((r, i) => (
                    <BarRow key={i} label={r.location} count={r.count} total={totalVisits} color="#06b6d4" />
                  ))}
                  {stats.location_stats.length === 0 && <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>데이터 없음</p>}
                </div>

                {/* 시간대 히트맵 */}
                <div style={card}>
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>시간대별 방문</h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {Array.from({ length: 24 }, (_, h) => {
                      const hourStr = String(h).padStart(2, '0');
                      const found = stats.hourly_stats.find(x => x.hour === hourStr);
                      const cnt = found?.count || 0;
                      const maxC = Math.max(...stats.hourly_stats.map(x => x.count), 1);
                      const intensity = cnt / maxC;
                      return (
                        <div key={h} title={`${hourStr}시: ${cnt}회`}
                          style={{
                            width: 28, height: 28, borderRadius: 5,
                            background: `rgba(99,102,241,${0.08 + intensity * 0.92})`,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '0.62rem', fontWeight: 600,
                            color: intensity > 0.45 ? '#fff' : '#9ca3af',
                          }}>
                          {h}
                        </div>
                      );
                    })}
                  </div>
                  {/* 요일별 */}
                  <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '1rem 0 0.6rem' }}>요일별 방문</h3>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {stats.weekday_stats.map((r, i) => {
                      const maxC = Math.max(...stats.weekday_stats.map(x => x.count), 1);
                      const intensity = r.count / maxC;
                      return (
                        <div key={i} title={`${r.weekday}요일: ${r.count}회`}
                          style={{
                            flex: 1, height: 36, borderRadius: 6,
                            background: `rgba(99,102,241,${0.08 + intensity * 0.92})`,
                            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                            fontSize: '0.65rem', fontWeight: 700,
                            color: intensity > 0.5 ? '#fff' : '#6b7280',
                          }}>
                          {r.weekday}
                          <span style={{ fontSize: '0.58rem', fontWeight: 400 }}>{r.count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* UTM 유입 */}
                {stats.utm_stats.length > 0 && (
                  <div style={card}>
                    <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>UTM 캠페인 유입</h3>
                    {stats.utm_stats.map((r, i) => (
                      <div key={i} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '0.45rem 0', borderBottom: '1px solid #f1f5f9',
                      }}>
                        <div>
                          <SourceBadge source={r.source} />
                          {r.medium && <span style={{ fontSize: '0.72rem', color: '#6b7280', marginLeft: 4 }}>{r.medium}</span>}
                          {r.campaign && <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginTop: 1 }}>{r.campaign}</div>}
                        </div>
                        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#6366f1' }}>{fmt(r.count)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 일별 추이 */}
              <div style={card}>
                <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#374151', margin: '0 0 0.75rem' }}>일별 방문 추이 (최근 30일)</h3>
                {stats.daily_visits.length === 0 ? (
                  <p style={{ color: '#9ca3af', fontSize: '0.82rem', margin: 0 }}>데이터 없음</p>
                ) : (
                  <>
                    {/* 미니 바 차트 */}
                    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 60, marginBottom: 8 }}>
                      {[...stats.daily_visits].reverse().map((d, i) => {
                        const maxC = Math.max(...stats.daily_visits.map(x => x.count), 1);
                        const h = Math.max(4, (d.count / maxC) * 56);
                        return (
                          <div key={i} title={`${d.date}: ${d.count}회`}
                            style={{
                              flex: 1, height: h, background: '#6366f1', borderRadius: '3px 3px 0 0', opacity: 0.8,
                              minWidth: 4,
                            }} />
                        );
                      })}
                    </div>
                    <div style={{ maxHeight: 160, overflowY: 'auto' }}>
                      {[...stats.daily_visits].reverse().map((d, i) => (
                        <div key={i} style={{
                          display: 'flex', justifyContent: 'space-between',
                          padding: '3px 0', borderBottom: '1px solid #f8fafc',
                        }}>
                          <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>{d.date}</span>
                          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#6366f1' }}>{fmt(d.count)}회</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
          )}

          {/* ── 페이지별 분석 탭 ────────────────────────── */}
          {activeTab === 'pages' && stats && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.07)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>페이지별 방문 현황</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {stats.page_stats.length}개 페이지</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th style={{ padding: '0.7rem 1rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0' }}>#</th>
                      <th style={{ padding: '0.7rem 1rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0' }}>페이지</th>
                      <th style={{ padding: '0.7rem 1rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>방문수</th>
                      <th style={{ padding: '0.7rem 1rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>고유 방문자</th>
                      <th style={{ padding: '0.7rem 1rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>평균 체류</th>
                      <th style={{ padding: '0.7rem 1rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0' }}>비율</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.page_stats.map((p, i) => {
                      const pct = totalVisits > 0 ? Math.round((p.count / totalVisits) * 100) : 0;
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '0.65rem 1rem', color: '#9ca3af', fontWeight: 600 }}>{i + 1}</td>
                          <td style={{ padding: '0.65rem 1rem' }}>
                            <div style={{ fontWeight: 600, color: '#374151', fontSize: '0.85rem' }}>
                              {shortenUrl(p.page_url)}
                            </div>
                            <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginTop: 1, wordBreak: 'break-all' }}>
                              {p.page_url}
                            </div>
                          </td>
                          <td style={{ padding: '0.65rem 1rem', textAlign: 'right', fontWeight: 700, color: '#6366f1' }}>{fmt(p.count)}</td>
                          <td style={{ padding: '0.65rem 1rem', textAlign: 'right', color: '#10b981', fontWeight: 600 }}>{fmt(p.unique_count)}</td>
                          <td style={{ padding: '0.65rem 1rem', textAlign: 'right', color: '#06b6d4', fontWeight: 600 }}>{fmtDuration(p.avg_duration)}</td>
                          <td style={{ padding: '0.65rem 1rem', minWidth: 120 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <div style={{ flex: 1, height: 6, background: '#f1f5f9', borderRadius: 4 }}>
                                <div style={{ height: '100%', width: `${pct}%`, background: '#6366f1', borderRadius: 4 }} />
                              </div>
                              <span style={{ fontSize: '0.75rem', color: '#9ca3af', width: 30, textAlign: 'right' }}>{pct}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {stats.page_stats.length === 0 && (
                <div style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>
                  WordPress 방문 데이터가 없습니다. WPCode 스크립트가 활성화되어 있는지 확인하세요.
                </div>
              )}
            </div>
          )}

          {/* ── 방문자 로그 탭 ──────────────────────────── */}
          {activeTab === 'visitors' && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.07)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>방문자 로그</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(visitorTotal)}건</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.83rem' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      {['일시', 'IP', '페이지', '위치', 'OS', '브라우저', '디바이스', '체류시간', '유입경로'].map(h => (
                        <th key={h} style={{ padding: '0.65rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {visitors.map(v => (
                      <tr key={v.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.55rem 0.6rem', whiteSpace: 'nowrap', color: '#6b7280', fontSize: '0.78rem' }}>{v.created_at}</td>
                        <td style={{ padding: '0.55rem 0.6rem', fontFamily: 'monospace', fontSize: '0.78rem' }}>{v.ip_address}</td>
                        <td style={{ padding: '0.55rem 0.6rem', maxWidth: 180 }}>
                          <div style={{ fontWeight: 600, color: '#374151', fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                            title={v.page_url}>
                            {shortenUrl(v.page_url)}
                          </div>
                        </td>
                        <td style={{ padding: '0.55rem 0.6rem', fontSize: '0.78rem' }}>
                          {[v.city, v.region, v.country].filter(Boolean)[0] || <span style={{ color: '#d1d5db' }}>-</span>}
                        </td>
                        <td style={{ padding: '0.55rem 0.6rem' }}>{v.os}</td>
                        <td style={{ padding: '0.55rem 0.6rem' }}>{v.browser}</td>
                        <td style={{ padding: '0.55rem 0.6rem' }}>
                          {v.is_mobile ? (
                            <span style={{ background: '#fce7f3', color: '#be185d', padding: '2px 7px', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600 }}>모바일</span>
                          ) : (
                            <span style={{ color: '#9ca3af', fontSize: '0.78rem' }}>{v.device_type}</span>
                          )}
                        </td>
                        <td style={{ padding: '0.55rem 0.6rem', whiteSpace: 'nowrap' }}>
                          {v.duration_seconds > 0 ? (
                            <span style={{
                              background: v.duration_seconds >= 180 ? '#dcfce7' : v.duration_seconds >= 60 ? '#dbeafe' : '#f3f4f6',
                              color: v.duration_seconds >= 180 ? '#166534' : v.duration_seconds >= 60 ? '#1d4ed8' : '#6b7280',
                              padding: '2px 7px', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600,
                            }}>{fmtDuration(v.duration_seconds)}</span>
                          ) : <span style={{ color: '#d1d5db' }}>-</span>}
                        </td>
                        <td style={{ padding: '0.55rem 0.6rem' }}>
                          <SourceBadge source={getSource(v)} />
                          {v.utm_campaign && (
                            <div style={{ fontSize: '0.68rem', color: '#9ca3af', marginTop: 2 }}>{v.utm_campaign}</div>
                          )}
                        </td>
                      </tr>
                    ))}
                    {visitors.length === 0 && (
                      <tr>
                        <td colSpan={9} style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>
                          데이터가 없습니다.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.75rem 1rem', borderTop: '1px solid #e2e8f0', fontSize: '0.82rem', color: '#6b7280',
              }}>
                <span>{visitorTotal}건 / {visitorTotalPages}페이지</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button disabled={visitorPage <= 1} onClick={() => setVisitorPage(p => Math.max(1, p - 1))}
                    style={{ ...btn, background: visitorPage <= 1 ? '#f3f4f6' : '#e5e7eb', color: visitorPage <= 1 ? '#d1d5db' : '#374151', cursor: visitorPage <= 1 ? 'default' : 'pointer' }}>이전</button>
                  <button disabled={visitorPage >= visitorTotalPages} onClick={() => setVisitorPage(p => Math.min(visitorTotalPages, p + 1))}
                    style={{ ...btn, background: visitorPage >= visitorTotalPages ? '#f3f4f6' : '#e5e7eb', color: visitorPage >= visitorTotalPages ? '#d1d5db' : '#374151', cursor: visitorPage >= visitorTotalPages ? 'default' : 'pointer' }}>다음</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
