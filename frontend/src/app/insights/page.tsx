'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';
import {
  getInsightsSummary,
  getTopProducts,
  getTopVendorsByQty,
  getTopVendorsByRevenue,
  getMonthlyTrend,
  getOurRevenue,
  getInsightsVendorsList,
  searchInsightsData,
  InsightsSummary,
  TopProduct,
  TopVendorByQty,
  TopVendorByRevenue,
  MonthlyTrend,
  OurRevenue,
} from '@/lib/api';

type TabType = 'products' | 'vendors-qty' | 'vendors-revenue' | 'our-revenue' | 'trend' | 'search';

export default function InsightsPage() {
  const [activeTab, setActiveTab] = useState<TabType>('products');
  const [period, setPeriod] = useState<string>('');
  
  // 데이터
  const [summary, setSummary] = useState<InsightsSummary | null>(null);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [topVendorsByQty, setTopVendorsByQty] = useState<TopVendorByQty[]>([]);
  const [topVendorsByRevenue, setTopVendorsByRevenue] = useState<TopVendorByRevenue[]>([]);
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrend[]>([]);
  const [ourRevenue, setOurRevenue] = useState<OurRevenue | null>(null);
  
  // 검색
  const [searchVendor, setSearchVendor] = useState<string>('');
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [vendorsList, setVendorsList] = useState<string[]>([]);
  const [searchResults, setSearchResults] = useState<{
    count: number;
    total_qty: number;
    data: Record<string, unknown>[];
  } | null>(null);
  
  // UI 상태
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSummary();
  }, []);

  useEffect(() => {
    if (period !== undefined) {
      loadTabData();
    }
  }, [period, activeTab]);

  async function loadSummary() {
    try {
      setLoading(true);
      const data = await getInsightsSummary();
      setSummary(data);
      
      // 거래처 목록도 로드
      const vendors = await getInsightsVendorsList();
      setVendorsList(vendors);
      
      // 첫 번째 탭 데이터 로드
      await loadTabData();
    } catch (err) {
      setError(err instanceof Error ? err.message : '데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }

  async function loadTabData() {
    try {
      setLoading(true);
      const periodParam = period || undefined;
      
      switch (activeTab) {
        case 'products':
          setTopProducts(await getTopProducts(periodParam));
          break;
        case 'vendors-qty':
          setTopVendorsByQty(await getTopVendorsByQty(periodParam));
          break;
        case 'vendors-revenue':
          setTopVendorsByRevenue(await getTopVendorsByRevenue(periodParam));
          break;
        case 'our-revenue':
          setOurRevenue(await getOurRevenue(periodParam));
          break;
        case 'trend':
          setMonthlyTrend(await getMonthlyTrend());
          break;
        case 'search':
          // 검색 탭은 별도 처리
          break;
      }
    } catch (err) {
      console.error('Tab data load error:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch() {
    try {
      setLoading(true);
      const results = await searchInsightsData({
        vendor: searchVendor || undefined,
        keyword: searchKeyword || undefined,
        period: period || undefined,
        limit: 100,
      });
      setSearchResults(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : '검색 실패');
    } finally {
      setLoading(false);
    }
  }

  function formatNumber(num: number): string {
    return num.toLocaleString();
  }

  function formatCurrency(num: number): string {
    return `₩${num.toLocaleString()}`;
  }

  const tabs: { id: TabType; label: string }[] = [
    { id: 'products', label: '인기 상품' },
    { id: 'vendors-qty', label: '거래처별 출고량' },
    { id: 'vendors-revenue', label: '거래처별 매출' },
    { id: 'our-revenue', label: '우리 매출 분석' },
    { id: 'trend', label: '월별 트렌드' },
    { id: 'search', label: '상세 검색' },
  ];

  if (loading && !summary) {
    return <Loading />;
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>데이터 인사이트</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

      {/* 핵심 지표 */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.875rem', color: '#666' }}>총 주문 건수</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatNumber(summary.total_orders)}건</div>
            </div>
          </Card>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.875rem', color: '#666' }}>총 출고 수량</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatNumber(summary.total_qty)}개</div>
            </div>
          </Card>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.875rem', color: '#666' }}>거래처 수</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatNumber(summary.total_vendors)}개</div>
            </div>
          </Card>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.875rem', color: '#666' }}>총 정산액</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatCurrency(summary.total_amount)}</div>
            </div>
          </Card>
        </div>
      )}

      {/* 기간 필터 */}
      {summary && summary.periods.length > 0 && (
        <Card style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <label style={{ fontWeight: 500 }}>기간 필터:</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              style={{
                padding: '0.5rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
                minWidth: '150px',
              }}
            >
              <option value="">전체</option>
              {summary.periods.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </Card>
      )}

      {/* 탭 */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.5rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeTab === tab.id ? '#2196F3' : '#e0e0e0',
              color: activeTab === tab.id ? 'white' : '#333',
              cursor: 'pointer',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      {loading ? (
        <Loading />
      ) : (
        <>
          {/* 인기 상품 */}
          {activeTab === 'products' && (
            <Card title="인기 상품 TOP 20">
              {topProducts.length === 0 ? (
                <p>데이터가 없습니다.</p>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd', width: '60px' }}>순위</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>상품명</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>총판매수량</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topProducts.map((item) => (
                      <tr key={item.rank}>
                        <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{item.rank}</td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.product}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.quantity)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )}

          {/* 거래처별 출고량 */}
          {activeTab === 'vendors-qty' && (
            <Card title="거래처별 출고량 TOP 20">
              {topVendorsByQty.length === 0 ? (
                <p>데이터가 없습니다.</p>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd', width: '60px' }}>순위</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>총출고수량</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>주문건수</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>평균수량/건</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topVendorsByQty.map((item) => (
                      <tr key={item.rank}>
                        <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{item.rank}</td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.vendor}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.total_qty)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.order_count)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{item.avg_qty_per_order.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )}

          {/* 거래처별 매출 */}
          {activeTab === 'vendors-revenue' && (
            <Card title="거래처별 매출 TOP 20">
              {topVendorsByRevenue.length === 0 ? (
                <p>매출 데이터가 없습니다.</p>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd', width: '60px' }}>순위</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>총매출</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>주문건수</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>객단가</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topVendorsByRevenue.map((item) => (
                      <tr key={item.rank}>
                        <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{item.rank}</td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.vendor}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatCurrency(item.total_revenue)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.order_count)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatCurrency(item.avg_order_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )}

          {/* 우리 매출 분석 */}
          {activeTab === 'our-revenue' && ourRevenue && (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                <Card>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.875rem', color: '#666' }}>총 인보이스</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatNumber(ourRevenue.total_invoices)}건</div>
                  </div>
                </Card>
                <Card>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.875rem', color: '#666' }}>총 매출 (우리)</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatCurrency(ourRevenue.total_revenue)}</div>
                  </div>
                </Card>
                <Card>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.875rem', color: '#666' }}>총 주문 건수</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatNumber(ourRevenue.total_orders)}건</div>
                  </div>
                </Card>
                <Card>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.875rem', color: '#666' }}>전체 평균 객단가</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{formatCurrency(ourRevenue.avg_order_value)}</div>
                  </div>
                </Card>
              </div>

              <Card title="거래처별 매출 (인보이스 기반)">
                {ourRevenue.vendors.length === 0 ? (
                  <p>인보이스 데이터가 없습니다.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ backgroundColor: '#f5f5f5' }}>
                        <th style={{ padding: '0.75rem', textAlign: 'center', borderBottom: '2px solid #ddd', width: '60px' }}>순위</th>
                        <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>인보이스수</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>총매출</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>주문건수</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>객단가</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ourRevenue.vendors.map((item) => (
                        <tr key={item.rank}>
                          <td style={{ padding: '0.5rem', textAlign: 'center', borderBottom: '1px solid #eee' }}>{item.rank}</td>
                          <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.vendor_name || item.vendor}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.invoice_count)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatCurrency(item.total_revenue)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.total_orders)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatCurrency(item.avg_order_value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </div>
          )}

          {/* 월별 트렌드 */}
          {activeTab === 'trend' && (
            <Card title="월별 트렌드">
              {monthlyTrend.length === 0 ? (
                <p>데이터가 없습니다.</p>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>년월</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>총출고수량</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>주문건수</th>
                      <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>성장률</th>
                      {monthlyTrend[0]?.total_revenue !== undefined && (
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>총매출</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {monthlyTrend.map((item) => (
                      <tr key={item.period}>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.period}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.total_qty)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatNumber(item.order_count)}</td>
                        <td style={{ 
                          padding: '0.5rem', 
                          textAlign: 'right', 
                          borderBottom: '1px solid #eee',
                          color: item.qty_growth !== null ? (item.qty_growth > 0 ? 'green' : item.qty_growth < 0 ? 'red' : 'inherit') : 'inherit'
                        }}>
                          {item.qty_growth !== null ? `${item.qty_growth > 0 ? '+' : ''}${item.qty_growth.toFixed(1)}%` : '-'}
                        </td>
                        {item.total_revenue !== undefined && (
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>{formatCurrency(item.total_revenue)}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )}

          {/* 상세 검색 */}
          {activeTab === 'search' && (
            <Card title="상세 검색">
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                <select
                  value={searchVendor}
                  onChange={(e) => setSearchVendor(e.target.value)}
                  style={{
                    padding: '0.5rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    minWidth: '200px',
                  }}
                >
                  <option value="">전체 거래처</option>
                  {vendorsList.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
                <input
                  type="text"
                  placeholder="상품명 키워드"
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  style={{
                    padding: '0.5rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    minWidth: '200px',
                  }}
                />
                <button
                  onClick={handleSearch}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: '#2196F3',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  검색
                </button>
              </div>

              {searchResults && (
                <>
                  <div style={{ display: 'flex', gap: '2rem', marginBottom: '1rem' }}>
                    <div>검색 건수: <strong>{formatNumber(searchResults.count)}건</strong></div>
                    <div>총 수량: <strong>{formatNumber(searchResults.total_qty)}개</strong></div>
                  </div>

                  {searchResults.data.length > 0 ? (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ backgroundColor: '#f5f5f5' }}>
                            {Object.keys(searchResults.data[0]).map((key) => (
                              <th key={key} style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                                {key}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {searchResults.data.map((row, idx) => (
                            <tr key={idx}>
                              {Object.values(row).map((val, vidx) => (
                                <td key={vidx} style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                                  {String(val ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p>검색 결과가 없습니다.</p>
                  )}
                </>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}

