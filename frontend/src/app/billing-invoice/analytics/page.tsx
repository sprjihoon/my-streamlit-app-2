'use client';

import { useState, useEffect, useCallback } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── 타입 ────────────────────────────────────────────────────────────
interface Summary {
  invoice_count: number;
  total_billed: number;
  total_paid: number;
  total_unpaid: number;
}
interface Monthly { month: string; invoice_count: number; total: number; paid: number; unpaid: number; }
interface ByClient { client_name: string; invoice_count: number; total: number; paid: number; unpaid: number; }
interface ByCategory { category: string; total: number; }
interface UnpaidItem { id: string; client_name: string; invoice_date: string; due_date: string | null; total_amount: number; paid_amount: number; unpaid_amount: number; status: string; overdue: boolean; }

interface Analytics {
  year: string;
  summary: Summary;
  monthly: Monthly[];
  by_client: ByClient[];
  by_category: ByCategory[];
  unpaid_list: UnpaidItem[];
}

// ─── 유틸 ────────────────────────────────────────────────────────────
const fmt = (n: number) => n.toLocaleString('ko-KR') + '원';
const K = (n: number) => (n / 10000).toFixed(0) + '만';

const COLORS = ['#1a3c6e', '#2563eb', '#0891b2', '#16a34a', '#7c3aed', '#d97706', '#dc2626', '#84cc16', '#f97316', '#6b7280'];

