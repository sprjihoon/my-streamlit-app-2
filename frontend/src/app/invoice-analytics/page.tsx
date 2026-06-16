'use client';

import { useState, useEffect, useCallback } from 'react';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';
import {
  getInvoiceMonthlyTrend,
  getInvoiceMonthlyByCategory,
  getInvoiceMonthlyByVendor,
  getInvoiceAnalyticsSummary,
  InvoiceMonthlyTrend,
  InvoiceMonthlyCategoryData,
  InvoiceMonthlyVendorData,
  InvoiceAnalyticsSummary,
} from '@/lib/api';

// recharts + React 18 타입 호환 이슈 우회
// eslint-disable-next-line @typescript-eslint/no-var-requires
const recharts = require('recharts');
const { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ComposedChart } = recharts;

type TabType = 'monthly' | 'category' | 'vendor';

const CATEGORY_COLORS: Record<string, string> = {
  '기본출고비': '#2196F3',
  '택배요금': '#FF9800',
  '보관료': '#4CAF50',
  '박스/봉투': '#9C27B0',
  '입고검수': '#00BCD4',
  '도서산간': '#F44336',
  '합포장': '#3F51B5',
  '바코드': '#009688',
  '완충작업': '#E91E63',
  '반품': '#795548',
  '영상촬영': '#607D8B',
  '기타': '#9E9E9E',
};

const VENDOR_COLORS = [
  '#2196F3', '#FF9800', '#4CAF50', '#9C27B0', '#F44336',
  '#00BCD4', '#3F51B5', '#E91E63', '#795548', '#607D8B',
  '#FFC107', '#8BC34A', '#673AB7', '#FF5722', '#03A9F4',
];

function formatCurrency(num: number): string {
  if (num >= 10000) return `${(num / 10000).toFixed(0)}만`;
  return num.toLocaleString();
}

function formatFullCurrency(num: number): string {
  return `₩${num.toLocaleString()}`;
}

function CustomTooltipContent({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div style={{
      background: 'white', border: '1px solid #ddd', borderRadius: 8,
      padding: '0.75rem', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
      maxHeight: 300, overflowY: 'auto',
    }}>
      <p style={{ fontWeight: 'bold', marginBottom: '0.5rem', borderBottom: '1px solid #eee', paddingBottom: '0.25rem' }}>{label}</p>
      {payload.map((entry, idx) => (
        <p key={idx} style={{ margin: '0.2rem 0', fontSize: '0.85rem', color: entry.color }}>
          {entry.name}: {formatFullCurrency(entry.value)}
        </p>
      ))}
    </div>
  );
}

