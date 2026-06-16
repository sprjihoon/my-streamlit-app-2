'use client';

import { useState, useEffect, useRef } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { calculateInvoice, getVendors, Vendor } from '@/lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface InvoiceItem {
  항목: string;
  수량: number;
  단가: number;
  금액: number;
  비고?: string;
}

interface CalculateResult {
  success: boolean;
  vendor: string;
  date_from: string;
  date_to: string;
  items: InvoiceItem[];
  total_amount: number;
  warnings: string[];
}

interface BatchLog {
  vendor: string;
  status: 'success' | 'error' | 'pending' | 'processing';
  message: string;
  invoiceId?: number;
  duration?: number;
}

// 로컬 날짜를 YYYY-MM-DD 형식으로 변환 (시간대 문제 방지)
function formatLocalDate(date: Date): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * 인보이스 계산 페이지
 * 활성/비활성 거래처 필터 + 일괄 계산 기능
 */
export default function InvoicePage() {
  // 거래처 목록
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loadingVendors, setLoadingVendors] = useState(true);
  
  // 필터
  const [showMode, setShowMode] = useState<'active' | 'inactive' | 'all'>('active');
  const [selectedVendors, setSelectedVendors] = useState<string[]>([]);
  
  // 날짜
  const [selectedYear, setSelectedYear] = useState(() => new Date().getFullYear());
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return formatLocalDate(d);
  });
  const [dateTo, setDateTo] = useState(() => formatLocalDate(new Date()));
  
  // 옵션
  const [includeBasicShipping, setIncludeBasicShipping] = useState(true);
  const [includeCourierFee, setIncludeCourierFee] = useState(true);
  const [includeInboundFee, setIncludeInboundFee] = useState(true);
  const [includeRemoteFee, setIncludeRemoteFee] = useState(true);
  const [includeWorklog, setIncludeWorklog] = useState(true);
  const [includeCombinedFee, setIncludeCombinedFee] = useState(true);
  const [worklogSource, setWorklogSource] = useState<'all' | 'bot' | 'upload'>('all');
  
  // 계산 모드
  const [mode, setMode] = useState<'single' | 'batch'>('batch');
  const [singleVendor, setSingleVendor] = useState('');
  
  // 결과 상태
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CalculateResult | null>(null);
  const [batchLogs, setBatchLogs] = useState<BatchLog[]>([]);
  const [batchProgress, setBatchProgress] = useState(0);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  const stopRequestedRef = useRef(false);  // useRef로 최신 값 추적
  const [error, setError] = useState<string | null>(null);
  
  // 권한 체크
  const [isAdmin, setIsAdmin] = useState(false);
  
  useEffect(() => {
    const storedIsAdmin = localStorage.getItem('isAdmin') === 'true';
    setIsAdmin(storedIsAdmin);
  }, []);

  // 거래처 로드
  useEffect(() => {
    loadVendors();
  }, []);

  async function loadVendors() {
    try {
      setLoadingVendors(true);
      const data = await getVendors();
      setVendors(data);
      // 활성 거래처만 기본 선택
      const activeVendors = data.filter(v => v.active === 'YES').map(v => v.vendor);
      setSelectedVendors(activeVendors);
    } catch (err) {
      setError(err instanceof Error ? err.message : '거래처 로드 실패');
    } finally {
      setLoadingVendors(false);
    }
  }

  // 필터링된 거래처
  const filteredVendors = vendors.filter(v => {
    if (showMode === 'active') return v.active === 'YES';
    if (showMode === 'inactive') return v.active !== 'YES';
    return true;
  });

  // 통계
  const totalCount = vendors.length;
  const activeCount = vendors.filter(v => v.active === 'YES').length;
  const inactiveCount = vendors.filter(v => v.active !== 'YES').length;

  // 필터 변경 시 선택 업데이트
  useEffect(() => {
    const filtered = filteredVendors.map(v => v.vendor);
    setSelectedVendors(filtered);
  }, [showMode, vendors]);

  // 전체 선택/해제
  function handleSelectAll() {
    if (selectedVendors.length === filteredVendors.length) {
      setSelectedVendors([]);
    } else {
      setSelectedVendors(filteredVendors.map(v => v.vendor));
    }
  }

  // 개별 선택
  function handleToggleVendor(vendor: string) {
    if (selectedVendors.includes(vendor)) {
      setSelectedVendors(selectedVendors.filter(v => v !== vendor));
    } else {
      setSelectedVendors([...selectedVendors, vendor]);
    }
  }

  // 단일 인보이스 계산 (관리자만)
  async function handleSingleCalculate() {
    if (!isAdmin) {
      setError('계산 권한이 없습니다. 관리자만 인보이스를 계산할 수 있습니다.');
      return;
    }
    
    if (!singleVendor.trim()) {
      setError('공급처명을 입력하세요.');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const token = localStorage.getItem('token');
      const params = {
        vendor: singleVendor.trim(),
        date_from: dateFrom,
        date_to: dateTo,
        include_basic_shipping: includeBasicShipping,
        include_courier_fee: includeCourierFee,
        include_inbound_fee: includeInboundFee,
        include_remote_fee: includeRemoteFee,
        include_worklog: includeWorklog,
        include_combined_fee: includeCombinedFee,
        worklog_source: worklogSource,
      };
      
      const res = await fetch(`${API_URL}/calculate?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || '계산 실패');
      }
      
      const data = await res.json();

      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '계산 실패');
    } finally {
      setLoading(false);
    }
  }

  // 일괄 인보이스 계산 (관리자만)
  async function handleBatchCalculate() {
    if (!isAdmin) {
      setError('계산 권한이 없습니다. 관리자만 인보이스를 계산할 수 있습니다.');
      return;
    }
    
    if (selectedVendors.length === 0) {
      setError('선택된 거래처가 없습니다.');
      return;
    }

    setIsBatchRunning(true);
    setStopRequested(false);
    stopRequestedRef.current = false;  // ref도 초기화
    setBatchLogs([]);
    setBatchProgress(0);
    setError(null);

    const logs: BatchLog[] = selectedVendors.map(v => ({
      vendor: v,
      status: 'pending' as const,
      message: '대기 중...',
    }));
    setBatchLogs([...logs]);
    
    const token = localStorage.getItem('token');

    for (let i = 0; i < selectedVendors.length; i++) {
      if (stopRequestedRef.current) {
        logs[i] = {
          ...logs[i],
          status: 'error',
          message: '사용자 중지',
        };
        setBatchLogs([...logs]);
        break;
      }

      const vendor = selectedVendors[i];
      const startTime = Date.now();

      logs[i] = {
        ...logs[i],
        status: 'processing',
        message: '처리 중...',
      };
      setBatchLogs([...logs]);

      try {
        const params = {
          vendor,
          date_from: dateFrom,
          date_to: dateTo,
          include_basic_shipping: includeBasicShipping,
          include_courier_fee: includeCourierFee,
          include_inbound_fee: includeInboundFee,
          include_remote_fee: includeRemoteFee,
          include_worklog: includeWorklog,
          include_combined_fee: includeCombinedFee,
          worklog_source: worklogSource,
        };
        
        const res = await fetch(`${API_URL}/calculate?token=${token}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        });
        
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || '계산 실패');
        }
        
        const data = await res.json();

        const duration = (Date.now() - startTime) / 1000;
        logs[i] = {
          vendor,
          status: 'success',
          message: `완료 (${data.total_amount.toLocaleString()}원)`,
          duration,
        };
      } catch (err) {
        const duration = (Date.now() - startTime) / 1000;
        logs[i] = {
          vendor,
          status: 'error',
          message: `${err instanceof Error ? err.message : '실패'}`,
          duration,
        };
      }

      setBatchLogs([...logs]);
      setBatchProgress(((i + 1) / selectedVendors.length) * 100);
    }

    setIsBatchRunning(false);
  }

  function handleStopBatch() {
    setStopRequested(true);
    stopRequestedRef.current = true;  // ref 업데이트 (루프에서 즉시 감지)
  }

  const formatNumber = (n: number) => n.toLocaleString('ko-KR');

  if (loadingVendors) {
    return <Loading text="거래처 목록 로딩 중..." />;
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '1.5rem', fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>인보이스 계산</h1>

      {!isAdmin && (
        <Alert type="error" message="계산 권한이 없습니다. 관리자만 인보이스를 계산할 수 있습니다." onClose={() => {}} />
      )}
      
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

      {/* 거래처 통계 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
        <Card>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{totalCount}개</div>
            <div style={{ color: '#666' }}>전체 거래처</div>
          </div>
        </Card>
        <Card>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'green' }}>{activeCount}개</div>
            <div style={{ color: '#666' }}>🟢 활성</div>
          </div>
        </Card>
        <Card>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#999' }}>{inactiveCount}개</div>
            <div style={{ color: '#666' }}>⚪ 비활성</div>
          </div>
        </Card>
        <Card>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2196F3' }}>{selectedVendors.length}개</div>
            <div style={{ color: '#666' }}>선택됨</div>
          </div>
        </Card>
      </div>

      {/* 모드 선택 */}
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="radio"
              name="mode"
              checked={mode === 'batch'}
              onChange={() => setMode('batch')}
            />
            일괄 계산
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="radio"
              name="mode"
              checked={mode === 'single'}
              onChange={() => setMode('single')}
            />
            단일 거래처 계산
          </label>
        </div>
      </Card>

      {/* 계산 조건 */}
      <Card title="📅 계산 조건" style={{ marginBottom: '1rem' }}>
        {/* 월 빠른 선택 */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>📆 월 빠른 선택</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <select
              value={selectedYear}
              onChange={(e) => {
                const year = parseInt(e.target.value);
                setSelectedYear(year);
              }}
              style={{ 
                padding: '0.5rem', 
                border: '1px solid #ddd', 
                borderRadius: '4px',
                fontWeight: 500,
                minWidth: '90px'
              }}
            >
              {[...Array(5)].map((_, i) => {
                const year = new Date().getFullYear() - 2 + i;
                return <option key={year} value={year}>{year}년</option>;
              })}
            </select>
            <div style={{ 
              display: 'flex', 
              gap: '0.25rem', 
              flexWrap: 'wrap',
              flex: 1
            }}>
              {[...Array(12)].map((_, i) => {
                const month = i;
                // dateFrom에서 월과 일을 직접 파싱 (시간대 문제 방지)
                const [fromYear, fromMonth] = dateFrom.split('-').map(Number);
                const [, toMonth] = dateTo.split('-').map(Number);
                const isSelected = selectedYear === fromYear && 
                  (fromMonth - 1) === month && 
                  (toMonth - 1) === month;
                return (
                  <button
                    key={month}
                    onClick={() => {
                      const firstDay = new Date(selectedYear, month, 1);
                      const lastDay = new Date(selectedYear, month + 1, 0);
                      setDateFrom(formatLocalDate(firstDay));
                      setDateTo(formatLocalDate(lastDay));
                    }}
                    style={{
                      padding: '0.4rem 0.6rem',
                      border: isSelected ? '2px solid #4CAF50' : '1px solid #ddd',
                      borderRadius: '4px',
                      background: isSelected ? '#e8f5e9' : '#f9f9f9',
                      cursor: 'pointer',
                      fontWeight: isSelected ? 600 : 400,
                      color: isSelected ? '#2e7d32' : '#333',
                      transition: 'all 0.15s ease',
                      minWidth: '45px'
                    }}
                  >
                    {month + 1}월
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: mode === 'single' ? '1fr 1fr 1fr' : '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          {mode === 'single' && (
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>공급처명</label>
              <select
                value={singleVendor}
                onChange={(e) => setSingleVendor(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
              >
                <option value="">선택하세요</option>
                {vendors.map(v => (
                  <option key={v.vendor} value={v.vendor}>
                    {v.vendor} {v.active === 'YES' ? '🟢' : '⚪'}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>시작일</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>종료일</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
        </div>

        {/* 옵션 */}
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={includeBasicShipping} onChange={(e) => setIncludeBasicShipping(e.target.checked)} />
            기본 출고비
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={includeCourierFee} onChange={(e) => setIncludeCourierFee(e.target.checked)} />
            택배요금
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={includeInboundFee} onChange={(e) => setIncludeInboundFee(e.target.checked)} />
            입고검수
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={includeRemoteFee} onChange={(e) => setIncludeRemoteFee(e.target.checked)} />
            도서산간
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={includeWorklog} onChange={(e) => setIncludeWorklog(e.target.checked)} />
            작업일지
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={includeCombinedFee} onChange={(e) => setIncludeCombinedFee(e.target.checked)} />
            합포장
          </label>
        </div>

        {/* 작업일지 소스 선택 */}
        {includeWorklog && (
          <div style={{ 
            display: 'flex', 
            gap: '0.5rem', 
            alignItems: 'center', 
            marginBottom: '1rem',
            padding: '0.75rem',
            backgroundColor: '#f8f9fa',
            borderRadius: '8px',
            border: '1px solid #e9ecef'
          }}>
            <span style={{ fontWeight: 500, color: '#495057' }}>📋 작업일지 소스:</span>
            <select
              value={worklogSource}
              onChange={(e) => setWorklogSource(e.target.value as 'all' | 'bot' | 'upload')}
              style={{
                padding: '0.5rem 1rem',
                border: '1px solid #ced4da',
                borderRadius: '4px',
                backgroundColor: 'white',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">전체 (봇 + 업로드)</option>
              <option value="bot">봇 작업일지만</option>
              <option value="upload">업로드 파일만</option>
            </select>
            <span style={{ fontSize: '0.85rem', color: '#6c757d' }}>
              {worklogSource === 'all' && '모든 작업일지 데이터를 사용합니다'}
              {worklogSource === 'bot' && '봇으로 입력된 작업일지만 사용합니다'}
              {worklogSource === 'upload' && '엑셀로 업로드된 작업일지만 사용합니다'}
            </span>
          </div>
        )}
      </Card>

      {/* 일괄 계산 모드 */}
      {mode === 'batch' && (
        <>
          {/* 필터 및 거래처 선택 */}
          <Card title="✅ 계산할 거래처 선택" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
              <select
                value={showMode}
                onChange={(e) => setShowMode(e.target.value as 'active' | 'inactive' | 'all')}
                style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
              >
                <option value="active">활성만</option>
                <option value="inactive">비활성만</option>
                <option value="all">전체</option>
              </select>
              <button
                onClick={handleSelectAll}
                style={{
                  padding: '0.5rem 1rem',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  background: '#f5f5f5',
                  cursor: 'pointer',
                }}
              >
                {selectedVendors.length === filteredVendors.length ? '전체 해제' : '전체 선택'}
              </button>
              <span style={{ color: '#666' }}>
                {selectedVendors.length} / {filteredVendors.length} 선택됨
              </span>
            </div>

            <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid #eee', borderRadius: '4px', padding: '0.5rem' }}>
              {filteredVendors.map(v => (
                <label
                  key={v.vendor}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.5rem',
                    cursor: 'pointer',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedVendors.includes(v.vendor)}
                    onChange={() => handleToggleVendor(v.vendor)}
                  />
                  <span>{v.vendor}</span>
                  <span style={{ color: v.active === 'YES' ? 'green' : '#999', fontSize: '0.875rem' }}>
                    {v.active === 'YES' ? '🟢 활성' : '⚪ 비활성'}
                  </span>
                </label>
              ))}
            </div>
          </Card>

          {/* 일괄 계산 버튼 */}
          <div style={{ marginBottom: '1rem' }}>
            {!isBatchRunning ? (
              <button
                onClick={handleBatchCalculate}
                disabled={selectedVendors.length === 0}
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: selectedVendors.length === 0 ? '#ccc' : '#4CAF50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: selectedVendors.length === 0 ? 'not-allowed' : 'pointer',
                  fontSize: '1rem',
                }}
              >
                🚀 인보이스 일괄 생성 시작 ({selectedVendors.length}개)
              </button>
            ) : (
              <button
                onClick={handleStopBatch}
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: '#f44336',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '1rem',
                }}
              >
                ⏹️ 계산 중지
              </button>
            )}
          </div>

          {/* 진행 상황 */}
          {(isBatchRunning || batchLogs.length > 0) && (
            <Card title="📊 진행 상황">
              <div style={{ marginBottom: '1rem' }}>
                <div style={{
                  width: '100%',
                  height: '20px',
                  backgroundColor: '#e0e0e0',
                  borderRadius: '10px',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${batchProgress}%`,
                    height: '100%',
                    backgroundColor: '#4CAF50',
                    transition: 'width 0.3s',
                  }} />
                </div>
                <div style={{ textAlign: 'center', marginTop: '0.5rem' }}>
                  {batchProgress.toFixed(0)}% 완료
                </div>
              </div>

              <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f5f5f5' }}>
                      <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>거래처</th>
                      <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>결과</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>소요시간</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchLogs.map((log, idx) => (
                      <tr key={idx} style={{
                        backgroundColor: log.status === 'processing' ? '#fff3e0' :
                          log.status === 'success' ? '#e8f5e9' :
                            log.status === 'error' ? '#ffebee' : 'transparent'
                      }}>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{log.vendor}</td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{log.message}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee' }}>
                          {log.duration ? `${log.duration.toFixed(2)}s` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      {/* 단일 계산 모드 */}
      {mode === 'single' && (
        <>
          <button
            onClick={handleSingleCalculate}
            disabled={loading || !singleVendor}
            style={{
              padding: '0.75rem 2rem',
              backgroundColor: !singleVendor ? '#ccc' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: !singleVendor ? 'not-allowed' : 'pointer',
              fontSize: '1rem',
              marginBottom: '1rem',
            }}
          >
            {loading ? '계산 중...' : '🚀 인보이스 계산'}
          </button>

          {loading && <Loading text="인보이스 계산 중..." />}

          {result && (
            <>
              {result.warnings.length > 0 && (
                <Alert type="warning">
                  {result.warnings.map((w, i) => (
                    <div key={i}>{w}</div>
                  ))}
                </Alert>
              )}

              <Card title={`📋 ${result.vendor} 인보이스`} style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>{result.vendor}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>공급처</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>{result.date_from}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>시작일</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>{result.date_to}</div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>종료일</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: 'green' }}>
                      ₩{formatNumber(result.total_amount)}
                    </div>
                    <div style={{ color: '#666', fontSize: '0.875rem' }}>총 금액</div>
                  </div>
                </div>
              </Card>

              <Card title="📝 상세 항목">
                {result.items.length === 0 ? (
                  <p style={{ color: '#666' }}>계산된 항목이 없습니다.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ backgroundColor: '#f5f5f5' }}>
                        <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>항목</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>수량</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>단가</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>금액</th>
                        <th style={{ padding: '0.75rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>비고</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.items.map((item, i) => (
                        <tr key={i} style={{ backgroundColor: item.금액 < 0 ? '#fff5f5' : 'transparent' }}>
                          <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>{item.항목}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee', color: item.수량 < 0 ? '#dc2626' : 'inherit' }}>{formatNumber(item.수량)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee', color: item.단가 < 0 ? '#dc2626' : 'inherit' }}>₩{formatNumber(item.단가)}</td>
                          <td style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '1px solid #eee', color: item.금액 < 0 ? '#dc2626' : 'inherit', fontWeight: item.금액 < 0 ? 'bold' : 'normal' }}>₩{formatNumber(item.금액)}</td>
                          <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee', color: '#666' }}>{item.비고 || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr style={{ fontWeight: 'bold', backgroundColor: '#f5f5f5' }}>
                        <td colSpan={3} style={{ padding: '0.75rem' }}>합계</td>
                        <td style={{ padding: '0.75rem', textAlign: 'right' }}>₩{formatNumber(result.total_amount)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
