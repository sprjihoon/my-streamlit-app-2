'use client';

import { useState, useEffect, useRef } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── 타입 ───────────────────────────────────────────────────────────
interface CertInfo {
  user: {
    user_id: number;
    nickname: string;
    department: string;
    position: string;
    join_date: string;
  };
  company: {
    company_name: string;
    business_number: string;
    address: string;
    representative: string;
  };
  issued_date: string;
  duration: string;
}

// ─── 날짜 포맷 (2026년 06월 15일) ────────────────────────────────────
function fmtKo(dateStr: string) {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-');
  return `${y}년 ${m}월 ${d}일`;
}

// ─── 인쇄 스타일 (전역 주입) ─────────────────────────────────────────
const PRINT_STYLE = `
@media print {
  body * { visibility: hidden !important; }
  #cert-print-area, #cert-print-area * { visibility: visible !important; }
  #cert-print-area {
    position: fixed !important;
    top: 0 !important; left: 0 !important;
    width: 210mm !important; min-height: 297mm !important;
    margin: 0 !important; padding: 20mm 25mm !important;
    box-shadow: none !important;
    background: white !important;
    font-family: 'Malgun Gothic', '맑은 고딕', AppleGothic, sans-serif !important;
  }
  @page { size: A4 portrait; margin: 0; }
}
`;

