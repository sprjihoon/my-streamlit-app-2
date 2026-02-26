'use client';

import { useState, useEffect } from 'react';
import { Loading } from '@/components/Loading';

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

const BRAND_LABEL: Record<string, string> = { fashion: '패션', beauty: '뷰티', etc: '기타' };

export default function EstimateAnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [visitors, setVisitors] = useState<VisitorLog[]>([]);
  const [calculations, setCalculations] = useState<CalculateLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'visitors' | 'calculations'>('overview');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
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

  const inputStyle: React.CSSProperties = {
    padding: '0.5rem 0.65rem', border: '1px solid #d1d5db', borderRadius: 8,
    fontSize: '0.85rem', outline: 'none', background: '#fff',
  };

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

  const statCardStyle: React.CSSProperties = {
    ...cardStyle,
    textAlign: 'center',
    padding: '1.25rem 1rem',
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '0.6rem 1.25rem',
    background: active ? '#3b82f6' : '#f3f4f6',
    color: active ? '#fff' : '#6b7280',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.85rem',
  });

  const visitorTotalPages = Math.max(1, Math.ceil(visitorTotal / pageSize));
  const calcTotalPages = Math.max(1, Math.ceil(calcTotal / pageSize));

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '1rem' }}>
      <h1 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '1rem', color: '#1f2937' }}>
        견적서 로그 분석
      </h1>

      {/* 필터 바 */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end',
        background: '#fff', padding: '1rem', borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,.08)', marginBottom: '1rem',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>시작일</label>
          <input type="date" style={inputStyle} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>종료일</label>
          <input type="date" style={inputStyle} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        {(dateFrom || dateTo) && (
          <button onClick={() => { setDateFrom(''); setDateTo(''); }} style={{ ...btnStyle, background: '#e5e7eb', color: '#374151' }}>
            초기화
          </button>
        )}
      </div>

      {/* 탭 */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button style={tabStyle(activeTab === 'overview')} onClick={() => setActiveTab('overview')}>
          개요
        </button>
        <button style={tabStyle(activeTab === 'visitors')} onClick={() => setActiveTab('visitors')}>
          방문자 로그
        </button>
        <button style={tabStyle(activeTab === 'calculations')} onClick={() => setActiveTab('calculations')}>
          견적 계산 로그
        </button>
      </div>

      {loading && activeTab === 'overview' ? (
        <div style={{ padding: '3rem', textAlign: 'center' }}><Loading /></div>
      ) : (
        <>
          {/* 개요 탭 */}
          {activeTab === 'overview' && stats && (
            <>
              {/* 요약 카드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>총 방문수</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#3b82f6' }}>{fmt(stats.summary.total_visits)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>고유 방문자</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10b981' }}>{fmt(stats.summary.unique_visitors)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>총 계산 횟수</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#8b5cf6' }}>{fmt(stats.summary.total_calculations)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>전환율</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f59e0b' }}>{stats.summary.conversion_rate}%</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>모바일 접속</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#ec4899' }}>{fmt(stats.summary.mobile_count)}</div>
                  <div style={{ fontSize: '0.7rem', color: '#9ca3af' }}>{stats.summary.mobile_rate}%</div>
                </div>
              </div>

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
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>일시</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>IP</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>위치</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>OS</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>브라우저</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'center', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>디바이스</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'center', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>모바일</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>접속경로</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visitors.map((v) => (
                      <tr key={v.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.6rem', whiteSpace: 'nowrap', color: '#6b7280' }}>{v.created_at}</td>
                        <td style={{ padding: '0.6rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{v.ip_address}</td>
                        <td style={{ padding: '0.6rem', fontSize: '0.8rem' }}>
                          {v.country || v.region || v.city ? (
                            <span title={[v.country, v.region, v.city].filter(Boolean).join(', ')}>
                              {v.city || v.region || v.country || '-'}
                            </span>
                          ) : (
                            <span style={{ color: '#9ca3af' }}>-</span>
                          )}
                        </td>
                        <td style={{ padding: '0.6rem' }}>{v.os}</td>
                        <td style={{ padding: '0.6rem' }}>{v.browser}</td>
                        <td style={{ padding: '0.6rem', textAlign: 'center' }}>{v.device_type}</td>
                        <td style={{ padding: '0.6rem', textAlign: 'center' }}>
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
                        <td style={{ padding: '0.6rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#6b7280' }} title={v.referrer}>
                          {v.referrer || '직접 접속'}
                        </td>
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
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>일시</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>IP</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>업체명</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>이메일</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'center', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>브랜드</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>월 출고건</th>
                      <th style={{ padding: '0.7rem 0.6rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>총 금액</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calculations.map((c) => (
                      <tr key={c.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.6rem', whiteSpace: 'nowrap', color: '#6b7280' }}>{c.created_at}</td>
                        <td style={{ padding: '0.6rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>{c.ip_address}</td>
                        <td style={{ padding: '0.6rem', fontWeight: 500 }}>{c.company_name || '-'}</td>
                        <td style={{ padding: '0.6rem', color: '#6b7280' }}>{c.email || '-'}</td>
                        <td style={{ padding: '0.6rem', textAlign: 'center' }}>
                          <span style={{
                            display: 'inline-block', padding: '2px 10px', borderRadius: 12,
                            fontSize: '0.75rem', fontWeight: 600,
                            background: c.brand_type === 'fashion' ? '#dbeafe' : c.brand_type === 'beauty' ? '#fce7f3' : '#f3f4f6',
                            color: c.brand_type === 'fashion' ? '#1d4ed8' : c.brand_type === 'beauty' ? '#be185d' : '#374151',
                          }}>
                            {BRAND_LABEL[c.brand_type] || c.brand_type}
                          </span>
                        </td>
                        <td style={{ padding: '0.6rem', textAlign: 'right' }}>{fmt(c.monthly_outbound || 0)}</td>
                        <td style={{ padding: '0.6rem', textAlign: 'right', fontWeight: 600, color: '#1d4ed8' }}>₩{fmt(c.total_amount || 0)}</td>
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
