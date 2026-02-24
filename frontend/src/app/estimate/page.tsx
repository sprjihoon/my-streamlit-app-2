'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { calculateEstimate, exportEstimatePdf, getChargeableItems, type EstimateItem } from '@/lib/api';

const ZONE_LABELS = ['극소', '소', '중', '대', '특대', '특특대'];

function formatNumber(n: number): string {
  return n.toLocaleString('ko-KR');
}

export default function EstimatePage() {
  // 수신처 (PDF/저장 시 견적서에 반영)
  const [companyName, setCompanyName] = useState('');
  const [contact, setContact] = useState('');
  const [email, setEmail] = useState('');

  // 견적 조건
  const [monthlyOutbound, setMonthlyOutbound] = useState(1000);
  const [rateType, setRateType] = useState<'표준' | 'A'>('표준');
  const [zoneRatios, setZoneRatios] = useState<Record<string, number>>({
    극소: 30, 소: 40, 중: 20, 대: 7, 특대: 2, 특특대: 1,
  });
  const [returnPercentage, setReturnPercentage] = useState(0);
  const [inboundQty, setInboundQty] = useState<number | ''>('');
  const [combinedPercentage, setCombinedPercentage] = useState(0);
  const [brandType, setBrandType] = useState<'fashion' | 'beauty' | 'etc'>('etc');
  const [needQualityWork, setNeedQualityWork] = useState(false);
  const [ppBagProvider, setPpBagProvider] = useState<'brand' | 'ours'>('brand');
  const [mailerProvider, setMailerProvider] = useState<'brand' | 'ours'>('brand');
  const [needTexWork, setNeedTexWork] = useState(false);
  // 화장품/기타: 박스 입고 vs 개당 입고
  const [inboundType, setInboundType] = useState<'box' | 'piece'>('piece');

  // 청구서 항목 목록 (추가 작업 선택용)
  const [chargeableItems, setChargeableItems] = useState<Array<{ item_name: string; unit_price: number; source: string }>>([]);
  const [extraWorkEntries, setExtraWorkEntries] = useState<Array<{ item_name: string; qty: number }>>([]);

  // 작업일지 (의류 등)
  const [workLogEntries, setWorkLogEntries] = useState<Array<{ 분류: string; 수량: number; 단가: number }>>([
    { 분류: '의류', 수량: 0, 단가: 0 },
  ]);

  useEffect(() => {
    getChargeableItems()
      .then((res) => setChargeableItems(res.items || []))
      .catch(() => setChargeableItems([]));
  }, []);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [result, setResult] = useState<{
    items: EstimateItem[];
    total_amount: number;
    company_name: string;
    contact: string;
    email: string;
  } | null>(null);

  function zoneRatiosToDecimal(): Record<string, number> {
    const sum = Object.values(zoneRatios).reduce((a, b) => a + (Number(b) || 0), 0);
    if (sum <= 0) return { 극소: 1 };
    const out: Record<string, number> = {};
    ZONE_LABELS.forEach((label) => {
      const v = Number(zoneRatios[label]) || 0;
      out[label] = v / sum;
    });
    return out;
  }

  async function handleCalculate() {
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const data = await calculateEstimate({
        company_name: companyName,
        contact,
        email,
        monthly_outbound: monthlyOutbound,
        rate_type: rateType,
        zone_ratios: zoneRatiosToDecimal(),
        return_percentage: returnPercentage,
        inbound_qty: inboundQty === '' ? undefined : Number(inboundQty),
        combined_percentage: combinedPercentage,
        brand_type: brandType,
        need_quality_work: brandType === 'fashion' ? needQualityWork : false,
        pp_bag_provider: ppBagProvider,
        mailer_provider: mailerProvider,
        need_tex_work: needTexWork,
        inbound_type: (brandType === 'beauty' || brandType === 'etc') ? inboundType : undefined,
        extra_work_entries: extraWorkEntries.filter((e) => e.item_name.trim() && e.qty > 0),
        work_log_entries: workLogEntries.filter((e) => e.분류.trim() && (e.수량 > 0 || e.단가 > 0)),
      });
      setResult({
        items: data.items,
        total_amount: data.total_amount,
        company_name: data.company_name,
        contact: data.contact,
        email: data.email,
      });
      setSuccess('견적이 계산되었습니다.');
    } catch (err) {
      setError(err instanceof Error ? err.message : '견적 계산 실패');
    } finally {
      setLoading(false);
    }
  }

  async function handleExportPdf(doDownload: boolean) {
    if (!result || result.items.length === 0) {
      setError('먼저 견적을 계산해 주세요.');
      return;
    }
    setError(null);
    try {
      const blob = await exportEstimatePdf({
        company_name: result.company_name || companyName,
        contact: result.contact || contact,
        email: result.email || email,
        items: result.items,
        total_amount: result.total_amount,
      });
      const url = URL.createObjectURL(blob);
      if (doDownload) {
        const a = document.createElement('a');
        a.href = url;
        const name = (result.company_name || companyName || '견적서').replace(/[/\\?%*:|"]/g, '_');
        a.download = `견적서_${name}_${new Date().toISOString().slice(0, 10)}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        setSuccess('견적서가 저장되었습니다.');
      } else {
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        setSuccess('견적서 PDF를 열었습니다.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF 출력 실패');
    }
  }

  function addWorkLogRow() {
    setWorkLogEntries((prev) => [...prev, { 분류: '', 수량: 0, 단가: 0 }]);
  }
  function removeWorkLogRow(i: number) {
    setWorkLogEntries((prev) => prev.filter((_, idx) => idx !== i));
  }

  return (
    <div className="container" style={{ maxWidth: 900, margin: '0 auto', padding: '1rem' }}>
      <h1 style={{ marginBottom: '1rem' }}>📋 가견적</h1>
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      <Card title="📌 수신처 정보 (PDF·저장 시 견적서에 반영)" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>업체명</label>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="업체명"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>연락처</label>
            <input
              type="text"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              placeholder="연락처"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>이메일</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="이메일"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
        </div>
      </Card>

      <Card title="📊 견적 조건" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>월 출고건수</label>
            <input
              type="number"
              min={0}
              value={monthlyOutbound}
              onChange={(e) => setMonthlyOutbound(Number(e.target.value) || 0)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>택배 요금제</label>
            <select
              value={rateType}
              onChange={(e) => setRateType(e.target.value as '표준' | 'A')}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            >
              <option value="표준">표준</option>
              <option value="A">A</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>반품 비율 (%)</label>
            <input
              type="number"
              min={0}
              max={100}
              value={returnPercentage}
              onChange={(e) => setReturnPercentage(Number(e.target.value) || 0)}
              placeholder="0"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
            <span style={{ fontSize: '0.75rem', color: '#666' }}>전체 출고건 대비 %</span>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>입고수량 (선택)</label>
            <input
              type="number"
              min={0}
              value={inboundQty}
              onChange={(e) => setInboundQty(e.target.value === '' ? '' : Number(e.target.value))}
              placeholder="0"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>합포장 비율 (%)</label>
            <input
              type="number"
              min={0}
              max={100}
              value={combinedPercentage}
              onChange={(e) => setCombinedPercentage(Number(e.target.value) || 0)}
              placeholder="0"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
            <span style={{ fontSize: '0.75rem', color: '#666' }}>출고건 대비 %</span>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>브랜드유형</label>
            <select
              value={brandType}
              onChange={(e) => setBrandType(e.target.value as 'fashion' | 'beauty' | 'etc')}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            >
              <option value="fashion">패션</option>
              <option value="beauty">뷰티</option>
              <option value="etc">기타</option>
            </select>
          </div>
        </div>
        {(brandType === 'beauty' || brandType === 'etc') && (
          <div style={{ marginTop: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>입고 방식</label>
            <select
              value={inboundType}
              onChange={(e) => setInboundType(e.target.value as 'box' | 'piece')}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4, minWidth: 160 }}
            >
              <option value="piece">개당 입고</option>
              <option value="box">박스 입고</option>
            </select>
          </div>
        )}
        {brandType === 'fashion' && (
          <div style={{ marginTop: '1rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={needQualityWork}
                onChange={(e) => setNeedQualityWork(e.target.checked)}
              />
              <span>양품화 작업 필요 (입고수량 × 500원)</span>
            </label>
          </div>
        )}
        <div style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>PP 봉투</label>
            <select
              value={ppBagProvider}
              onChange={(e) => setPpBagProvider(e.target.value as 'brand' | 'ours')}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            >
              <option value="brand">브랜드 제공</option>
              <option value="ours">우리 쪽 사용</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>택배 봉투</label>
            <select
              value={mailerProvider}
              onChange={(e) => setMailerProvider(e.target.value as 'brand' | 'ours')}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            >
              <option value="brand">브랜드 제공</option>
              <option value="ours">우리 쪽 사용</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', marginTop: '1.75rem' }}>
              <input
                type="checkbox"
                checked={needTexWork}
                onChange={(e) => setNeedTexWork(e.target.checked)}
              />
              <span>텍작업 필요 (150원/건)</span>
            </label>
          </div>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>택배 구간별 비율 (%)</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {ZONE_LABELS.map((label) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <span style={{ fontSize: '0.875rem' }}>{label}</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  style={{ width: 52, padding: '0.35rem', border: '1px solid #ddd', borderRadius: 4 }}
                  value={zoneRatios[label] ?? 0}
                  onChange={(e) => setZoneRatios((prev) => ({ ...prev, [label]: Number(e.target.value) || 0 }))}
                />
                <span style={{ fontSize: '0.875rem' }}>%</span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <Card title="➕ 추가 작업 (청구서 항목 중 선택, 단가 자동 반영)" style={{ marginBottom: '1rem' }}>
        <p style={{ fontSize: '0.875rem', color: '#666', marginBottom: '0.75rem' }}>
          아래 목록은 요금표 관리에 등록된 항목입니다. 항목 선택 후 수량만 입력하면 단가가 자동 적용됩니다.
        </p>
        {extraWorkEntries.map((row, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
            <select
              value={row.item_name}
              onChange={(e) => {
                const next = [...extraWorkEntries];
                next[i] = { ...next[i], item_name: e.target.value };
                setExtraWorkEntries(next);
              }}
              style={{ minWidth: 180, padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            >
              <option value="">항목 선택</option>
              {chargeableItems.map((c) => (
                <option key={c.item_name} value={c.item_name}>
                  {c.item_name} (₩{formatNumber(c.unit_price)}/단위)
                </option>
              ))}
            </select>
            <input
              type="number"
              min={0}
              placeholder="수량"
              value={row.qty || ''}
              onChange={(e) => {
                const next = [...extraWorkEntries];
                next[i] = { ...next[i], qty: Number(e.target.value) || 0 };
                setExtraWorkEntries(next);
              }}
              style={{ width: 90, padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
            <button
              type="button"
              onClick={() => setExtraWorkEntries((prev) => prev.filter((_, idx) => idx !== i))}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4, background: '#f5f5f5', cursor: 'pointer' }}
            >
              삭제
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => setExtraWorkEntries((prev) => [...prev, { item_name: '', qty: 0 }])}
          style={{ padding: '0.5rem 1rem', border: '1px solid #ddd', borderRadius: 4, background: '#f5f5f5', cursor: 'pointer' }}
        >
          + 추가 작업 행
        </button>
      </Card>

      <Card title="📝 작업일지 (의류 등)" style={{ marginBottom: '1rem' }}>
        {workLogEntries.map((row, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
            <input
              type="text"
              placeholder="분류 (예: 의류)"
              value={row.분류}
              onChange={(e) => {
                const next = [...workLogEntries];
                next[i] = { ...next[i], 분류: e.target.value };
                setWorkLogEntries(next);
              }}
              style={{ width: 120, padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
            <input
              type="number"
              min={0}
              placeholder="수량"
              value={row.수량 || ''}
              onChange={(e) => {
                const next = [...workLogEntries];
                next[i] = { ...next[i], 수량: Number(e.target.value) || 0 };
                setWorkLogEntries(next);
              }}
              style={{ width: 80, padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
            <input
              type="number"
              min={0}
              placeholder="단가"
              value={row.단가 || ''}
              onChange={(e) => {
                const next = [...workLogEntries];
                next[i] = { ...next[i], 단가: Number(e.target.value) || 0 };
                setWorkLogEntries(next);
              }}
              style={{ width: 100, padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
            />
            <button
              type="button"
              onClick={() => removeWorkLogRow(i)}
              style={{ padding: '0.5rem', border: '1px solid #ddd', borderRadius: 4, background: '#f5f5f5', cursor: 'pointer' }}
            >
              삭제
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={addWorkLogRow}
          style={{ padding: '0.5rem 1rem', border: '1px solid #ddd', borderRadius: 4, background: '#f5f5f5', cursor: 'pointer' }}
        >
          + 행 추가
        </button>
      </Card>

      <div style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          onClick={handleCalculate}
          disabled={loading}
          style={{
            padding: '0.75rem 1.5rem',
            background: '#4CAF50',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          {loading ? '계산 중…' : '견적 계산'}
        </button>
      </div>

      {result && (
        <>
          <Card title="📄 견적 결과" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: 'green' }}>
                  ₩{formatNumber(result.total_amount)}
                </div>
                <div style={{ color: '#666', fontSize: '0.875rem' }}>총 금액</div>
              </div>
            </div>
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
                  <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '0.5rem' }}>{item.항목}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>{formatNumber(item.수량)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>₩{formatNumber(item.단가)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>₩{formatNumber(item.금액)}</td>
                    <td style={{ padding: '0.5rem', color: '#666' }}>{item.비고 || '-'}</td>
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
          </Card>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => handleExportPdf(false)}
              style={{
                padding: '0.75rem 1.25rem',
                background: '#2196F3',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              PDF로 출력하기
            </button>
            <button
              type="button"
              onClick={() => handleExportPdf(true)}
              style={{
                padding: '0.75rem 1.25rem',
                background: '#FF9800',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              저장하기
            </button>
          </div>
          <p style={{ marginTop: '0.75rem', color: '#666', fontSize: '0.875rem' }}>
            PDF로 출력하기·저장하기 시 위에 입력한 <strong>업체명, 연락처, 이메일</strong>이 견적서 수신란에 반영됩니다.
          </p>
        </>
      )}
    </div>
  );
}