// ─── 재직증명서 컴포넌트 ─────────────────────────────────────────────
function EmploymentCert({ info, purpose }: { info: CertInfo; purpose: string }) {
  const { user, company, issued_date } = info;
  return (
    <div id="cert-print-area" style={certWrap}>
      <div style={certTitle}>재 직 증 명 서</div>
      <div style={certSubtitle}>CERTIFICATE OF EMPLOYMENT</div>

      <table style={infoTable}>
        <tbody>
          {[
            { label: '성    명', value: user.nickname },
            { label: '소    속', value: user.department || '—' },
            { label: '직    위', value: user.position || '—' },
            { label: '입 사 일', value: fmtKo(user.join_date) || '—' },
            { label: '재직기간', value: user.join_date ? `${fmtKo(user.join_date)} ~ 현재 (${info.duration})` : '—' },
          ].map(({ label, value }) => (
            <tr key={label}>
              <td style={tdLabel}>{label}</td>
              <td style={tdValue}>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={bodyText}>
        위 사람은 당사에 재직 중임을 증명합니다.
      </div>
      {purpose && (
        <div style={{ ...bodyText, fontSize: '0.9rem', color: '#555', marginTop: '0.5rem' }}>
          발급 목적: {purpose}
        </div>
      )}

      <div style={dateText}>{fmtKo(issued_date)}</div>

      <div style={companyBlock}>
        <div style={companyName}>{company.company_name}</div>
        {company.address && <div style={companyDetail}>{company.address}</div>}
        {company.business_number && <div style={companyDetail}>사업자등록번호: {company.business_number}</div>}
        <div style={{ ...companyDetail, marginTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2rem' }}>
          <span>대표이사: {company.representative || '—'}</span>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/seal.png" alt="직인" style={sealImg} />
        </div>
      </div>
    </div>
  );
}

// ─── 경력증명서 컴포넌트 ─────────────────────────────────────────────
function CareerCert({ info, purpose }: { info: CertInfo; purpose: string }) {
  const { user, company, issued_date } = info;
  return (
    <div id="cert-print-area" style={certWrap}>
      <div style={certTitle}>경 력 증 명 서</div>
      <div style={certSubtitle}>CERTIFICATE OF CAREER</div>

      <table style={infoTable}>
        <tbody>
          {[
            { label: '성    명', value: user.nickname },
            { label: '소    속', value: user.department || '—' },
            { label: '직    위', value: user.position || '—' },
            { label: '입 사 일', value: fmtKo(user.join_date) || '—' },
          ].map(({ label, value }) => (
            <tr key={label}>
              <td style={tdLabel}>{label}</td>
              <td style={tdValue}>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 경력 상세 테이블 */}
      <table style={{ ...infoTable, marginTop: '2rem' }}>
        <thead>
          <tr>
            <th style={{ ...tdLabel, textAlign: 'center', background: '#1a3c6e', color: 'white', padding: '0.6rem' }}>근무기간</th>
            <th style={{ ...tdLabel, textAlign: 'center', background: '#1a3c6e', color: 'white', padding: '0.6rem' }}>소속부서</th>
            <th style={{ ...tdLabel, textAlign: 'center', background: '#1a3c6e', color: 'white', padding: '0.6rem' }}>직위</th>
            <th style={{ ...tdLabel, textAlign: 'center', background: '#1a3c6e', color: 'white', padding: '0.6rem' }}>비고</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={{ ...tdValue, textAlign: 'center' }}>
              {user.join_date ? `${fmtKo(user.join_date)} ~ 현재` : '—'}
            </td>
            <td style={{ ...tdValue, textAlign: 'center' }}>{user.department || '—'}</td>
            <td style={{ ...tdValue, textAlign: 'center' }}>{user.position || '—'}</td>
            <td style={{ ...tdValue, textAlign: 'center' }}>재직중</td>
          </tr>
        </tbody>
      </table>

      <div style={bodyText}>
        위 사람은 당사에서 위와 같이 근무하였음을 증명합니다.
      </div>
      {purpose && (
        <div style={{ ...bodyText, fontSize: '0.9rem', color: '#555', marginTop: '0.5rem' }}>
          발급 목적: {purpose}
        </div>
      )}

      <div style={dateText}>{fmtKo(issued_date)}</div>

      <div style={companyBlock}>
        <div style={companyName}>{company.company_name}</div>
        {company.address && <div style={companyDetail}>{company.address}</div>}
        {company.business_number && <div style={companyDetail}>사업자등록번호: {company.business_number}</div>}
        <div style={{ ...companyDetail, marginTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2rem' }}>
          <span>대표이사: {company.representative || '—'}</span>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/seal.png" alt="직인" style={sealImg} />
        </div>
      </div>
    </div>
  );
}

// ─── 메인 페이지 ─────────────────────────────────────────────────────
export default function CertificatesPage() {
  const [token, setToken] = useState('');
  const [info, setInfo] = useState<CertInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [certType, setCertType] = useState<'employment' | 'career'>('employment');
  const [purpose, setPurpose] = useState('');
  const [printing, setPrinting] = useState(false);
  const styleRef = useRef<HTMLStyleElement | null>(null);

  useEffect(() => {
    const tok = localStorage.getItem('token') || '';
    setToken(tok);
    if (!tok) { setError('로그인이 필요합니다.'); setLoading(false); return; }

    // 인쇄 스타일 주입
    const el = document.createElement('style');
    el.textContent = PRINT_STYLE;
    document.head.appendChild(el);
    styleRef.current = el;

    fetch(`${API}/certificates/info?token=${tok}`)
      .then(r => r.json())
      .then(d => {
        if (d.detail) throw new Error(d.detail);
        setInfo(d);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));

    return () => {
      if (styleRef.current) document.head.removeChild(styleRef.current);
    };
  }, []);

  const handlePrint = async () => {
    if (!token) return;
    setPrinting(true);
    try {
      // 발급 로그 기록
      await fetch(`${API}/certificates/log?token=${token}&cert_type=${certType === 'employment' ? '재직증명서' : '경력증명서'}&purpose=${encodeURIComponent(purpose)}`, {
        method: 'POST',
      });
    } catch { /* 로그 실패해도 인쇄는 진행 */ }
    window.print();
    setPrinting(false);
  };

  if (loading) return <div style={{ padding: '2rem', color: '#888' }}>로딩 중...</div>;
  if (error) return <div style={{ padding: '2rem', color: '#dc3545' }}>{error}</div>;
  if (!info) return null;

  return (
    <div style={{ padding: '1.25rem', maxWidth: 900 }}>
      {/* 헤더 (인쇄 시 숨김) */}
      <div className="no-print" style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.25rem' }}>📄 증명서 발급</h2>
        <p style={{ color: '#6c757d', fontSize: '0.875rem' }}>발급 후 브라우저 인쇄 기능으로 PDF 저장이 가능합니다.</p>
      </div>

      {/* 컨트롤 패널 */}
      <div className="no-print" style={{
        background: 'white', border: '1px solid #e5e7eb', borderRadius: 10,
        padding: '1.25rem', marginBottom: '1.5rem', display: 'flex', gap: '1rem',
        alignItems: 'flex-end', flexWrap: 'wrap',
      }}>
        {/* 종류 선택 */}
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.3rem', fontWeight: 600 }}>증명서 종류</label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {([['employment', '재직증명서'], ['career', '경력증명서']] as const).map(([val, label]) => (
              <button key={val} onClick={() => setCertType(val)}
                style={{
                  padding: '0.45rem 1.1rem', border: '2px solid',
                  borderColor: certType === val ? '#1a3c6e' : '#d1d5db',
                  background: certType === val ? '#1a3c6e' : 'white',
                  color: certType === val ? 'white' : '#374151',
                  borderRadius: 6, cursor: 'pointer', fontWeight: certType === val ? 700 : 400,
                  fontSize: '0.875rem',
                }}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* 발급 목적 */}
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.3rem', fontWeight: 600 }}>발급 목적</label>
          <input
            type="text"
            value={purpose}
            onChange={e => setPurpose(e.target.value)}
            placeholder="예: 금융기관 제출용, 관공서 제출용 ..."
            style={{ width: '100%', padding: '0.45rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 6, fontSize: '0.875rem', boxSizing: 'border-box' }}
          />
        </div>

        {/* 인쇄 버튼 */}
        <button onClick={handlePrint} disabled={printing}
          style={{
            padding: '0.5rem 1.5rem', background: printing ? '#9ca3af' : '#1a3c6e',
            color: 'white', border: 'none', borderRadius: 6,
            cursor: printing ? 'default' : 'pointer', fontWeight: 700, fontSize: '0.875rem',
            whiteSpace: 'nowrap',
          }}>
          🖨️ {printing ? '준비 중...' : 'PDF / 인쇄'}
        </button>
      </div>

      {/* 안내 */}
      <div className="no-print" style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '0.75rem 1rem', marginBottom: '1.5rem', fontSize: '0.8rem', color: '#1d4ed8' }}>
        💡 PDF 저장 방법: 인쇄 버튼 클릭 → 프린터를 <strong>"PDF로 저장"</strong> 선택 → 저장
      </div>

      {/* 증명서 미리보기 */}
      {certType === 'employment'
        ? <EmploymentCert info={info} purpose={purpose} />
        : <CareerCert info={info} purpose={purpose} />
      }
    </div>
  );
}

// ─── 공통 스타일 ──────────────────────────────────────────────────────
const certWrap: React.CSSProperties = {
  background: 'white',
  border: '1px solid #d1d5db',
  borderRadius: 8,
  padding: '40px 50px',
  fontFamily: "'Malgun Gothic', '맑은 고딕', AppleGothic, sans-serif",
  maxWidth: 680,
  boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
};

const certTitle: React.CSSProperties = {
  textAlign: 'center',
  fontSize: '2rem',
  fontWeight: 700,
  letterSpacing: '0.3em',
  color: '#1a3c6e',
  borderBottom: '3px solid #1a3c6e',
  paddingBottom: '0.5rem',
  marginBottom: '0.35rem',
};

const certSubtitle: React.CSSProperties = {
  textAlign: 'center',
  fontSize: '0.85rem',
  color: '#6b7280',
  letterSpacing: '0.15em',
  marginBottom: '2.5rem',
};

const infoTable: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  marginBottom: '0.5rem',
};

const tdLabel: React.CSSProperties = {
  padding: '0.6rem 1rem',
  background: '#f0f4f8',
  fontWeight: 600,
  fontSize: '0.9rem',
  color: '#374151',
  borderTop: '1px solid #d1d5db',
  borderBottom: '1px solid #d1d5db',
  width: '130px',
  whiteSpace: 'nowrap',
};

const tdValue: React.CSSProperties = {
  padding: '0.6rem 1.2rem',
  fontSize: '0.9rem',
  color: '#111827',
  borderTop: '1px solid #d1d5db',
  borderBottom: '1px solid #d1d5db',
};

const bodyText: React.CSSProperties = {
  marginTop: '2.5rem',
  textAlign: 'center',
  fontSize: '1rem',
  fontWeight: 600,
  color: '#111827',
  letterSpacing: '0.03em',
};

const dateText: React.CSSProperties = {
  textAlign: 'center',
  marginTop: '2.5rem',
  fontSize: '1rem',
  color: '#374151',
  letterSpacing: '0.05em',
};

const companyBlock: React.CSSProperties = {
  marginTop: '2rem',
  textAlign: 'center',
  borderTop: '2px solid #1a3c6e',
  paddingTop: '1.5rem',
};

const companyName: React.CSSProperties = {
  fontSize: '1.3rem',
  fontWeight: 700,
  color: '#1a3c6e',
  letterSpacing: '0.1em',
  marginBottom: '0.4rem',
};

const companyDetail: React.CSSProperties = {
  fontSize: '0.85rem',
  color: '#6b7280',
  marginBottom: '0.15rem',
};

const sealImg: React.CSSProperties = {
  width: 80,
  height: 80,
  objectFit: 'contain',
};