export default function InvoiceAnalyticsPage() {
  const [activeTab, setActiveTab] = useState<TabType>('monthly');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<InvoiceAnalyticsSummary | null>(null);
  const [trendData, setTrendData] = useState<InvoiceMonthlyTrend[]>([]);
  const [categoryData, setCategoryData] = useState<InvoiceMonthlyCategoryData | null>(null);
  const [vendorData, setVendorData] = useState<InvoiceMonthlyVendorData | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const summaryResult = await getInvoiceAnalyticsSummary();
      setSummary(summaryResult);

      switch (activeTab) {
        case 'monthly': {
          const trend = await getInvoiceMonthlyTrend();
          setTrendData(trend);
          break;
        }
        case 'category': {
          const cat = await getInvoiceMonthlyByCategory();
          setCategoryData(cat);
          break;
        }
        case 'vendor': {
          const ven = await getInvoiceMonthlyByVendor();
          setVendorData(ven);
          break;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tabs: { id: TabType; label: string }[] = [
    { id: 'monthly', label: '월별 청구금액 추이' },
    { id: 'category', label: '항목별 월별 추이' },
    { id: 'vendor', label: '거래처별 월별 추이' },
  ];

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>청구금액 분석</h1>
        <p style={{ color: 'var(--text-secondary)', margin: '0.25rem 0 0', fontSize: '0.8125rem' }}>
          인보이스 기반 월별 청구금액 추이를 확인합니다.
        </p>
      </div>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

      {/* 요약 카드 */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.8rem', color: '#999', marginBottom: '0.25rem' }}>분석 기간</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>
                {summary.first_period || '-'} ~ {summary.last_period || '-'}
              </div>
              <div style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>{summary.total_months}개월</div>
            </div>
          </Card>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.8rem', color: '#999', marginBottom: '0.25rem' }}>총 인보이스</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{summary.total_invoices}건</div>
            </div>
          </Card>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.8rem', color: '#999', marginBottom: '0.25rem' }}>총 청구금액</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2196F3' }}>
                {formatFullCurrency(summary.total_amount)}
              </div>
            </div>
          </Card>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.8rem', color: '#999', marginBottom: '0.25rem' }}>월평균 청구</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#4CAF50' }}>
                {formatFullCurrency(summary.avg_monthly_amount)}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* 탭 */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.6rem 1.2rem',
              border: 'none',
              borderRadius: '6px',
              backgroundColor: activeTab === tab.id ? '#2196F3' : '#e0e0e0',
              color: activeTab === tab.id ? 'white' : '#333',
              cursor: 'pointer',
              fontWeight: activeTab === tab.id ? 'bold' : 'normal',
              fontSize: '0.9rem',
              transition: 'all 0.2s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Loading />
      ) : (
        <>
          {/* 월별 추이 */}
          {activeTab === 'monthly' && (
            <div>
              <Card title="월별 청구금액 추이" style={{ marginBottom: '1.5rem' }}>
                {trendData.length === 0 ? (
                  <p style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>데이터가 없습니다.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={400}>
                    <ComposedChart data={trendData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                      <YAxis
                        yAxisId="amount"
                        tickFormatter={(v: number) => formatCurrency(v)}
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis
                        yAxisId="count"
                        orientation="right"
                        tick={{ fontSize: 12 }}
                      />
                      <Tooltip content={<CustomTooltipContent />} />
                      <Legend />
                      <Bar yAxisId="amount" dataKey="total_amount" name="청구금액" fill="#2196F3" radius={[4, 4, 0, 0]} />
                      <Line yAxisId="count" type="monotone" dataKey="invoice_count" name="인보이스 건수" stroke="#FF9800" strokeWidth={2} dot={{ r: 4 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
              </Card>

              {/* 테이블 */}
              <Card title="월별 상세 내역">
                {trendData.length === 0 ? (
                  <p style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>데이터가 없습니다.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#f5f5f5' }}>
                          <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>월</th>
                          <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>인보이스 수</th>
                          <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>청구금액</th>
                          <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>전월 대비</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trendData.map((row) => (
                          <tr key={row.period}>
                            <td style={{ padding: '0.6rem 0.75rem', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>{row.period}</td>
                            <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{row.invoice_count}건</td>
                            <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>
                              {formatFullCurrency(row.total_amount)}
                            </td>
                            <td style={{
                              padding: '0.6rem 0.75rem', textAlign: 'right', borderBottom: '1px solid #eee',
                              color: row.growth !== null ? (row.growth > 0 ? '#4CAF50' : row.growth < 0 ? '#F44336' : '#666') : '#999',
                            }}>
                              {row.growth !== null ? `${row.growth > 0 ? '+' : ''}${row.growth.toFixed(1)}%` : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr style={{ backgroundColor: '#f5f5f5', fontWeight: 'bold' }}>
                          <td style={{ padding: '0.75rem' }}>합계</td>
                          <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                            {trendData.reduce((s, r) => s + r.invoice_count, 0)}건
                          </td>
                          <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                            {formatFullCurrency(trendData.reduce((s, r) => s + r.total_amount, 0))}
                          </td>
                          <td style={{ padding: '0.75rem' }}></td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </Card>
            </div>
          )}

          {/* 항목별 월별 추이 */}
          {activeTab === 'category' && categoryData && (
            <div>
              <Card title="항목별 월별 청구금액 추이" style={{ marginBottom: '1.5rem' }}>
                {categoryData.data.length === 0 ? (
                  <p style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>데이터가 없습니다.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={450}>
                    <BarChart data={categoryData.data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                      <YAxis tickFormatter={(v: number) => formatCurrency(v)} tick={{ fontSize: 12 }} />
                      <Tooltip content={<CustomTooltipContent />} />
                      <Legend />
                      {categoryData.categories.map((cat) => (
                        <Bar
                          key={cat}
                          dataKey={cat}
                          name={cat}
                          stackId="a"
                          fill={CATEGORY_COLORS[cat] || '#9E9E9E'}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </Card>

              {/* 항목별 테이블 */}
              <Card title="항목별 월별 상세">
                {categoryData.data.length === 0 ? (
                  <p style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>데이터가 없습니다.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#f5f5f5' }}>
                          <th style={{ padding: '0.6rem', textAlign: 'left', borderBottom: '2px solid #ddd', position: 'sticky', left: 0, backgroundColor: '#f5f5f5', minWidth: 80 }}>월</th>
                          {categoryData.categories.map((cat) => (
                            <th key={cat} style={{ padding: '0.6rem', textAlign: 'right', borderBottom: '2px solid #ddd', minWidth: 100 }}>
                              <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, backgroundColor: CATEGORY_COLORS[cat] || '#9E9E9E', marginRight: 4, verticalAlign: 'middle' }} />
                              {cat}
                            </th>
                          ))}
                          <th style={{ padding: '0.6rem', textAlign: 'right', borderBottom: '2px solid #ddd', fontWeight: 'bold', minWidth: 110 }}>월 합계</th>
                        </tr>
                      </thead>
                      <tbody>
                        {categoryData.data.map((row) => {
                          const rowTotal = categoryData.categories.reduce((s, cat) => s + ((row[cat] as number) || 0), 0);
                          return (
                            <tr key={row.period as string}>
                              <td style={{ padding: '0.5rem 0.6rem', borderBottom: '1px solid #eee', fontWeight: 'bold', position: 'sticky', left: 0, backgroundColor: 'white' }}>
                                {row.period as string}
                              </td>
                              {categoryData.categories.map((cat) => (
                                <td key={cat} style={{ padding: '0.5rem 0.6rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                                  {(row[cat] as number) ? formatFullCurrency(row[cat] as number) : '-'}
                                </td>
                              ))}
                              <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>
                                {formatFullCurrency(rowTotal)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                      <tfoot>
                        <tr style={{ backgroundColor: '#f5f5f5', fontWeight: 'bold' }}>
                          <td style={{ padding: '0.6rem', position: 'sticky', left: 0, backgroundColor: '#f5f5f5' }}>합계</td>
                          {categoryData.categories.map((cat) => {
                            const catTotal = categoryData.data.reduce((s, row) => s + ((row[cat] as number) || 0), 0);
                            return (
                              <td key={cat} style={{ padding: '0.6rem', textAlign: 'right' }}>
                                {formatFullCurrency(catTotal)}
                              </td>
                            );
                          })}
                          <td style={{ padding: '0.6rem', textAlign: 'right' }}>
                            {formatFullCurrency(
                              categoryData.data.reduce((total, row) =>
                                total + categoryData.categories.reduce((s, cat) => s + ((row[cat] as number) || 0), 0), 0
                              )
                            )}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </Card>
            </div>
          )}

          {/* 거래처별 월별 추이 */}
          {activeTab === 'vendor' && vendorData && (
            <div>
              <Card title="거래처별 월별 청구금액 추이" style={{ marginBottom: '1.5rem' }}>
                {vendorData.data.length === 0 ? (
                  <p style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>데이터가 없습니다.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={450}>
                    <LineChart data={vendorData.data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                      <YAxis tickFormatter={(v: number) => formatCurrency(v)} tick={{ fontSize: 12 }} />
                      <Tooltip content={<CustomTooltipContent />} />
                      <Legend />
                      {vendorData.vendors.slice(0, 10).map((vendor, idx) => (
                        <Line
                          key={vendor}
                          type="monotone"
                          dataKey={vendor}
                          name={vendor}
                          stroke={VENDOR_COLORS[idx % VENDOR_COLORS.length]}
                          strokeWidth={2}
                          dot={{ r: 3 }}
                          connectNulls
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </Card>

              {/* 거래처별 테이블 */}
              <Card title="거래처별 월별 상세">
                {vendorData.data.length === 0 ? (
                  <p style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>데이터가 없습니다.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#f5f5f5' }}>
                          <th style={{ padding: '0.6rem', textAlign: 'left', borderBottom: '2px solid #ddd', position: 'sticky', left: 0, backgroundColor: '#f5f5f5', minWidth: 80 }}>월</th>
                          {vendorData.vendors.map((v, idx) => (
                            <th key={v} style={{ padding: '0.6rem', textAlign: 'right', borderBottom: '2px solid #ddd', minWidth: 110 }}>
                              <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', backgroundColor: VENDOR_COLORS[idx % VENDOR_COLORS.length], marginRight: 4, verticalAlign: 'middle' }} />
                              {v}
                            </th>
                          ))}
                          <th style={{ padding: '0.6rem', textAlign: 'right', borderBottom: '2px solid #ddd', fontWeight: 'bold', minWidth: 110 }}>월 합계</th>
                        </tr>
                      </thead>
                      <tbody>
                        {vendorData.data.map((row) => {
                          const rowTotal = vendorData.vendors.reduce((s, v) => s + ((row[v] as number) || 0), 0);
                          return (
                            <tr key={row.period as string}>
                              <td style={{ padding: '0.5rem 0.6rem', borderBottom: '1px solid #eee', fontWeight: 'bold', position: 'sticky', left: 0, backgroundColor: 'white' }}>
                                {row.period as string}
                              </td>
                              {vendorData.vendors.map((v) => (
                                <td key={v} style={{ padding: '0.5rem 0.6rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                                  {(row[v] as number) ? formatFullCurrency(row[v] as number) : '-'}
                                </td>
                              ))}
                              <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>
                                {formatFullCurrency(rowTotal)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                      <tfoot>
                        <tr style={{ backgroundColor: '#f5f5f5', fontWeight: 'bold' }}>
                          <td style={{ padding: '0.6rem', position: 'sticky', left: 0, backgroundColor: '#f5f5f5' }}>합계</td>
                          {vendorData.vendors.map((v) => {
                            const vTotal = vendorData.data.reduce((s, row) => s + ((row[v] as number) || 0), 0);
                            return (
                              <td key={v} style={{ padding: '0.6rem', textAlign: 'right' }}>
                                {formatFullCurrency(vTotal)}
                              </td>
                            );
                          })}
                          <td style={{ padding: '0.6rem', textAlign: 'right' }}>
                            {formatFullCurrency(
                              vendorData.data.reduce((total, row) =>
                                total + vendorData.vendors.reduce((s, v) => s + ((row[v] as number) || 0), 0), 0
                              )
                            )}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
