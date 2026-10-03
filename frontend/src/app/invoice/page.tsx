'use client';
import PageHeader from '@/components/ui/page-header';

import { useState, useEffect, useRef } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { KpiStrip } from '@/components/data';
import { calculateInvoice, getVendors, Vendor } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';

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
    <div>
      <PageHeader title="인보이스 계산" />

      {!isAdmin && (
        <Alert type="error" message="계산 권한이 없습니다. 관리자만 인보이스를 계산할 수 있습니다." onClose={() => {}} />
      )}
      
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}

      {/* 거래처 통계 */}
      <KpiStrip
        items={[
          { label: '전체 거래처', value: `${totalCount}개` },
          { label: '활성', value: <span className="tw-text-tillion-success">{activeCount}개</span> },
          { label: '비활성', value: `${inactiveCount}개` },
          { label: '선택됨', value: `${selectedVendors.length}개` },
        ]}
      />

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
        <div className="tw-mb-4">
          <label className="ops-label">월 빠른 선택</label>
          <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2">
            <Select
              value={selectedYear}
              onChange={(e) => {
                const year = parseInt(e.target.value);
                setSelectedYear(year);
              }}
              className="tw-max-w-[110px]"
            >
              {[...Array(5)].map((_, i) => {
                const year = new Date().getFullYear() - 2 + i;
                return <option key={year} value={year}>{year}년</option>;
              })}
            </Select>
            <div className="data-tabs tw-mb-0">
              {[...Array(12)].map((_, i) => {
                const month = i;
                const [fromYear, fromMonth] = dateFrom.split('-').map(Number);
                const [, toMonth] = dateTo.split('-').map(Number);
                const isSelected = selectedYear === fromYear &&
                  (fromMonth - 1) === month &&
                  (toMonth - 1) === month;
                return (
                  <Button
                    key={month}
                    type="button"
                    variant={isSelected ? 'primary' : 'secondary'}
                    onClick={() => {
                      const firstDay = new Date(selectedYear, month, 1);
                      const lastDay = new Date(selectedYear, month + 1, 0);
                      setDateFrom(formatLocalDate(firstDay));
                      setDateTo(formatLocalDate(lastDay));
                    }}
                  >
                    {month + 1}월
                  </Button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="data-form-grid">
          {mode === 'single' && (
            <Field label="공급처명">
              <Select
                value={singleVendor}
                onChange={(e) => setSingleVendor(e.target.value)}
              >
                <option value="">선택하세요</option>
                {vendors.map(v => (
                  <option key={v.vendor} value={v.vendor}>
                    {v.vendor} {v.active === 'YES' ? '활성' : '비활성'}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="시작일">
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </Field>
          <Field label="종료일">
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </Field>
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
          <div className="tw-mb-4 tw-flex tw-flex-wrap tw-items-end tw-gap-3 tw-rounded-lg tw-border tw-border-tillion-border tw-bg-tillion-page tw-p-3">
            <Field label="작업일지 소스" className="tw-mb-0">
              <Select
                value={worklogSource}
                onChange={(e) => setWorklogSource(e.target.value as 'all' | 'bot' | 'upload')}
              >
                <option value="all">전체 (봇 + 업로드)</option>
                <option value="bot">봇 작업일지만</option>
                <option value="upload">업로드 파일만</option>
              </Select>
            </Field>
            <p className="caption">
              {worklogSource === 'all' && '모든 작업일지 데이터를 사용합니다'}
              {worklogSource === 'bot' && '봇으로 입력된 작업일지만 사용합니다'}
              {worklogSource === 'upload' && '엑셀로 업로드된 작업일지만 사용합니다'}
            </p>
          </div>
        )}
      </Card>

      {/* 일괄 계산 모드 */}
      {mode === 'batch' && (
        <>
          {/* 필터 및 거래처 선택 */}
          <Card title="✅ 계산할 거래처 선택" style={{ marginBottom: '1rem' }}>
            <div className="tw-mb-4 tw-flex tw-flex-wrap tw-items-center tw-gap-3">
              <Select
                value={showMode}
                onChange={(e) => setShowMode(e.target.value as 'active' | 'inactive' | 'all')}
                className="tw-max-w-[140px]"
              >
                <option value="active">활성만</option>
                <option value="inactive">비활성만</option>
                <option value="all">전체</option>
              </Select>
              <Button type="button" variant="secondary" onClick={handleSelectAll}>
                {selectedVendors.length === filteredVendors.length ? '전체 해제' : '전체 선택'}
              </Button>
              <span className="caption">
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
          <div className="tw-mb-4">
            {!isBatchRunning ? (
              <Button
                type="button"
                variant="success"
                onClick={handleBatchCalculate}
                disabled={selectedVendors.length === 0}
              >
                인보이스 일괄 생성 시작 ({selectedVendors.length}개)
              </Button>
            ) : (
              <Button type="button" variant="danger" onClick={handleStopBatch}>
                계산 중지
              </Button>
            )}
          </div>

          {/* 진행 상황 */}
          {(isBatchRunning || batchLogs.length > 0) && (
            <Card title="📊 진행 상황">
              <div className="tw-mb-4 tw-h-5 tw-w-full tw-overflow-hidden tw-rounded-full tw-bg-tillion-border">
                <div className="tw-h-full tw-bg-tillion-success" style={{ width: `${batchProgress}%` }} />
              </div>
              <p className="caption tw-mb-3 tw-text-center">{batchProgress.toFixed(0)}% 완료</p>

              <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>거래처</th>
                      <th>결과</th>
                      <th className="cell-num">소요시간</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchLogs.map((log, idx) => (
                      <tr key={idx}>
                        <td>{log.vendor}</td>
                        <td>{log.message}</td>
                        <td className="cell-num">
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
          <Button
            type="button"
            variant="success"
            className="tw-mb-4"
            onClick={handleSingleCalculate}
            disabled={loading || !singleVendor}
          >
            {loading ? '계산 중...' : '인보이스 계산'}
          </Button>

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

              <Card title={`${result.vendor} 인보이스`} className="tw-mb-4">
                <KpiStrip
                  items={[
                    { label: '공급처', value: result.vendor },
                    { label: '시작일', value: result.date_from },
                    { label: '종료일', value: result.date_to },
                    { label: '총 금액', value: <span className="tw-text-tillion-success">₩{formatNumber(result.total_amount)}</span> },
                  ]}
                />
              </Card>

              <Card title="📝 상세 항목">
                {result.items.length === 0 ? (
                  <p style={{ color: '#666' }}>계산된 항목이 없습니다.</p>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>항목</th>
                        <th className="cell-num">수량</th>
                        <th className="cell-num">단가</th>
                        <th className="cell-num">금액</th>
                        <th>비고</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.items.map((item, i) => (
                        <tr key={i}>
                          <td>{item.항목}</td>
                          <td className="cell-num">{formatNumber(item.수량)}</td>
                          <td className="cell-num">₩{formatNumber(item.단가)}</td>
                          <td className="cell-num">₩{formatNumber(item.금액)}</td>
                          <td>{item.비고 || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td colSpan={3}>합계</td>
                        <td className="cell-num">₩{formatNumber(result.total_amount)}</td>
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
