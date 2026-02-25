'use client';

import { useState } from 'react';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { calculateEstimate, exportEstimatePdf, type EstimateItem } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ZONE_LABELS = ['극소', '소', '중', '대'];
const BRAND_LABEL: Record<string, string> = { fashion: '패션', beauty: '뷰티', etc: '기타' };

function fmt(n: number) {
  return n.toLocaleString('ko-KR');
}

export default function EstimatePage() {
  const [companyName, setCompanyName] = useState('');
  const [contact, setContact] = useState('');
  const [email, setEmail] = useState('');

  const [monthlyOutbound, setMonthlyOutbound] = useState(1000);
  const rateType = '표준';
  const [zoneRatios, setZoneRatios] = useState<Record<string, number>>({
    극소: 70, 소: 20, 중: 7, 대: 3,
  });
  const [returnPercentage, setReturnPercentage] = useState(0);
  const [inboundQty, setInboundQty] = useState(0);
  const [combinedPercentage, setCombinedPercentage] = useState(0);
  const [combinedAvgQty, setCombinedAvgQty] = useState(0);
  const [brandType, setBrandType] = useState<'fashion' | 'beauty' | 'etc'>('fashion');
  const [needQualityWork, setNeedQualityWork] = useState(false);
  const [ppBagProvider, setPpBagProvider] = useState<'brand' | 'ours'>('brand');
  const [mailerProvider, setMailerProvider] = useState<'brand' | 'ours'>('brand');
  const [courierBoxProvider, setCourierBoxProvider] = useState<'brand' | 'ours'>('brand');
  const [needTexWork, setNeedTexWork] = useState(false);
  const [needBarcodeAttach, setNeedBarcodeAttach] = useState(false);
  const [needVoidWork, setNeedVoidWork] = useState(false);
  const [needVideoOut, setNeedVideoOut] = useState(false);
  const [needVideoRet, setNeedVideoRet] = useState(false);
  const [storagePlt, setStoragePlt] = useState(0);
  const [skuCount, setSkuCount] = useState(0);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
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
      out[label] = (Number(zoneRatios[label]) || 0) / sum;
    });
    return out;
  }

  function handleZoneRatioChange(changedLabel: string, newValue: number) {
    setZoneRatios((prev) => {
      const oldValue = prev[changedLabel] || 0;
      const clampedValue = Math.max(0, Math.min(100, Math.ceil(newValue)));
      const diff = clampedValue - oldValue; // 양수면 증가, 음수면 감소
      
      if (diff === 0) return prev;
      
      const updated = { ...prev, [changedLabel]: clampedValue };
      
      // 다른 구간들 중 값이 있는 것들만 (내림차순 정렬)
      const otherLabels = ZONE_LABELS
        .filter(l => l !== changedLabel)
        .sort((a, b) => (updated[b] || 0) - (updated[a] || 0));
      
      // 조정할 차이 (증가했으면 다른 곳에서 빼야 하고, 감소했으면 다른 곳에 더해야 함)
      let remaining = Math.abs(diff);
      
      for (const label of otherLabels) {
        if (remaining <= 0) break;
        
        const currentValue = updated[label] || 0;
        
        if (diff > 0) {
          // 현재 구간이 증가 → 다른 구간에서 빼기
          const deduction = Math.min(currentValue, remaining);
          updated[label] = currentValue - deduction;
          remaining -= deduction;
        } else {
          // 현재 구간이 감소 → 다른 구간에 더하기 (최대 100까지)
          const maxAdd = 100 - currentValue;
          const addition = Math.min(maxAdd, remaining);
          updated[label] = currentValue + addition;
          remaining -= addition;
        }
      }
      
      return updated;
    });
  }

  async function handleCalculate() {
    setError(null);
    setSuccess(null);

    // 필수 입력값 검증
    if (!companyName.trim()) {
      setError('업체명을 입력해 주세요.');
      return;
    }
    if (!email.trim()) {
      setError('이메일 주소를 입력해 주세요.');
      return;
    }
    // 이메일 형식 검증
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      setError('올바른 이메일 형식을 입력해 주세요.');
      return;
    }

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
        inbound_qty: Number(inboundQty) || 0,
        combined_percentage: combinedPercentage,
        combined_avg_qty: combinedAvgQty === '' ? undefined : Number(combinedAvgQty),
        brand_type: brandType,
        need_quality_work: brandType === 'fashion' ? needQualityWork : false,
        pp_bag_provider: ppBagProvider,
        mailer_provider: mailerProvider,
        courier_box_provider: courierBoxProvider,
        need_tex_work: needTexWork,
        need_barcode_attach: needBarcodeAttach,
        need_void_work: needVoidWork,
        need_video_out: needVideoOut,
        need_video_ret: needVideoRet,
        storage_plt: storagePlt === '' ? undefined : Number(storagePlt),
        sku_count: skuCount === '' ? undefined : Number(skuCount),
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

  async function handleSaveAndDownload() {
    if (!result || result.items.length === 0) {
      setError('먼저 견적을 계산해 주세요.');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await fetch(`${API_BASE}/estimate/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: result.company_name || companyName,
          contact: result.contact || contact,
          email: result.email || email,
          items: result.items,
          total_amount: result.total_amount,
          brand_type: brandType,
        }),
      });

      const blob = await exportEstimatePdf({
        company_name: result.company_name || companyName,
        contact: result.contact || contact,
        email: result.email || email,
        items: result.items,
        total_amount: result.total_amount,
        brand_type: brandType,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const name = (result.company_name || companyName || '견적서').replace(/[/\\?%*:|"]/g, '_');
      a.download = `견적서_${name}_${new Date().toISOString().slice(0, 10)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setSuccess('견적서가 저장 및 다운로드되었습니다.');
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장/PDF 출력 실패');
    } finally {
      setSaving(false);
    }
  }

  async function handlePreviewPdf() {
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
        brand_type: brandType,
      });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF 미리보기 실패');
    }
  }

  /* ─── 공통 스타일 (다크 테마) ─── */
  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.6rem 0.75rem', border: '1px solid #333',
    borderRadius: 8, fontSize: '0.9rem', transition: 'border-color .2s',
    outline: 'none', background: '#1a1a1a', color: '#e5e5e5',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: 4, fontWeight: 600, fontSize: '0.82rem', color: '#d1d5db',
  };
  const selectStyle: React.CSSProperties = { ...inputStyle, appearance: 'auto' as const };
  const sectionStyle: React.CSSProperties = {
    background: '#111', borderRadius: 12, padding: '1.25rem',
    boxShadow: '0 1px 3px rgba(0,0,0,.3)', marginBottom: '1rem',
    border: '1px solid #222',
  };
  const sectionTitle: React.CSSProperties = {
    fontSize: '1rem', fontWeight: 700, color: '#e5e5e5', marginBottom: '1rem',
    paddingBottom: 8, borderBottom: '2px solid #333',
  };
  const gridTwo: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem',
  };
  const chipLabel: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px',
    borderRadius: 20, border: '1px solid #333', cursor: 'pointer',
    fontSize: '0.82rem', background: '#1a1a1a', color: '#9ca3af', transition: 'all .15s',
  };
  const chipChecked: React.CSSProperties = {
    ...chipLabel, background: '#0d2a0d', borderColor: '#39ff14', color: '#39ff14',
  };
  const hint: React.CSSProperties = { fontSize: '0.72rem', color: '#6b7280', marginTop: 2 };

  const zoneTotal = Object.values(zoneRatios).reduce((a, b) => a + (Number(b) || 0), 0);

  return (
    <div className="estimate-dark" style={{ maxWidth: 640, margin: '0 auto', padding: '1rem', background: '#000', minHeight: '100vh' }}>
      {/* 히어로 헤더 */}
      <div style={{
        background: '#39ff14',
        borderRadius: 16, padding: '2rem 1.5rem', marginBottom: '1.25rem',
        color: '#000', textAlign: 'center',
      }}>
        <h1 style={{ fontSize: '1.35rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>
          스프링풀필먼트 견적확인하기
        </h1>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem', opacity: 0.75, color: '#000' }}>
          조건을 입력하면 실시간으로 물류 비용을 산출해 드립니다
        </p>
      </div>

      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      {/* 수신처 */}
      <div style={sectionStyle}>
        <div style={sectionTitle}>수신처 정보</div>
        <div style={gridTwo}>
          <div>
            <label style={labelStyle}>업체명 <span style={{ color: '#ef4444' }}>*</span></label>
            <input style={inputStyle} value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="업체명" />
          </div>
          <div>
            <label style={labelStyle}>연락처</label>
            <input style={inputStyle} value={contact} onChange={(e) => setContact(e.target.value)} placeholder="010-0000-0000" />
          </div>
        </div>
        <div style={{ marginTop: '0.75rem' }}>
          <label style={labelStyle}>이메일 <span style={{ color: '#ef4444' }}>*</span></label>
          <input style={inputStyle} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@example.com" />
        </div>
      </div>

      {/* 견적 조건 */}
      <div style={sectionStyle}>
        <div style={sectionTitle}>견적 조건</div>
        <div style={gridTwo}>
          <div>
            <label style={labelStyle}>택배 요금제</label>
            <div style={{ ...inputStyle, background: '#222', color: '#9ca3af' }}>표준(우체국택배)</div>
          </div>
          <div>
            <label style={labelStyle}>브랜드유형</label>
            <select style={selectStyle} value={brandType} onChange={(e) => setBrandType(e.target.value as 'fashion' | 'beauty' | 'etc')}>
              <option value="fashion">패션</option>
              <option value="beauty">뷰티</option>
              <option value="etc">기타</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>월 출고건수</label>
            <input style={inputStyle} type="number" min={0} step={1} value={monthlyOutbound || ''} onChange={(e) => setMonthlyOutbound(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} />
          </div>
          <div>
            <label style={labelStyle}>반품 비율 (%)</label>
            <input style={inputStyle} type="number" min={0} max={100} step={1} value={returnPercentage || ''} onChange={(e) => setReturnPercentage(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} placeholder="0" />
            <div style={hint}>전체 출고건 대비 %</div>
          </div>
          <div>
            <label style={labelStyle}>합포장 비율 (%)</label>
            <input style={inputStyle} type="number" min={0} max={100} step={1} value={combinedPercentage || ''} onChange={(e) => setCombinedPercentage(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} placeholder="0" />
            <div style={hint}>출고건 대비 %</div>
          </div>
          <div>
            <label style={labelStyle}>합포장 평균 수량</label>
            <input style={inputStyle} type="number" min={0} step={1} value={combinedAvgQty || ''} onChange={(e) => setCombinedAvgQty(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} placeholder="0" />
            <div style={hint}>건당 개수</div>
          </div>
          <div>
            <label style={labelStyle}>입고수량</label>
            <input style={inputStyle} type="number" min={0} step={1} value={inboundQty || ''} onChange={(e) => setInboundQty(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} placeholder="0" />
          </div>
          <div>
            <label style={labelStyle}>보관량 (PLT)</label>
            <input style={inputStyle} type="number" min={0} step={1} value={storagePlt || ''} onChange={(e) => setStoragePlt(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} placeholder="0" />
            <div style={hint}>PLT 기준</div>
          </div>
          <div>
            <label style={labelStyle}>SKU 수</label>
            <input style={inputStyle} type="number" min={0} step={1} value={skuCount || ''} onChange={(e) => setSkuCount(Math.ceil(Number(e.target.value)) || 0)} onKeyDown={(e) => { if (e.key === '.') e.preventDefault(); }} placeholder="0" />
            <div style={hint}>1 PLT당 SKU 2개 초과 → 중량랙</div>
          </div>
        </div>

        {/* 포장재 제공 방식 */}
        <div style={{ marginTop: '1rem' }}>
          <div style={{ ...labelStyle, marginBottom: 8 }}>포장재 제공 방식</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {brandType === 'fashion' && (
              <>
                <div style={{ minWidth: 160 }}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>PP 봉투</div>
                  <select style={{ ...selectStyle, fontSize: '0.82rem', padding: '0.45rem 0.6rem' }} value={ppBagProvider} onChange={(e) => setPpBagProvider(e.target.value as 'brand' | 'ours')}>
                    <option value="brand">브랜드 제공</option>
                    <option value="ours">풀필먼트 공용</option>
                  </select>
                </div>
                <div style={{ minWidth: 160 }}>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>택배 봉투</div>
                  <select style={{ ...selectStyle, fontSize: '0.82rem', padding: '0.45rem 0.6rem' }} value={mailerProvider} onChange={(e) => setMailerProvider(e.target.value as 'brand' | 'ours')}>
                    <option value="brand">브랜드 제공</option>
                    <option value="ours">풀필먼트 공용</option>
                  </select>
                </div>
              </>
            )}
            <div style={{ minWidth: 160 }}>
              <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: 4 }}>택배박스</div>
              <select style={{ ...selectStyle, fontSize: '0.82rem', padding: '0.45rem 0.6rem' }} value={courierBoxProvider} onChange={(e) => setCourierBoxProvider(e.target.value as 'brand' | 'ours')}>
                <option value="brand">브랜드 제공</option>
                <option value="ours">풀필먼트 공용</option>
              </select>
            </div>
          </div>
        </div>

        {/* 부가 작업 (칩 스타일) */}
        <div style={{ marginTop: '1rem' }}>
          <div style={{ ...labelStyle, marginBottom: 8 }}>부가 작업</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {brandType === 'fashion' && (
              <label style={needQualityWork ? chipChecked : chipLabel}>
                <input type="checkbox" checked={needQualityWork} onChange={(e) => setNeedQualityWork(e.target.checked)} style={{ display: 'none' }} />
                양품화
              </label>
            )}
            <label style={needTexWork ? chipChecked : chipLabel}>
              <input type="checkbox" checked={needTexWork} onChange={(e) => setNeedTexWork(e.target.checked)} style={{ display: 'none' }} />
              텍작업
            </label>
            <label style={needBarcodeAttach ? chipChecked : chipLabel}>
              <input type="checkbox" checked={needBarcodeAttach} onChange={(e) => setNeedBarcodeAttach(e.target.checked)} style={{ display: 'none' }} />
              바코드 부착
            </label>
            <label style={needVoidWork ? chipChecked : chipLabel}>
              <input type="checkbox" checked={needVoidWork} onChange={(e) => setNeedVoidWork(e.target.checked)} style={{ display: 'none' }} />
              완충작업
            </label>
            <label style={needVideoOut ? chipChecked : chipLabel}>
              <input type="checkbox" checked={needVideoOut} onChange={(e) => setNeedVideoOut(e.target.checked)} style={{ display: 'none' }} />
              출고영상촬영
            </label>
            <label style={needVideoRet ? chipChecked : chipLabel}>
              <input type="checkbox" checked={needVideoRet} onChange={(e) => setNeedVideoRet(e.target.checked)} style={{ display: 'none' }} />
              반품영상촬영
            </label>
          </div>
        </div>

        {/* 택배 구간별 비율 */}
        <div style={{ marginTop: '1rem' }}>
          <div style={{ ...labelStyle, marginBottom: 12 }}>
            택배 구간별 비율
            <span style={{ fontWeight: 400, fontSize: '0.72rem', color: zoneTotal === 100 ? '#39ff14' : '#ef4444', marginLeft: 8 }}>
              합계 {zoneTotal}%
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ZONE_LABELS.map((label) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: '0.82rem', fontWeight: 500, minWidth: 32, color: '#d1d5db' }}>{label}</span>
                <input
                  type="range" min={0} max={100} step={1}
                  value={zoneRatios[label] || 0}
                  onChange={(e) => handleZoneRatioChange(label, Number(e.target.value))}
                  style={{
                    flex: 1,
                    height: 6,
                    borderRadius: 3,
                    background: `linear-gradient(to right, #39ff14 0%, #39ff14 ${zoneRatios[label] || 0}%, #333 ${zoneRatios[label] || 0}%, #333 100%)`,
                    appearance: 'none',
                    cursor: 'pointer',
                  }}
                />
                <span style={{ fontSize: '0.85rem', fontWeight: 600, minWidth: 40, textAlign: 'right', color: '#39ff14' }}>
                  {zoneRatios[label] || 0}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 필수 입력 에러 메시지 */}
      {error && (
        <div style={{
          padding: '0.75rem 1rem', marginBottom: '0.75rem', borderRadius: 8,
          background: '#2d1f1f', border: '1px solid #ef4444', color: '#fca5a5',
          fontSize: '0.85rem', textAlign: 'center',
        }}>
          {error}
        </div>
      )}

      {/* 견적 계산 버튼 */}
      <button
        onClick={handleCalculate}
        disabled={loading}
        style={{
          width: '100%', padding: '0.85rem', border: 'none', borderRadius: 10,
          background: loading ? '#a3e635' : '#39ff14',
          color: '#000', fontSize: '1rem', fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
          boxShadow: '0 2px 8px rgba(57,255,20,.35)', transition: 'all .2s', marginBottom: '1rem',
        }}
      >
        {loading ? <Loading /> : '견적 계산하기'}
      </button>

      {/* 결과 */}
      {result && (
        <>
          <div style={{ ...sectionStyle, border: '2px solid #39ff14' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={sectionTitle}>견적 결과</div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#39ff14' }}>₩{fmt(result.total_amount)}</div>
                <div style={{ fontSize: '0.72rem', color: '#6b7280' }}>월 예상 비용 (VAT 별도)</div>
              </div>
            </div>

            <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', color: '#e5e5e5' }}>
                <thead>
                  <tr style={{ background: '#0d2a0d' }}>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #39ff14', color: '#39ff14' }}>항목</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #39ff14', color: '#39ff14' }}>수량</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #39ff14', color: '#39ff14' }}>단가</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontWeight: 600, borderBottom: '2px solid #39ff14', color: '#39ff14' }}>금액</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((item, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #222' }}>
                      <td style={{ padding: '0.5rem' }}>
                        {item.항목}
                        {item.비고 && <div style={{ fontSize: '0.7rem', color: '#6b7280' }}>{item.비고}</div>}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>{fmt(item.수량)}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>₩{fmt(item.단가)}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>₩{fmt(item.금액)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: '#0d2a0d' }}>
                    <td colSpan={3} style={{ padding: '0.6rem 0.5rem', fontWeight: 700, color: '#e5e5e5' }}>합계</td>
                    <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontWeight: 700, color: '#39ff14' }}>₩{fmt(result.total_amount)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* 하단 액션 버튼 */}
          <div style={{ marginBottom: '0.75rem' }}>
            <button
              onClick={handleSaveAndDownload}
              disabled={saving}
              style={{
                width: '100%', padding: '0.75rem', border: 'none', borderRadius: 10,
                background: saving ? '#a3e635' : '#22c55e',
                color: '#000', fontSize: '0.9rem', fontWeight: 600,
                cursor: saving ? 'not-allowed' : 'pointer',
                boxShadow: '0 2px 8px rgba(34,197,94,.3)',
              }}
            >
              {saving ? '저장 중…' : '저장 및 다운로드'}
            </button>
          </div>
          {/* 표준요금표 다운로드 */}
          <div style={{ marginBottom: '1.5rem' }}>
            <a
              href="/표준가격표.pdf"
              download="스프링풀필먼트_표준가격표.pdf"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                width: '100%', padding: '0.65rem', border: '1px solid #39ff14', borderRadius: 10,
                background: '#111', color: '#39ff14', fontSize: '0.85rem', fontWeight: 500,
                textDecoration: 'none', cursor: 'pointer', transition: 'all .15s',
              }}
            >
              📋 표준요금표 다운로드
            </a>
          </div>
        </>
      )}
    </div>
  );
}