// ─── SVG 바차트 ──────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function BarChart({ data, keyY = 'total', color = '#1a3c6e', h = 140 }: {
  data: any[];
  keyY?: string; color?: string; h?: number;
}) {
  if (!data.length) return <p style={{ color: '#9ca3af', fontSize: '0.8rem', textAlign: 'center', padding: '1rem' }}>데이터 없음</p>;
  const max = Math.max(...data.map(d => Number(d[keyY]) || 0), 1);
  const w = 100 / data.length;
  return (
    <svg viewBox={`0 0 100 ${h}`} preserveAspectRatio="none" style={{ width: '100%', height: h }}>
      {data.map((d, i) => {
        const val = Number(d[keyY]) || 0;
        const bh = (val / max) * (h - 22);
        const x = i * w + w * 0.1;
        const bw = w * 0.8;
        const y = h - 18 - bh;
        const lbl = String(d.month || d.client_name || '').slice(-5);
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={bh} fill={color} rx="1" opacity={0.85} />
            {bh > 14 && <text x={x + bw / 2} y={y + bh / 2 + 4} textAnchor="middle" fontSize="4" fill="white">{K(val)}</text>}
            <text x={x + bw / 2} y={h - 3} textAnchor="middle" fontSize="4" fill="#9ca3af">{lbl}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── 도넛차트 ────────────────────────────────────────────────────────
function Donut({ data }: { data: { label: string; value: number }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  let cum = 0;
  const r = 32; const cx = 40; const cy = 40;
  const paths = data.map((d, i) => {
    const frac = d.value / total;
    const start = cum * 2 * Math.PI - Math.PI / 2;
    cum += frac;
    const end = cum * 2 * Math.PI - Math.PI / 2;
    if (frac < 0.001) return null;
    const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
    const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
    return <path key={i} d={`M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${frac > 0.5 ? 1 : 0},1 ${x2},${y2} Z`} fill={COLORS[i % COLORS.length]} opacity={0.9} />;
  });
  return (
    <svg viewBox="0 0 80 80" style={{ width: 80, height: 80, flexShrink: 0 }}>
      {paths}
      <circle cx={cx} cy={cy} r={13} fill="white" />
    </svg>
  );
}

// ─── 메인 페이지 ─────────────────────────────────────────────────────
export default function BillingAnalyticsPage() {
  const [token, setToken] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());
  const [selectedClient, setSelectedClient] = useState('');
  const [clientTrend, setClientTrend] = useState<Monthly[]>([]);

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    const admin = localStorage.getItem('isAdmin') === 'true';
    setToken(tok); setIsAdmin(admin);
    if (admin && tok) load(tok, new Date().getFullYear());
    else setLoading(false);
  }, []); // eslint-disable-line

  const load = useCallback(async (tok: string, y: number) => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/billing-invoice/analytics/summary?token=${tok}&year=${y}`);
      if (r.ok) setData(await r.json());
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadClientTrend = useCallback(async (tok: string, client: string, y: number) => {
    if (!client) { setClientTrend([]); return; }
    const r = await fetch(`${API}/billing-invoice/analytics/client-trend?token=${tok}&client_name=${encodeURIComponent(client)}&year=${y}`);
    if (r.ok) setClientTrend(await r.json());
  }, []);

  useEffect(() => {
    if (token && isAdmin) load(token, year);
  }, [year, token, isAdmin, load]);

  useEffect(() => {
    if (token && selectedClient) loadClientTrend(token, selectedClient, year);
    else setClientTrend([]);
  }, [selectedClient, year, token, loadClientTrend]);

  if (!isAdmin) return <div style={{ padding: '2rem', color: '#dc2626' }}>관리자 권한이 필요합니다.</div>;

  const card = (title: string, children: React.ReactNode) => (
    <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem' }}>
      <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#374151', marginBottom: '0.75rem' }}>{title}</div>
      {children}
    </div>
  );

  return (
    <div style={{ padding: '1.25rem', maxWidth: 1100 }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>청구금액 분석</h2>
          <p style={{ color: '#6b7280', fontSize: '0.8rem' }}>실 청구서 기준 매출·미수금 분석</p>
        </div>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          {[2024, 2025, 2026, 2027].map(y => (
            <button key={y} onClick={() => setYear(y)}
              style={{ padding: '0.35rem 0.75rem', border: '1px solid', borderColor: year === y ? '#1a3c6e' : '#d1d5db', background: year === y ? '#1a3c6e' : 'white', color: year === y ? 'white' : '#374151', borderRadius: 6, cursor: 'pointer', fontSize: '0.8rem' }}>
              {y}년
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p style={{ textAlign: 'center', color: '#9ca3af', padding: '3rem' }}>로딩 중...</p>
      ) : !data ? (
        <p style={{ textAlign: 'center', color: '#9ca3af', padding: '3rem' }}>데이터 없음</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

          {/* KPI */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
            {[
              { label: '총 청구 건수', value: `${data.summary.invoice_count}건`, color: '#1a3c6e' },
              { label: '총 청구액', value: fmt(data.summary.total_billed), color: '#1d4ed8' },
              { label: '총 입금액', value: fmt(data.summary.total_paid), color: '#16a34a' },
              { label: '총 미수금', value: fmt(data.summary.total_unpaid), color: data.summary.total_unpaid > 0 ? '#dc2626' : '#16a34a' },
            ].map(k => (
              <div key={k.label} style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: '0.25rem' }}>{k.label}</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: k.color }}>{k.value}</div>
              </div>
            ))}
          </div>

          {/* 월별 추이 */}
          {card('📈 월별 청구 추이',
            data.monthly.length === 0
              ? <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</p>
              : <>
                <BarChart data={data.monthly} keyY="total" color="#1a3c6e" />
                <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', fontSize: '0.72rem', color: '#9ca3af' }}>
                  {data.monthly.map(m => (
                    <div key={m.month} style={{ flex: 1, textAlign: 'center' }}>
                      <div style={{ color: '#374151', fontWeight: 600 }}>{m.month?.slice(5)}월</div>
                      <div>청구 {K(m.total)}</div>
                      <div style={{ color: '#16a34a' }}>입금 {K(m.paid)}</div>
                      {m.unpaid > 0 && <div style={{ color: '#dc2626' }}>미수 {K(m.unpaid)}</div>}
                    </div>
                  ))}
                </div>
              </>
          )}

          {/* 거래처별 + 카테고리별 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            {/* 거래처별 비중 */}
            {card('🏢 거래처별 청구 비중',
              data.by_client.length === 0
                ? <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</p>
                : <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  <Donut data={data.by_client.map(c => ({ label: c.client_name, value: c.total }))} />
                  <div style={{ flex: 1 }}>
                    {data.by_client.map((c, i) => {
                      const totalAll = data.by_client.reduce((s, x) => s + x.total, 0);
                      const pct = ((c.total / (totalAll || 1)) * 100).toFixed(1);
                      return (
                        <div key={i} style={{ marginBottom: '0.4rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                              <div style={{ width: 8, height: 8, borderRadius: 2, background: COLORS[i % COLORS.length] }} />
                              {c.client_name}
                            </span>
                            <span style={{ color: '#6b7280' }}>{pct}%</span>
                          </div>
                          <div style={{ height: 4, background: '#f3f4f6', borderRadius: 2, marginTop: '2px' }}>
                            <div style={{ height: 4, width: `${pct}%`, background: COLORS[i % COLORS.length], borderRadius: 2 }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
            )}

            {/* 항목별 분석 */}
            {card('📦 항목(카테고리)별 분석',
              data.by_category.length === 0
                ? <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>데이터 없음</p>
                : <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  <Donut data={data.by_category.map(c => ({ label: c.category, value: c.total }))} />
                  <div style={{ flex: 1 }}>
                    {data.by_category.map((c, i) => {
                      const totalAll = data.by_category.reduce((s, x) => s + x.total, 0);
                      const pct = ((c.total / (totalAll || 1)) * 100).toFixed(1);
                      return (
                        <div key={i} style={{ marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem' }}>
                          <div style={{ width: 8, height: 8, borderRadius: 2, background: COLORS[i % COLORS.length], flexShrink: 0 }} />
                          <span style={{ flex: 1 }}>{c.category}</span>
                          <span style={{ color: '#6b7280' }}>{c.total.toLocaleString()}</span>
                          <span style={{ color: '#9ca3af', minWidth: 36, textAlign: 'right' }}>{pct}%</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
            )}
          </div>

          {/* 거래처별 추이 */}
          {card('📉 거래처별 월별 추이',
            <>
              <div style={{ marginBottom: '0.75rem' }}>
                <select value={selectedClient} onChange={e => setSelectedClient(e.target.value)}
                  style={{ padding: '0.35rem 0.6rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.8rem' }}>
                  <option value="">거래처 선택</option>
                  {data.by_client.map(c => <option key={c.client_name} value={c.client_name}>{c.client_name}</option>)}
                </select>
              </div>
              {clientTrend.length > 0
                ? <>
                  <BarChart data={clientTrend} keyY="total" color="#0891b2" />
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))', gap: '0.4rem', marginTop: '0.5rem', fontSize: '0.72rem' }}>
                    {clientTrend.map(m => (
                      <div key={m.month} style={{ background: '#f9fafb', borderRadius: 6, padding: '0.4rem', textAlign: 'center' }}>
                        <div style={{ fontWeight: 600, color: '#374151' }}>{m.month?.slice(5)}월</div>
                        <div style={{ color: '#1d4ed8' }}>{K(m.total)}</div>
                        {m.unpaid > 0 && <div style={{ color: '#dc2626' }}>미수 {K(m.unpaid)}</div>}
                      </div>
                    ))}
                  </div>
                </>
                : <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>거래처를 선택하세요.</p>
              }
            </>
          )}

          {/* 미수금 추적 */}
          {card(`⚠️ 미수금 추적 (${data.unpaid_list.length}건)`,
            data.unpaid_list.length === 0
              ? <p style={{ color: '#16a34a', fontSize: '0.875rem' }}>✅ 미수금이 없습니다.</p>
              : <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ background: '#fef2f2', borderBottom: '2px solid #fca5a5' }}>
                      {['거래처', '청구일', '납기일', '청구금액', '입금액', '미수금액', '상태'].map(h => (
                        <th key={h} style={{ padding: '0.45rem 0.6rem', textAlign: 'left', color: '#9f1239', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.unpaid_list.map(r => (
                      <tr key={r.id} style={{ borderBottom: '1px solid #fee2e2', background: r.overdue ? '#fff5f5' : 'white' }}>
                        <td style={{ padding: '0.4rem 0.6rem', fontWeight: 600 }}>
                          {r.client_name}
                          {r.overdue && <span style={{ marginLeft: 4, fontSize: '0.65rem', background: '#dc2626', color: 'white', padding: '1px 5px', borderRadius: 3 }}>연체</span>}
                        </td>
                        <td style={{ padding: '0.4rem 0.6rem', color: '#6b7280' }}>{r.invoice_date}</td>
                        <td style={{ padding: '0.4rem 0.6rem', color: r.overdue ? '#dc2626' : '#6b7280', fontWeight: r.overdue ? 700 : 400 }}>{r.due_date || '-'}</td>
                        <td style={{ padding: '0.4rem 0.6rem' }}>{r.total_amount.toLocaleString()}</td>
                        <td style={{ padding: '0.4rem 0.6rem', color: '#16a34a' }}>{r.paid_amount.toLocaleString()}</td>
                        <td style={{ padding: '0.4rem 0.6rem', color: '#dc2626', fontWeight: 700 }}>{r.unpaid_amount.toLocaleString()}</td>
                        <td style={{ padding: '0.4rem 0.6rem' }}>
                          <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: '0.7rem', fontWeight: 700, background: r.status === '부분납' ? '#fff7ed' : '#fef2f2', color: r.status === '부분납' ? '#ea580c' : '#dc2626' }}>
                            {r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ background: '#fef2f2', borderTop: '2px solid #fca5a5' }}>
                      <td colSpan={5} style={{ padding: '0.45rem 0.6rem', fontWeight: 700, color: '#9f1239' }}>합계</td>
                      <td style={{ padding: '0.45rem 0.6rem', fontWeight: 700, color: '#dc2626' }}>
                        {data.unpaid_list.reduce((s, r) => s + r.unpaid_amount, 0).toLocaleString()}원
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
          )}

        </div>
      )}
    </div>
  );
}
