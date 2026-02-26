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

  const cardStyle: React.CSSProperties = {
    background: '#111',
    borderRadius: 12,
    padding: '1.25rem',
    border: '1px solid #222',
  };

  const statCardStyle: React.CSSProperties = {
    ...cardStyle,
    textAlign: 'center',
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '0.75rem 1.5rem',
    background: active ? '#39ff14' : '#222',
    color: active ? '#000' : '#9ca3af',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.9rem',
  });

  const tableStyle: React.CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '0.85rem',
    color: '#e5e5e5',
  };

  const thStyle: React.CSSProperties = {
    padding: '0.75rem 0.5rem',
    textAlign: 'left',
    fontWeight: 600,
    borderBottom: '2px solid #333',
    color: '#39ff14',
    whiteSpace: 'nowrap',
  };

  const tdStyle: React.CSSProperties = {
    padding: '0.6rem 0.5rem',
    borderBottom: '1px solid #222',
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '1.5rem', background: '#000', minHeight: '100vh', color: '#e5e5e5' }}>
      {/* 헤더 */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#39ff14', margin: 0 }}>
          견적서 로그 분석
        </h1>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.9rem', color: '#6b7280' }}>
          방문자 정보, 견적 계산 횟수, 사용자 행동 분석
        </p>
      </div>

      {/* 날짜 필터 */}
      <div style={{ ...cardStyle, marginBottom: '1rem', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <label style={{ fontSize: '0.82rem', color: '#9ca3af', marginRight: 8 }}>시작일</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            style={{
              padding: '0.5rem',
              background: '#1a1a1a',
              border: '1px solid #333',
              borderRadius: 6,
              color: '#e5e5e5',
            }}
          />
        </div>
        <div>
          <label style={{ fontSize: '0.82rem', color: '#9ca3af', marginRight: 8 }}>종료일</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            style={{
              padding: '0.5rem',
              background: '#1a1a1a',
              border: '1px solid #333',
              borderRadius: 6,
              color: '#e5e5e5',
            }}
          />
        </div>
        <button
          onClick={() => { setDateFrom(''); setDateTo(''); }}
          style={{
            padding: '0.5rem 1rem',
            background: '#333',
            border: 'none',
            borderRadius: 6,
            color: '#9ca3af',
            cursor: 'pointer',
          }}
        >
          초기화
        </button>
      </div>

      {/* 탭 */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
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
        <div style={{ textAlign: 'center', padding: '3rem' }}><Loading /></div>
      ) : (
        <>
          {/* 개요 탭 */}
          {activeTab === 'overview' && stats && (
            <>
              {/* 요약 카드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>총 방문수</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#39ff14' }}>{fmt(stats.summary.total_visits)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>고유 방문자</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#22c55e' }}>{fmt(stats.summary.unique_visitors)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>총 계산 횟수</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#3b82f6' }}>{fmt(stats.summary.total_calculations)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>고유 계산자</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#8b5cf6' }}>{fmt(stats.summary.unique_calculators)}</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>전환율</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f59e0b' }}>{stats.summary.conversion_rate}%</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>모바일 접속</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#ec4899' }}>{fmt(stats.summary.mobile_count)}</div>
                  <div style={{ fontSize: '0.72rem', color: '#6b7280' }}>{stats.summary.mobile_rate}%</div>
                </div>
                <div style={statCardStyle}>
                  <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 4 }}>터치 기기</div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#14b8a6' }}>{fmt(stats.summary.touch_device_count)}</div>
                </div>
              </div>

              {/* 통계 그리드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
                {/* OS 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>OS별 방문</h3>
                  {stats.os_stats.length === 0 ? (
                    <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {stats.os_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem' }}>{item.os}</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#39ff14' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 브라우저 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>브라우저별 방문</h3>
                  {stats.browser_stats.length === 0 ? (
                    <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {stats.browser_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem' }}>{item.browser}</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#22c55e' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 디바이스 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>디바이스별 방문</h3>
                  {stats.device_stats.length === 0 ? (
                    <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {stats.device_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem' }}>{item.device}</span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 접속 경로 통계 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>접속 경로</h3>
                  {stats.referrer_stats.length === 0 ? (
                    <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {stats.referrer_stats.map((item, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.source}
                          </span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#8b5cf6' }}>{fmt(item.count)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 브랜드 타입별 계산 */}
                <div style={cardStyle}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>브랜드 타입별 계산</h3>
                  {stats.brand_stats.length === 0 ? (
                    <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {stats.brand_stats.map((item, i) => (
                        <div key={i} style={{ padding: '0.75rem', background: '#1a1a1a', borderRadius: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{ fontWeight: 600 }}>{BRAND_LABEL[item.brand_type] || item.brand_type}</span>
                            <span style={{ color: '#39ff14', fontWeight: 600 }}>{fmt(item.count)}회</span>
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
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>시간대별 방문</h3>
                  {stats.hourly_stats.length === 0 ? (
                    <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                  ) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {stats.hourly_stats.map((item, i) => {
                        const maxCount = Math.max(...stats.hourly_stats.map(h => h.count));
                        const intensity = maxCount > 0 ? item.count / maxCount : 0;
                        return (
                          <div
                            key={i}
                            style={{
                              width: 28,
                              height: 28,
                              borderRadius: 4,
                              background: `rgba(57, 255, 20, ${0.1 + intensity * 0.9})`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.65rem',
                              color: intensity > 0.5 ? '#000' : '#9ca3af',
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
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginTop: 0, marginBottom: '1rem' }}>일별 추이 (최근 30일)</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div>
                    <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 8 }}>방문</div>
                    {stats.daily_visits.length === 0 ? (
                      <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                    ) : (
                      <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                        {stats.daily_visits.slice().reverse().map((item, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #222' }}>
                            <span style={{ fontSize: '0.8rem' }}>{item.date}</span>
                            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#39ff14' }}>{fmt(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.82rem', color: '#6b7280', marginBottom: 8 }}>계산</div>
                    {stats.daily_calculations.length === 0 ? (
                      <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>데이터 없음</div>
                    ) : (
                      <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                        {stats.daily_calculations.slice().reverse().map((item, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #222' }}>
                            <span style={{ fontSize: '0.8rem' }}>{item.date}</span>
                            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#3b82f6' }}>{fmt(item.count)}</span>
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
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', margin: 0 }}>방문자 로그</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(visitorTotal)}건</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>일시</th>
                      <th style={thStyle}>IP</th>
                      <th style={thStyle}>OS</th>
                      <th style={thStyle}>브라우저</th>
                      <th style={thStyle}>디바이스</th>
                      <th style={thStyle}>모바일</th>
                      <th style={thStyle}>화면</th>
                      <th style={thStyle}>접속경로</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visitors.map((v) => (
                      <tr key={v.id}>
                        <td style={tdStyle}>{v.created_at}</td>
                        <td style={tdStyle}>{v.ip_address}</td>
                        <td style={tdStyle}>{v.os}</td>
                        <td style={tdStyle}>{v.browser}</td>
                        <td style={tdStyle}>{v.device_type}</td>
                        <td style={tdStyle}>
                          {v.is_mobile === true ? (
                            <span style={{ color: '#ec4899', fontWeight: 600 }}>모바일</span>
                          ) : v.is_touch_device === true ? (
                            <span style={{ color: '#14b8a6' }}>터치</span>
                          ) : (
                            <span style={{ color: '#6b7280' }}>-</span>
                          )}
                        </td>
                        <td style={tdStyle}>{v.inner_width || v.screen_width}x{v.inner_height || v.screen_height}</td>
                        <td style={{ ...tdStyle, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={v.referrer}>
                          {v.referrer || '직접 접속'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* 페이지네이션 */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
                <button
                  onClick={() => setVisitorPage(p => Math.max(1, p - 1))}
                  disabled={visitorPage === 1}
                  style={{
                    padding: '0.5rem 1rem',
                    background: visitorPage === 1 ? '#222' : '#333',
                    border: 'none',
                    borderRadius: 6,
                    color: visitorPage === 1 ? '#6b7280' : '#e5e5e5',
                    cursor: visitorPage === 1 ? 'not-allowed' : 'pointer',
                  }}
                >
                  이전
                </button>
                <span style={{ padding: '0.5rem 1rem', color: '#9ca3af' }}>
                  {visitorPage} / {Math.ceil(visitorTotal / pageSize) || 1}
                </span>
                <button
                  onClick={() => setVisitorPage(p => p + 1)}
                  disabled={visitorPage >= Math.ceil(visitorTotal / pageSize)}
                  style={{
                    padding: '0.5rem 1rem',
                    background: visitorPage >= Math.ceil(visitorTotal / pageSize) ? '#222' : '#333',
                    border: 'none',
                    borderRadius: 6,
                    color: visitorPage >= Math.ceil(visitorTotal / pageSize) ? '#6b7280' : '#e5e5e5',
                    cursor: visitorPage >= Math.ceil(visitorTotal / pageSize) ? 'not-allowed' : 'pointer',
                  }}
                >
                  다음
                </button>
              </div>
            </div>
          )}

          {/* 견적 계산 로그 탭 */}
          {activeTab === 'calculations' && (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', margin: 0 }}>견적 계산 로그</h3>
                <span style={{ fontSize: '0.82rem', color: '#6b7280' }}>총 {fmt(calcTotal)}건</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>일시</th>
                      <th style={thStyle}>IP</th>
                      <th style={thStyle}>업체명</th>
                      <th style={thStyle}>이메일</th>
                      <th style={thStyle}>브랜드</th>
                      <th style={thStyle}>월 출고건</th>
                      <th style={thStyle}>총 금액</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calculations.map((c) => (
                      <tr key={c.id}>
                        <td style={tdStyle}>{c.created_at}</td>
                        <td style={tdStyle}>{c.ip_address}</td>
                        <td style={tdStyle}>{c.company_name || '-'}</td>
                        <td style={tdStyle}>{c.email || '-'}</td>
                        <td style={tdStyle}>{BRAND_LABEL[c.brand_type] || c.brand_type}</td>
                        <td style={{ ...tdStyle, textAlign: 'right' }}>{fmt(c.monthly_outbound || 0)}</td>
                        <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: '#39ff14' }}>₩{fmt(c.total_amount || 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* 페이지네이션 */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
                <button
                  onClick={() => setCalcPage(p => Math.max(1, p - 1))}
                  disabled={calcPage === 1}
                  style={{
                    padding: '0.5rem 1rem',
                    background: calcPage === 1 ? '#222' : '#333',
                    border: 'none',
                    borderRadius: 6,
                    color: calcPage === 1 ? '#6b7280' : '#e5e5e5',
                    cursor: calcPage === 1 ? 'not-allowed' : 'pointer',
                  }}
                >
                  이전
                </button>
                <span style={{ padding: '0.5rem 1rem', color: '#9ca3af' }}>
                  {calcPage} / {Math.ceil(calcTotal / pageSize) || 1}
                </span>
                <button
                  onClick={() => setCalcPage(p => p + 1)}
                  disabled={calcPage >= Math.ceil(calcTotal / pageSize)}
                  style={{
                    padding: '0.5rem 1rem',
                    background: calcPage >= Math.ceil(calcTotal / pageSize) ? '#222' : '#333',
                    border: 'none',
                    borderRadius: 6,
                    color: calcPage >= Math.ceil(calcTotal / pageSize) ? '#6b7280' : '#e5e5e5',
                    cursor: calcPage >= Math.ceil(calcTotal / pageSize) ? 'not-allowed' : 'pointer',
                  }}
                >
                  다음
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
