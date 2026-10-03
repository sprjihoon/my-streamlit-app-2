'use client';
import PageHeader from '@/components/ui/page-header';

import { useState, useEffect } from 'react';
import { Loading } from '@/components/Loading';
import { DateRangeControl, FilterBar, KpiStrip } from '@/components/data';
import { Button } from '@/components/ui/button';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Stats {
  summary: {
    total_visits: number;
    unique_visitors: number;
    total_calculations: number;
    unique_calculators: number;
    conversion_rate: number;
    touch_device_count: number;
    mobile_count: number;
    mobile_rate: number;
    avg_duration_seconds: number;
    max_duration_seconds: number;
    tracked_visit_count: number;
  };
  os_stats: { os: string; count: number }[];
  browser_stats: { browser: string; count: number }[];
  device_stats: { device: string; count: number }[];
  brand_stats: { brand_type: string; count: number; avg_outbound: number; avg_amount: number }[];
  daily_visits: { date: string; count: number }[];
  daily_calculations: { date: string; count: number }[];
  hourly_stats: { hour: string; count: number }[];
  referrer_stats: { source: string; count: number }[];
  location_stats: { location: string; count: number }[];
  utm_campaign_stats: { campaign: string; count: number }[];
}

interface VisitorLog {
  id: number;
  ip_address: string;
  country: string;
  region: string;
  is_touch_device: boolean | null;
  is_mobile: boolean | null;
  inner_width: number | null;
  inner_height: number | null;
  city: string;
  page_url: string;
  referrer: string;
  os: string;
  browser: string;
  device_type: string;
  screen_width: number;
  screen_height: number;
  language: string;
  timezone: string;
  session_id: string;
  created_at: string;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  duration_seconds: number;
}

interface CalculateLog {
  id: number;
  ip_address: string;
  session_id: string;
  company_name: string;
  email: string;
  brand_type: string;
  monthly_outbound: number;
  total_amount: number;
  created_at: string;
}

function fmt(n: number) {
  return n.toLocaleString('ko-KR');
}

function fmtDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '-';
  if (seconds < 60) return `${seconds}초`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s > 0 ? `${m}분 ${s}초` : `${m}분`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}시간 ${rm}분` : `${h}시간`;
}

const BRAND_LABEL: Record<string, string> = { fashion: '패션', beauty: '뷰티', etc: '기타' };

type Preset = '오늘' | '어제' | '7일' | '15일' | '30일' | '전체' | '직접입력';
const PRESETS: Preset[] = ['오늘', '어제', '7일', '15일', '30일', '전체', '직접입력'];

function calcPreset(p: Preset): { from: string; to: string } {
  const d = new Date();
  const iso = (x: Date) => x.toISOString().split('T')[0];
  const ago = (n: number) => { const t = new Date(d); t.setDate(d.getDate() - n); return t; };
  switch (p) {
    case '오늘':  return { from: iso(d), to: iso(d) };
    case '어제':  return { from: iso(ago(1)), to: iso(ago(1)) };
    case '7일':   return { from: iso(ago(6)), to: iso(d) };
    case '15일':  return { from: iso(ago(14)), to: iso(d) };
    case '30일':  return { from: iso(ago(29)), to: iso(d) };
    default:      return { from: '', to: '' };
  }
}

export default function EstimateAnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [visitors, setVisitors] = useState<VisitorLog[]>([]);
  const [calculations, setCalculations] = useState<CalculateLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'visitors' | 'calculations'>('overview');
  const [preset, setPreset] = useState<Preset>('30일');
  const [dateFrom, setDateFrom] = useState(calcPreset('30일').from);
  const [dateTo, setDateTo] = useState(calcPreset('30일').to);

  function applyPreset(p: Preset) {
    setPreset(p);
    if (p !== '직접입력') {
      const { from, to } = calcPreset(p);
      setDateFrom(from);
      setDateTo(to);
    }
  }
  const [visitorPage, setVisitorPage] = useState(1);
  const [visitorTotal, setVisitorTotal] = useState(0);
  const [calcPage, setCalcPage] = useState(1);
  const [calcTotal, setCalcTotal] = useState(0);
  const pageSize = 20;

  useEffect(() => {
    loadStats();
  }, [dateFrom, dateTo]);

  useEffect(() => {
    if (activeTab === 'visitors') {
      loadVisitors();
    } else if (activeTab === 'calculations') {
      loadCalculations();
    }
  }, [activeTab, visitorPage, calcPage, dateFrom, dateTo]);

  async function loadStats() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      const res = await fetch(`${API_BASE}/estimate-analytics/stats?${params}`);
      if (!res.ok) throw new Error('Failed to load stats');
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function loadVisitors() {
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      params.append('page', String(visitorPage));
      params.append('page_size', String(pageSize));
      const res = await fetch(`${API_BASE}/estimate-analytics/visitors?${params}`);
      if (!res.ok) throw new Error('Failed to load visitors');
      const data = await res.json();
      setVisitors(data.items);
      setVisitorTotal(data.total);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadCalculations() {
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      params.append('page', String(calcPage));
      params.append('page_size', String(pageSize));
      const res = await fetch(`${API_BASE}/estimate-analytics/calculations?${params}`);
      if (!res.ok) throw new Error('Failed to load calculations');
      const data = await res.json();
      setCalculations(data.items);
      setCalcTotal(data.total);
    } catch (err) {
      console.error(err);
    }
  }

  const btnStyle: React.CSSProperties = {
    padding: '0.5rem 1rem', border: 'none', borderRadius: 8,
    fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer', transition: 'all .15s',
  };

  const cardStyle: React.CSSProperties = {
    background: '#fff',
    borderRadius: 12,
    padding: '1rem',
    boxShadow: '0 1px 3px rgba(0,0,0,.08)',
  };

  const visitorTotalPages = Math.max(1, Math.ceil(visitorTotal / pageSize));
  const calcTotalPages = Math.max(1, Math.ceil(calcTotal / pageSize));

  return (
    <div>
      <PageHeader title="견적서 로그 분석" />

      {/* 필터 바 */}
      <FilterBar
        trailing={(dateFrom || dateTo) && preset !== '전체' ? (
          <span className="caption">{dateFrom || '전체'} ~ {dateTo || '전체'}</span>
        ) : null}
      >
        <div className="data-tabs tw-mb-0">
          {PRESETS.map((p) => (
            <Button key={p} type="button" variant={preset === p ? 'primary' : 'secondary'} onClick={() => applyPreset(p)}>{p}</Button>
          ))}
        </div>
        {preset === '직접입력' && (
          <DateRangeControl from={dateFrom} to={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        )}
      </FilterBar>

      {/* 탭 */}
      <div className="data-tabs">
        <Button type="button" variant={activeTab === 'overview' ? 'primary' : 'secondary'} onClick={() => setActiveTab('overview')}>개요</Button>
        <Button type="button" variant={activeTab === 'visitors' ? 'primary' : 'secondary'} onClick={() => setActiveTab('visitors')}>방문자 로그</Button>
        <Button type="button" variant={activeTab === 'calculations' ? 'primary' : 'secondary'} onClick={() => setActiveTab('calculations')}>견적 계산 로그</Button>
      </div>

      {loading && activeTab === 'overview' ? (
        <div style={{ padding: '3rem', textAlign: 'center' }}><Loading /></div>
      ) : (
        <>
          {/* 개요 탭 */}
          {activeTab === 'overview' && stats && (
            <>
              {/* 요약 카드 */}
              <KpiStrip
                items={[
                  { label: '총 방문수', value: fmt(stats.summary.total_visits) },
                  { label: '고유 방문자', value: <span className="tw-text-tillion-success">{fmt(stats.summary.unique_visitors)}</span> },
                  { label: '총 계산 횟수', value: fmt(stats.summary.total_calculations) },
                  { label: '전환율', value: <span className="tw-text-tillion-warning">{stats.summary.conversion_rate}%</span> },
                  { label: '모바일 접속', value: fmt(stats.summary.mobile_count), hint: `${stats.summary.mobile_rate}%` },
                  { label: '평균 체류시간', value: fmtDuration(stats.summary.avg_duration_seconds), hint: `최대 ${fmtDuration(stats.summary.max_duration_seconds)}` },
                ]}
              />

              {/* 통계 그리드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                {/* OS 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>OS별 방문</h3>
                  {stats.os_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stats.os_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', color: '#374151' }}>{item.os}</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 브라우저 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>브라우저별 방문</h3>
                  {stats.browser_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stats.browser_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', color: '#374151' }}>{item.browser}</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#10b981' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 디바이스 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>디바이스별 방문</h3>
                  {stats.device_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stats.device_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', color: '#374151' }}>{item.device}</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#8b5cf6' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 접속 경로 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>접속 경로</h3>
                  {stats.referrer_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stats.referrer_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', color: '#374151', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.source}
                          </span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f59e0b' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 접속 지역 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>접속 지역</h3>
                  {stats.location_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stats.location_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', color: '#374151' }}>
                            {item.location}
                          </span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#06b6d4' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* UTM 캠페인 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>캠페인별 유입</h3>
                  {stats.utm_campaign_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {stats.utm_campaign_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', color: '#374151', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.campaign}
                          </span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#a855f7' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 브랜드 타입별 계산 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>브랜드 타입별 계산</h3>
                  {stats.brand_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {stats.brand_stats.map((item, i) => (
                        <div key={i} style={{ padding: '0.6rem', background: '#f8fafc', borderRadius: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                            <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#374151' }}>{BRAND_LABEL[item.brand_type] || item.brand_type}</span>
                            <span style={{ color: '#3b82f6', fontWeight: 600, fontSize: '0.85rem' }}>{fmt(item.count)}회</span>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                            평균 출고: {fmt(item.avg_outbound)}건 | 평균 금액: ₩{fmt(item.avg_amount)}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 시간대별 방문 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>시간대별 방문</h3>
                  {stats.hourly_stats.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {stats.hourly_stats.map((item, i) => {
                        const maxCount = Math.max(...stats.hourly_stats.map(h => h.count));
                        const intensity = maxCount > 0 ? item.count / maxCount : 0;
                        return (
                          <div
                            key={i}
                            style={{
                              width: 26,
                              height: 26,
                              borderRadius: 4,
                              background: `rgba(59, 130, 246, ${0.1 + intensity * 0.9})`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.65rem',
                              color: intensity > 0.5 ? '#fff' : '#6b7280',
                              fontWeight: 600,
                            }}
                            title={`${item.hour}시: ${item.count}회`}
                          >
                            {item.hour}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* 일별 추이 */}
              <div style={{ ...cardStyle, marginTop: '1rem' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', marginTop: 0, marginBottom: '0.75rem' }}>일별 추이 (최근 30일)</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 6 }}>방문</div>
                    {stats.daily_visits.length === 0 ? (
                      <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                    ) : (
                      <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                        {stats.daily_visits.slice().reverse().map((item, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f1f5f9' }}>
                            <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>{item.date}</span>
                            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#3b82f6' }}>{fmt(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 6 }}>계산</div>
                    {stats.daily_calculations.length === 0 ? (
                      <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>데이터 없음</div>
                    ) : (
                      <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                        {stats.daily_calculations.slice().reverse().map((item, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f1f5f9' }}>
                            <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>{item.date}</span>
                            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#8b5cf6' }}>{fmt(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}

          {/* 방문자 로그 탭 */}
          {activeTab === 'visitors' && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,.08)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>방문자 로그</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(visitorTotal)}건</span>
              </div>
              <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' as const }}>
                <table>
                  <thead>
                    <tr>
                      <th>일시</th>
                      <th>IP</th>
                      <th>위치</th>
                      <th>OS</th>
                      <th>브라우저</th>
                      <th className="tw-text-center">디바이스</th>
                      <th className="tw-text-center">모바일</th>
                      <th className="tw-text-center">체류시간</th>
                      <th>유입경로</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visitors.map((v) => {
                      const getSourceDisplay = () => {
                        if (v.utm_source) {
                          const src = v.utm_source.toLowerCase();
                          if (src === 'instagram') return { name: 'Instagram', color: '#e4405f' };
                          if (src === 'youtube') return { name: 'YouTube', color: '#ff0000' };
                          if (src === 'naver') return { name: 'Naver', color: '#03c75a' };
                          if (src === 'google') return { name: 'Google', color: '#4285f4' };
                          if (src === 'facebook') return { name: 'Facebook', color: '#1877f2' };
                          if (src === 'kakao' || src === 'kakaotalk') return { name: 'KakaoTalk', color: '#fee500', textColor: '#3c1e1e' };
                          if (src === 'tiktok') return { name: 'TikTok', color: '#000000' };
                          return { name: v.utm_source, color: '#a855f7' };
                        }
                        if (v.referrer) {
                          const ref = v.referrer.toLowerCase();
                          if (ref.includes('instagram')) return { name: 'Instagram', color: '#e4405f' };
                          if (ref.includes('youtube')) return { name: 'YouTube', color: '#ff0000' };
                          if (ref.includes('naver')) return { name: 'Naver', color: '#03c75a' };
                          if (ref.includes('google')) return { name: 'Google', color: '#4285f4' };
                          if (ref.includes('facebook')) return { name: 'Facebook', color: '#1877f2' };
                          if (ref.includes('kakao')) return { name: 'KakaoTalk', color: '#fee500', textColor: '#3c1e1e' };
                          return { name: '기타', color: '#6b7280' };
                        }
                        return { name: '직접 접속', color: '#9ca3af' };
                      };
                      const source = getSourceDisplay();
                      return (
                      <tr key={v.id}>
                        <td>{v.created_at}</td>
                        <td style={{ padding: '0.6rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{v.ip_address}</td>
                        <td>
                          {v.country || v.region || v.city ? (
                            <span title={[v.country, v.region, v.city].filter(Boolean).join(', ')}>
                              {v.city || v.region || v.country || '-'}
                            </span>
                          ) : (
                            <span style={{ color: '#9ca3af' }}>-</span>
                          )}
                        </td>
                        <td>{v.os}</td>
                        <td>{v.browser}</td>
                        <td className="tw-text-center">{v.device_type}</td>
                        <td className="tw-text-center">
                          {v.is_mobile === true ? (
                            <span style={{
                              display: 'inline-block', padding: '2px 8px', borderRadius: 10,
                              fontSize: '0.75rem', fontWeight: 600, background: '#fce7f3', color: '#be185d',
                            }}>모바일</span>
                          ) : v.is_touch_device === true ? (
                            <span style={{
                              display: 'inline-block', padding: '2px 8px', borderRadius: 10,
                              fontSize: '0.75rem', fontWeight: 600, background: '#d1fae5', color: '#047857',
                            }}>터치</span>
                          ) : (
                            <span style={{ color: '#9ca3af' }}>-</span>
                          )}
                        </td>
                        <td className="tw-text-center">
                          {v.duration_seconds > 0 ? (
                            <span style={{
                              display: 'inline-block', padding: '2px 8px', borderRadius: 10,
                              fontSize: '0.75rem', fontWeight: 600,
                              background: v.duration_seconds >= 180 ? '#dcfce7' : v.duration_seconds >= 60 ? '#dbeafe' : '#f3f4f6',
                              color: v.duration_seconds >= 180 ? '#166534' : v.duration_seconds >= 60 ? '#1d4ed8' : '#6b7280',
                            }}>{fmtDuration(v.duration_seconds)}</span>
                          ) : (
                            <span style={{ color: '#d1d5db', fontSize: '0.8rem' }}>-</span>
                          )}
                        </td>
                        <td title={v.utm_campaign ? `캠페인: ${v.utm_campaign}` : v.referrer || ''}>
                          <span style={{
                            display: 'inline-block', padding: '2px 8px', borderRadius: 10,
                            fontSize: '0.75rem', fontWeight: 600,
                            background: source.color,
                            color: source.textColor || '#fff',
                          }}>{source.name}</span>
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {/* 페이지네이션 */}
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.75rem 1rem', borderTop: '1px solid #e2e8f0', fontSize: '0.82rem', color: '#6b7280',
              }}>
                <span>총 {visitorTotal}건 / {visitorTotalPages} 페이지</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    disabled={visitorPage <= 1}
                    onClick={() => setVisitorPage((p) => Math.max(1, p - 1))}
                    style={{
                      ...btnStyle, padding: '0.35rem 0.75rem', fontSize: '0.8rem',
                      background: visitorPage <= 1 ? '#f3f4f6' : '#e5e7eb', color: visitorPage <= 1 ? '#d1d5db' : '#374151',
                      cursor: visitorPage <= 1 ? 'default' : 'pointer',
                    }}
                  >
                    이전
                  </button>
                  <button
                    disabled={visitorPage >= visitorTotalPages}
                    onClick={() => setVisitorPage((p) => Math.min(visitorTotalPages, p + 1))}
                    style={{
                      ...btnStyle, padding: '0.35rem 0.75rem', fontSize: '0.8rem',
                      background: visitorPage >= visitorTotalPages ? '#f3f4f6' : '#e5e7eb', color: visitorPage >= visitorTotalPages ? '#d1d5db' : '#374151',
                      cursor: visitorPage >= visitorTotalPages ? 'default' : 'pointer',
                    }}
                  >
                    다음
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 견적 계산 로그 탭 */}
          {activeTab === 'calculations' && (
            <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,.08)', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#374151', margin: 0 }}>견적 계산 로그</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(calcTotal)}건</span>
              </div>
              <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' as const }}>
                <table>
                  <thead>
                    <tr>
                      <th>일시</th>
                      <th>IP</th>
                      <th>업체명</th>
                      <th>이메일</th>
                      <th className="tw-text-center">브랜드</th>
                      <th className="cell-num">월 출고건</th>
                      <th className="cell-num">총 금액</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calculations.map((c) => (
                      <tr key={c.id}>
                        <td>{c.created_at}</td>
                        <td style={{ padding: '0.6rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{c.ip_address}</td>
                        <td>{c.company_name || '-'}</td>
                        <td>{c.email || '-'}</td>
                        <td className="tw-text-center">
                          <span style={{
                            display: 'inline-block', padding: '2px 10px', borderRadius: 12,
                            fontSize: '0.75rem', fontWeight: 600,
                            background: c.brand_type === 'fashion' ? '#dbeafe' : c.brand_type === 'beauty' ? '#fce7f3' : '#f3f4f6',
                            color: c.brand_type === 'fashion' ? '#1d4ed8' : c.brand_type === 'beauty' ? '#be185d' : '#374151',
                          }}>
                            {BRAND_LABEL[c.brand_type] || c.brand_type}
                          </span>
                        </td>
                        <td className="cell-num">{fmt(c.monthly_outbound || 0)}</td>
                        <td className="cell-num">₩{fmt(c.total_amount || 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* 페이지네이션 */}
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.75rem 1rem', borderTop: '1px solid #e2e8f0', fontSize: '0.82rem', color: '#6b7280',
              }}>
                <span>총 {calcTotal}건 / {calcTotalPages} 페이지</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    disabled={calcPage <= 1}
                    onClick={() => setCalcPage((p) => Math.max(1, p - 1))}
                    style={{
                      ...btnStyle, padding: '0.35rem 0.75rem', fontSize: '0.8rem',
                      background: calcPage <= 1 ? '#f3f4f6' : '#e5e7eb', color: calcPage <= 1 ? '#d1d5db' : '#374151',
                      cursor: calcPage <= 1 ? 'default' : 'pointer',
                    }}
                  >
                    이전
                  </button>
                  <button
                    disabled={calcPage >= calcTotalPages}
                    onClick={() => setCalcPage((p) => Math.min(calcTotalPages, p + 1))}
                    style={{
                      ...btnStyle, padding: '0.35rem 0.75rem', fontSize: '0.8rem',
                      background: calcPage >= calcTotalPages ? '#f3f4f6' : '#e5e7eb', color: calcPage >= calcTotalPages ? '#d1d5db' : '#374151',
                      cursor: calcPage >= calcTotalPages ? 'default' : 'pointer',
                    }}
                  >
                    다음
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
