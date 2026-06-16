'use client';

import { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const HOURS_PER_DAY = 7;

// ─────────────────────────────────────
// 타입 정의
// ─────────────────────────────────────

interface LeaveSummary {
  user_id: number;
  nickname: string;
  year: number;
  join_date: string;
  work_year_start?: string;
  work_year_end?: string;
  total_hours: number;
  total_days: number;
  used_hours: number;
  used_days: number;
  pending_hours: number;
  pending_days: number;
  remaining_hours: number;
  remaining_days: number;
  exempt?: boolean;
  no_join_date?: boolean;
}

interface LeaveRequest {
  id: number;
  leave_type: string;
  start_date: string;
  end_date: string;
  hours_requested: number;
  days_requested: number;
  reason: string | null;
  status: string;
  created_at: string;
  approvals: string;
}

interface PendingApproval {
  approval_id: number;
  request_id: number;
  step: number;
  leave_type: string;
  start_date: string;
  end_date: string;
  hours_requested: number;
  days_requested: number;
  reason: string | null;
  created_at: string;
  requester_nickname: string;
  requester_department: string;
  requester_position: string;
  approval_type: 'normal' | 'cancel';  // cancel = 취소결재
}

interface ApprovalHistory {
  approval_id: number;
  request_id: number;
  step: number;
  status: string;        // approved / rejected / cancelled
  comment: string | null;
  acted_at: string | null;
  leave_type: string;
  start_date: string;
  end_date: string;
  hours_requested: number;
  days_requested: number;
  req_status: string;
  cancel_reason: string | null;
  requester_nickname: string;
  requester_department: string;
  requester_position: string;
}

interface AdminUser {
  user_id: number;
  nickname: string;
  department: string;
  position: string;
  total_days: number;
  used_days: number;
  remaining_days: number;
  exempt?: boolean;
  no_join_date?: boolean;
}

// ─────────────────────────────────────
// 상태 배지
// ─────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; bg: string; color: string }> = {
    pending:          { label: '결재중',    bg: '#fff3cd', color: '#856404' },
    approved:         { label: '승인',      bg: '#d1e7dd', color: '#0a3622' },
    rejected:         { label: '반려',      bg: '#f8d7da', color: '#842029' },
    cancelled:        { label: '취소',      bg: '#e2e3e5', color: '#41464b' },
    cancel_requested: { label: '취소결재중', bg: '#fff0e6', color: '#c45000' },
  };
  const s = map[status] || { label: status, bg: '#e9ecef', color: '#495057' };
  return (
    <span style={{
      padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem',
      backgroundColor: s.bg, color: s.color, fontWeight: 600,
    }}>
      {s.label}
    </span>
  );
}

// ─────────────────────────────────────
// 연차 도넛 차트
// ─────────────────────────────────────

function LeaveDonut({ summary }: { summary: LeaveSummary }) {
  const total = summary.total_days;
  const used = summary.used_days;
  const pending = summary.pending_days;
  const remaining = summary.remaining_days;

  const isNegative = remaining < 0;
  const usedPct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  const pendingPct = total > 0 ? Math.min((pending / total) * 100, 100 - usedPct) : 0;

  const r = 54;
  const circ = 2 * Math.PI * r;
  const usedDash = (usedPct / 100) * circ;
  const pendingDash = (pendingPct / 100) * circ;
  const remainingDash = circ - usedDash - pendingDash;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', flexWrap: 'wrap' }}>
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r={r} fill="none" stroke="#e9ecef" strokeWidth="16" />
        {remainingDash > 0 && (
          <circle cx="70" cy="70" r={r} fill="none"
            stroke={isNegative ? '#dc3545' : '#198754'}
            strokeWidth="16"
            strokeDasharray={`${remainingDash} ${circ - remainingDash}`}
            strokeDashoffset={circ * 0.25}
            style={{ transform: `rotate(${(usedPct + pendingPct) * 3.6}deg)`, transformOrigin: '70px 70px' }}
          />
        )}
        {pendingDash > 0 && (
          <circle cx="70" cy="70" r={r} fill="none"
            stroke="#ffc107" strokeWidth="16"
            strokeDasharray={`${pendingDash} ${circ - pendingDash}`}
            strokeDashoffset={circ * 0.25}
            style={{ transform: `rotate(${usedPct * 3.6}deg)`, transformOrigin: '70px 70px' }}
          />
        )}
        {usedDash > 0 && (
          <circle cx="70" cy="70" r={r} fill="none"
            stroke="#0d6efd" strokeWidth="16"
            strokeDasharray={`${usedDash} ${circ - usedDash}`}
            strokeDashoffset={circ * 0.25}
          />
        )}
        <text x="70" y="65" textAnchor="middle" fontSize="20" fontWeight="bold" fill={isNegative ? '#dc3545' : '#212529'}>
          {remaining}일
        </text>
        <text x="70" y="82" textAnchor="middle" fontSize="11" fill="#6c757d">잔여</text>
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {[
          { color: '#0d6efd', label: '사용', value: `${used}일 (${summary.used_hours}h)` },
          { color: '#ffc107', label: '결재중', value: `${pending}일 (${summary.pending_hours}h)` },
          { color: isNegative ? '#dc3545' : '#198754', label: '잔여', value: `${remaining}일 (${summary.remaining_hours}h)` },
          { color: '#e9ecef', label: '총 부여', value: `${total}일 (${summary.total_hours}h)`, border: '1px solid #dee2e6' },
        ].map(item => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <div style={{ width: 12, height: 12, borderRadius: 2, backgroundColor: item.color, border: (item as {border?: string}).border, flexShrink: 0 }} />
            <span style={{ fontSize: '0.875rem', color: '#495057', minWidth: 40 }}>{item.label}</span>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>{item.value}</span>
          </div>
        ))}
        {summary.work_year_start && summary.work_year_end && (
          <div style={{ marginTop: '0.5rem', padding: '0.4rem 0.6rem', background: '#f8f9fa', borderRadius: 6, fontSize: '0.78rem', color: '#6c757d' }}>
            📅 연차 기간: {summary.work_year_start} ~ {summary.work_year_end}
          </div>
        )}
      </div>
    </div>
  );
}



// ─────────────────────────────────────
// 메인 페이지
// ─────────────────────────────────────

export default function LeavePage() {
  const [tab, setTab] = useState<'my' | 'approvals' | 'admin'>('my');
  const [year, setYear] = useState(new Date().getFullYear());
  const [token, setToken] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 내 연차
  const [summary, setSummary] = useState<LeaveSummary | null>(null);
  const [requests, setRequests] = useState<LeaveRequest[]>([]);

  // 결재
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [approvalHistory, setApprovalHistory] = useState<ApprovalHistory[]>([]);
  const [rejectComment, setRejectComment] = useState('');
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  // 취소 모달
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState('');

  // 취소결재 반려 모달
  const [rejectingCancelId, setRejectingCancelId] = useState<number | null>(null);  // request_id
  const [rejectCancelComment, setRejectCancelComment] = useState('');

  // 신청 폼
  const [showForm, setShowForm] = useState(false);
  const [formLeaveType, setFormLeaveType] = useState('연차');
  const [formStartDate, setFormStartDate] = useState('');
  const [formEndDate, setFormEndDate] = useState('');
  const [formReason, setFormReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 관리자
  const [adminData, setAdminData] = useState<AdminUser[]>([]);

  useEffect(() => {
    const t = localStorage.getItem('token') || '';
    const u = localStorage.getItem('user');
    setToken(t);
    if (u) {
      try { setIsAdmin(JSON.parse(u).is_admin); } catch {}
    }
    setLoading(false);
  }, []);

  const fetchMySummary = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/leave/summary?token=${token}&year=${year}`);
      if (res.ok) setSummary(await res.json());
    } catch {}
  }, [token, year]);

  const fetchMyRequests = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/leave/requests?token=${token}&year=${year}`);
      if (res.ok) setRequests(await res.json());
    } catch {}
  }, [token, year]);

  const fetchPendingApprovals = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/leave/pending-approvals?token=${token}`);
      if (res.ok) setPendingApprovals(await res.json());
    } catch {}
  }, [token]);

  const fetchApprovalHistory = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/leave/approval-history?token=${token}&limit=100`);
      if (res.ok) setApprovalHistory(await res.json());
    } catch {}
  }, [token]);

  const fetchAdminData = useCallback(async () => {
    if (!token || !isAdmin) return;
    try {
      const res = await fetch(`${API_URL}/leave/admin/all?token=${token}&year=${year}`);
      if (res.ok) setAdminData(await res.json());
    } catch {}
  }, [token, isAdmin, year]);

  useEffect(() => {
    if (!token) return;
    fetchMySummary();
    fetchMyRequests();
    fetchPendingApprovals();
    fetchApprovalHistory();
    if (isAdmin) fetchAdminData();
  }, [token, year, fetchMySummary, fetchMyRequests, fetchPendingApprovals, fetchApprovalHistory, fetchAdminData]);

  function showMsg(msg: string, isError = false) {
    if (isError) { setError(msg); setSuccess(null); }
    else { setSuccess(msg); setError(null); }
    setTimeout(() => { setError(null); setSuccess(null); }, 4000);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!formStartDate) return showMsg('시작일을 선택하세요.', true);
    if (!formEndDate) return showMsg('종료일을 선택하세요.', true);

    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/leave/requests?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          leave_type: formLeaveType,
          start_date: formStartDate,
          end_date: formEndDate,
          reason: formReason || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '신청 실패');
      showMsg(`연차 신청 완료! ${data.days_requested}일 (${data.hours_requested}시간)`);
      setShowForm(false);
      setFormStartDate(''); setFormEndDate(''); setFormReason(''); setFormLeaveType('연차');
      fetchMySummary(); fetchMyRequests();
    } catch (err) {
      showMsg(err instanceof Error ? err.message : '신청 실패', true);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancel(requestId: number, reason = '') {
    try {
      const res = await fetch(`${API_URL}/leave/requests/${requestId}/cancel?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '취소 실패');
      showMsg(data.message || '연차가 취소되었습니다.');
      setCancelingId(null); setCancelReason('');
      fetchMySummary(); fetchMyRequests();
      if (isAdmin) fetchAdminData();
    } catch (err) {
      showMsg(err instanceof Error ? err.message : '취소 실패', true);
    }
  }

  // 취소결재 승인/반려
  async function handleCancelApprove(requestId: number, action: 'approve' | 'reject', comment = '') {
    try {
      const res = await fetch(`${API_URL}/leave/requests/${requestId}/cancel-approve?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, comment }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '처리 실패');
      showMsg(data.message || '처리되었습니다.');
      setRejectingCancelId(null); setRejectCancelComment('');
      fetchPendingApprovals(); fetchApprovalHistory(); fetchMySummary();
    } catch (err) {
      showMsg(err instanceof Error ? err.message : '처리 실패', true);
    }
  }

  async function handleApprove(approvalId: number) {
    try {
      const res = await fetch(`${API_URL}/leave/approvals/${approvalId}/act?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'approve' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '승인 실패');
      showMsg(data.message || '승인되었습니다.');
      fetchPendingApprovals(); fetchMySummary(); fetchApprovalHistory();
    } catch (err) {
      showMsg(err instanceof Error ? err.message : '승인 실패', true);
    }
  }

  async function handleReject(approvalId: number) {
    if (!rejectComment.trim()) return showMsg('반려 사유를 입력하세요.', true);
    try {
      const res = await fetch(`${API_URL}/leave/approvals/${approvalId}/act?token=${token}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reject', comment: rejectComment }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '반려 실패');
      showMsg(data.message || '반려 처리되었습니다.');
      setRejectingId(null); setRejectComment('');
      fetchPendingApprovals(); fetchApprovalHistory();
    } catch (err) {
      showMsg(err instanceof Error ? err.message : '반려 실패', true);
    }
  }

  if (loading) return <div style={{ padding: '2rem' }}>로딩 중...</div>;

  const card: React.CSSProperties = {
    backgroundColor: 'white', borderRadius: '8px', padding: '1.5rem',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem',
  };

  return (
    <div style={{ padding: '1.5rem', maxWidth: '960px' }}>
      <div style={{ marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0, lineHeight: 1.3 }}>
          연월차 관리
        </h1>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          근로기준법 기준 | 1일 = 7시간 (10:00~18:00)
        </p>
      </div>

      {/* 알림 */}
      {error && <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: '1rem' }}>{success}</div>}

      {/* 연도 선택 + 탭 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
          {[
            { key: 'my', label: '내 연차' },
            { key: 'approvals', label: `결재함${pendingApprovals.length > 0 ? ` (${pendingApprovals.length})` : ''}` },
            ...(isAdmin ? [{ key: 'admin', label: '전체 현황' }] : []),
          ].map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key as any)}
              style={{
                padding: '0.5rem 1rem', border: 'none', borderRadius: '4px', cursor: 'pointer',
                backgroundColor: tab === key ? '#0d6efd' : '#e9ecef',
                color: tab === key ? 'white' : '#495057', fontWeight: tab === key ? 600 : 400,
              }}>
              {label}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <select value={year} onChange={e => setYear(Number(e.target.value))}
            style={{ padding: '0.4rem 0.75rem', border: '1px solid #dee2e6', borderRadius: '4px', fontSize: '0.875rem' }}>
            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>{y}년</option>)}
          </select>
        </div>
      </div>

      {/* ── 내 연차 탭 ── */}
      {tab === 'my' && (
        <>
          {/* 연차 현황 카드 */}
          <div style={card}>
            {summary && !summary.exempt && !summary.no_join_date ? (
              <LeaveDonut summary={summary} />
            ) : summary?.exempt ? (
              <p style={{ color: '#6c757d' }}>연차 관리 대상이 아닙니다.</p>
            ) : summary?.no_join_date ? (
              <p style={{ color: '#dc3545' }}>입사일이 등록되지 않았습니다. 관리자에게 문의하세요.</p>
            ) : (
              <p style={{ color: '#6c757d' }}>연차 정보를 불러오는 중...</p>
            )}
          </div>

          {/* 신청 버튼 */}
          {summary && !summary.exempt && !summary.no_join_date && (
            <div style={{ marginBottom: '1.5rem' }}>
              <button onClick={() => setShowForm(!showForm)}
                style={{
                  padding: '0.6rem 1.25rem', backgroundColor: '#0d6efd', color: 'white',
                  border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600,
                }}>
                {showForm ? '닫기' : '연차 신청'}
              </button>
            </div>
          )}

          {/* 신청 폼 */}
          {showForm && (
            <div style={{ ...card, border: '2px solid #0d6efd' }}>
              <h4 style={{ marginBottom: '1rem' }}>연차 신청</h4>
              <form onSubmit={handleSubmit}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.25rem' }}>종류</label>
                    <select value={formLeaveType} onChange={e => setFormLeaveType(e.target.value)}
                      style={{ width: '100%', padding: '0.5rem', border: '1px solid #dee2e6', borderRadius: '4px' }}>
                      <option value="연차">연차</option>
                      <option value="반차(오전)">반차(오전)</option>
                      <option value="반차(오후)">반차(오후)</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.25rem' }}>시작일</label>
                    <input type="date" value={formStartDate}
                      onChange={e => { setFormStartDate(e.target.value); if (!formEndDate) setFormEndDate(e.target.value); }}
                      style={{ width: '100%', padding: '0.5rem', border: '1px solid #dee2e6', borderRadius: '4px' }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.25rem' }}>
                      {formLeaveType === '연차' ? '종료일' : '날짜'}
                    </label>
                    <input type="date" value={formEndDate}
                      onChange={e => setFormEndDate(e.target.value)}
                      disabled={formLeaveType !== '연차'}
                      style={{ width: '100%', padding: '0.5rem', border: '1px solid #dee2e6', borderRadius: '4px', backgroundColor: formLeaveType !== '연차' ? '#f8f9fa' : 'white' }} />
                  </div>
                </div>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.25rem' }}>사유 (선택)</label>
                  <input type="text" value={formReason} onChange={e => setFormReason(e.target.value)}
                    placeholder="연차 사유를 입력하세요 (선택사항)"
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid #dee2e6', borderRadius: '4px' }} />
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button type="submit" disabled={submitting}
                    style={{ padding: '0.5rem 1.5rem', backgroundColor: submitting ? '#ccc' : '#0d6efd', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                    {submitting ? '신청 중...' : '신청'}
                  </button>
                  <button type="button" onClick={() => setShowForm(false)}
                    style={{ padding: '0.5rem 1rem', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                    취소
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* 취소 확인 모달 */}
          {cancelingId !== null && (() => {
            const targetReq = requests.find(r => r.id === cancelingId);
            const isApproved = targetReq?.status === 'approved';
            return (
            <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ background: 'white', borderRadius: 10, padding: '1.5rem', width: 380, boxShadow: '0 8px 32px rgba(0,0,0,0.18)' }}>
                <h4 style={{ marginBottom: '0.5rem', color: isApproved ? '#fd7e14' : '#dc3545' }}>
                  {isApproved ? '승인된 연차 취소 요청' : '연차 취소'}
                </h4>
                <p style={{ fontSize: '0.875rem', color: '#555', marginBottom: '1rem' }}>
                  {isApproved
                    ? <>
                        승인된 연차는 <strong>결재라인 전원의 취소 승인</strong>이 필요합니다.<br />
                        모든 결재자가 승인해야 취소가 확정됩니다.
                      </>
                    : <>
                        취소 후에도 모든 기록은 이력에 보존됩니다.
                      </>
                  }
                </p>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#555', marginBottom: '0.3rem' }}>취소 사유 (선택)</label>
                  <input type="text" value={cancelReason} onChange={e => setCancelReason(e.target.value)}
                    placeholder="취소 사유를 입력하세요"
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid #dee2e6', borderRadius: 6, fontSize: '0.875rem', boxSizing: 'border-box' }} />
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                  <button onClick={() => { setCancelingId(null); setCancelReason(''); }}
                    style={{ padding: '0.45rem 1rem', background: '#6c757d', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
                    닫기
                  </button>
                  <button onClick={() => handleCancel(cancelingId, cancelReason)}
                    style={{ padding: '0.45rem 1rem', background: isApproved ? '#fd7e14' : '#dc3545', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}>
                    {isApproved ? '취소 요청 접수' : '취소 확정'}
                  </button>
                </div>
              </div>
            </div>
            );
          })()}

          {/* 신청 목록 */}
          <div style={card}>
            <h4 style={{ marginBottom: '1rem' }}>{year}년 신청 내역</h4>
            {requests.length === 0 ? (
              <p style={{ color: '#6c757d', fontSize: '0.875rem' }}>신청 내역이 없습니다.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #dee2e6' }}>
                      {['#', '종류', '기간', '일수', '사유', '상태', '결재자', ''].map(h => (
                        <th key={h} style={{ padding: '0.5rem', textAlign: 'left', fontWeight: 600, color: '#495057', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {requests.map(r => (
                      <tr key={r.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                        <td style={{ padding: '0.6rem 0.5rem', color: '#6c757d' }}>#{r.id}</td>
                        <td style={{ padding: '0.6rem 0.5rem', whiteSpace: 'nowrap' }}>{r.leave_type}</td>
                        <td style={{ padding: '0.6rem 0.5rem', whiteSpace: 'nowrap' }}>
                          {r.start_date === r.end_date ? r.start_date : `${r.start_date} ~ ${r.end_date}`}
                        </td>
                        <td style={{ padding: '0.6rem 0.5rem', whiteSpace: 'nowrap' }}>{r.days_requested}일</td>
                        <td style={{ padding: '0.6rem 0.5rem', color: '#495057' }}>{r.reason || '-'}</td>
                        <td style={{ padding: '0.6rem 0.5rem' }}><StatusBadge status={r.status} /></td>
                        <td style={{ padding: '0.6rem 0.5rem', fontSize: '0.75rem', color: '#6c757d' }}>
                          {r.approvals ? r.approvals.split('|').map((a, i) => {
                            const [name, st] = a.split(':');
                            return <span key={i} style={{ marginRight: 4 }}>{name}: <StatusBadge status={st} /></span>;
                          }) : '-'}
                        </td>
                        <td style={{ padding: '0.6rem 0.5rem' }}>
                          {(() => {
                            const today = new Date().toISOString().slice(0, 10);
                            const isPast = r.end_date < today;
                            if (r.status === 'cancel_requested') {
                              return (
                                <span style={{ fontSize: '0.72rem', color: '#c45000', fontStyle: 'italic' }}>취소결재 진행중</span>
                              );
                            }
                            if (r.status === 'pending' || r.status === 'approved') {
                              return (
                                <button
                                  onClick={() => { if (!isPast) { setCancelingId(r.id); setCancelReason(''); } }}
                                  disabled={isPast}
                                  title={isPast ? '이미 사용된 연차는 취소할 수 없습니다.' : ''}
                                  style={{
                                    padding: '2px 8px', fontSize: '0.75rem',
                                    backgroundColor: isPast ? '#dee2e6' : (r.status === 'approved' ? '#fd7e14' : '#dc3545'),
                                    color: isPast ? '#aaa' : 'white',
                                    border: 'none', borderRadius: '4px',
                                    cursor: isPast ? 'not-allowed' : 'pointer',
                                  }}>
                                  {r.status === 'approved' ? '취소 요청' : '취소'}
                                </button>
                              );
                            }
                            return null;
                          })()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── 결재함 탭 ── */}
      {tab === 'approvals' && (
        <>
          {/* 결재 대기 */}
          <div style={card}>
            <h4 style={{ marginBottom: '1rem' }}>
              결재 대기 목록
              {pendingApprovals.length > 0 && (
                <span style={{ marginLeft: '0.5rem', background: '#dc3545', color: 'white', borderRadius: '12px', padding: '1px 8px', fontSize: '0.78rem' }}>
                  {pendingApprovals.length}
                </span>
              )}
            </h4>
            {pendingApprovals.length === 0 ? (
              <p style={{ color: '#6c757d', fontSize: '0.875rem' }}>결재 대기 중인 연차가 없습니다. ✅</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {pendingApprovals.map(a => {
                  const isCancel = a.approval_type === 'cancel';
                  return (
                    <div key={`${isCancel ? 'c' : 'n'}-${a.approval_id}`} style={{
                      border: `2px solid ${isCancel ? '#fd7e14' : '#0d6efd'}`,
                      borderRadius: '8px', padding: '1rem',
                      backgroundColor: isCancel ? '#fff5eb' : '#f0f6ff',
                    }}>
                      {/* 헤더 배지 */}
                      {isCancel && (
                        <div style={{ marginBottom: '0.5rem' }}>
                          <span style={{ background: '#fd7e14', color: 'white', borderRadius: 6, padding: '2px 10px', fontSize: '0.75rem', fontWeight: 700 }}>
                            🔄 취소결재 요청
                          </span>
                          <span style={{ fontSize: '0.78rem', color: '#c45000', marginLeft: '0.5rem' }}>
                            승인 시 해당 연차가 취소됩니다
                          </span>
                        </div>
                      )}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <div>
                          <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                            {a.requester_nickname}
                            <span style={{ fontSize: '0.8rem', color: '#6c757d', fontWeight: 400, marginLeft: '0.5rem' }}>
                              {a.requester_department} · {a.requester_position} · {isCancel ? '취소결재' : '결재 요청'}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.875rem', color: '#495057' }}>
                            <strong>{a.leave_type}</strong> &nbsp;
                            {a.start_date === a.end_date ? a.start_date : `${a.start_date} ~ ${a.end_date}`}
                            &nbsp; <strong>{a.days_requested}일</strong> ({a.hours_requested}h)
                          </div>
                          {a.reason && (
                            <div style={{ fontSize: '0.8rem', color: '#6c757d', marginTop: '0.25rem' }}>
                              {isCancel ? '취소 사유' : '사유'}: {a.reason}
                            </div>
                          )}
                          <div style={{ fontSize: '0.75rem', color: '#aaa', marginTop: '0.2rem' }}>
                            {isCancel ? '취소요청일' : '신청일'}: {a.created_at ? new Date(a.created_at).toLocaleDateString('ko-KR') : '-'}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          {isCancel ? (
                            <>
                              <button onClick={() => handleCancelApprove(a.request_id, 'approve')}
                                style={{ padding: '0.4rem 1rem', backgroundColor: '#fd7e14', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}>
                                ✅ 취소 승인
                              </button>
                              <button onClick={() => setRejectingCancelId(rejectingCancelId === a.request_id ? null : a.request_id)}
                                style={{ padding: '0.4rem 1rem', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}>
                                ❌ 취소 반려
                              </button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => handleApprove(a.approval_id)}
                                style={{ padding: '0.4rem 1rem', backgroundColor: '#198754', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}>
                                ✅ 승인
                              </button>
                              <button onClick={() => setRejectingId(rejectingId === a.approval_id ? null : a.approval_id)}
                                style={{ padding: '0.4rem 1rem', backgroundColor: '#dc3545', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}>
                                ❌ 반려
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                      {/* 일반 반려 입력 */}
                      {!isCancel && rejectingId === a.approval_id && (
                        <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                          <input type="text" value={rejectComment}
                            onChange={e => setRejectComment(e.target.value)}
                            placeholder="반려 사유를 입력하세요 (필수)"
                            autoFocus
                            style={{ flex: 1, padding: '0.4rem 0.75rem', border: '1px solid #dee2e6', borderRadius: '4px', fontSize: '0.875rem' }} />
                          <button onClick={() => handleReject(a.approval_id)}
                            style={{ padding: '0.4rem 0.75rem', backgroundColor: '#dc3545', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                            반려 확정
                          </button>
                          <button onClick={() => { setRejectingId(null); setRejectComment(''); }}
                            style={{ padding: '0.4rem 0.5rem', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                            닫기
                          </button>
                        </div>
                      )}
                      {/* 취소결재 반려 입력 */}
                      {isCancel && rejectingCancelId === a.request_id && (
                        <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                          <input type="text" value={rejectCancelComment}
                            onChange={e => setRejectCancelComment(e.target.value)}
                            placeholder="취소 반려 사유를 입력하세요 (선택)"
                            autoFocus
                            style={{ flex: 1, padding: '0.4rem 0.75rem', border: '1px solid #dee2e6', borderRadius: '4px', fontSize: '0.875rem' }} />
                          <button onClick={() => handleCancelApprove(a.request_id, 'reject', rejectCancelComment)}
                            style={{ padding: '0.4rem 0.75rem', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                            반려 확정
                          </button>
                          <button onClick={() => { setRejectingCancelId(null); setRejectCancelComment(''); }}
                            style={{ padding: '0.4rem 0.5rem', backgroundColor: '#aaa', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                            닫기
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 처리 이력 */}
          <div style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h4 style={{ margin: 0 }}>
                처리 이력
                <span style={{ fontSize: '0.8rem', color: '#6c757d', fontWeight: 400, marginLeft: '0.5rem' }}>({approvalHistory.length}건)</span>
              </h4>
              <button onClick={() => setShowHistory(v => !v)}
                style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', background: '#f0f0f0', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}>
                {showHistory ? '접기 ▲' : '펼치기 ▼'}
              </button>
            </div>
            {showHistory && (
              approvalHistory.length === 0 ? (
                <p style={{ color: '#6c757d', fontSize: '0.875rem' }}>처리한 결재 이력이 없습니다.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                    <thead>
                      <tr style={{ background: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                        {['처리일시', '신청자', '종류', '기간', '일수', '결과', '사유/코멘트'].map(h => (
                          <th key={h} style={{ padding: '0.5rem 0.6rem', textAlign: 'left', fontWeight: 600, color: '#495057', whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {approvalHistory.map(h => (
                        <tr key={h.approval_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                          <td style={{ padding: '0.45rem 0.6rem', color: '#6c757d', whiteSpace: 'nowrap' }}>
                            {h.acted_at ? new Date(h.acted_at).toLocaleDateString('ko-KR') : '-'}
                          </td>
                          <td style={{ padding: '0.45rem 0.6rem', fontWeight: 600 }}>
                            {h.requester_nickname}
                            <span style={{ fontSize: '0.72rem', color: '#aaa', display: 'block' }}>{h.requester_department}</span>
                          </td>
                          <td style={{ padding: '0.45rem 0.6rem' }}>{h.leave_type}</td>
                          <td style={{ padding: '0.45rem 0.6rem', whiteSpace: 'nowrap' }}>
                            {h.start_date === h.end_date ? h.start_date : `${h.start_date}~${h.end_date}`}
                          </td>
                          <td style={{ padding: '0.45rem 0.6rem' }}>{h.days_requested}일</td>
                          <td style={{ padding: '0.45rem 0.6rem' }}>
                            <StatusBadge status={h.status} />
                            {h.req_status === 'cancelled' && h.status === 'approved' && (
                              <span style={{ display: 'block', fontSize: '0.68rem', color: '#fd7e14', marginTop: '2px' }}>신청자 취소됨</span>
                            )}
                          </td>
                          <td style={{ padding: '0.45rem 0.6rem', color: '#555', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                            title={h.comment || h.cancel_reason || ''}>
                            {h.comment || h.cancel_reason || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}
          </div>
        </>
      )}

      {/* ── 관리자 전체 현황 탭 ── */}
      {tab === 'admin' && isAdmin && (
        <div style={card}>
          <h4 style={{ marginBottom: '1rem' }}>{year}년 전체 직원 연차 현황</h4>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #dee2e6', backgroundColor: '#f8f9fa' }}>
                  {['이름', '팀', '직급', '총 부여', '사용', '잔여', '비고'].map(h => (
                    <th key={h} style={{ padding: '0.6rem 0.75rem', textAlign: 'left', fontWeight: 600, color: '#495057', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {adminData.map((u) => (
                  <tr key={u.user_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600 }}>{u.nickname}</td>
                    <td style={{ padding: '0.6rem 0.75rem', color: '#495057' }}>{u.department || '-'}</td>
                    <td style={{ padding: '0.6rem 0.75rem', color: '#495057' }}>{u.position || '-'}</td>
                    {u.exempt ? (
                      <td colSpan={4} style={{ padding: '0.6rem 0.75rem', color: '#6c757d', fontStyle: 'italic' }}>연차 관리 제외</td>
                    ) : u.no_join_date ? (
                      <td colSpan={4} style={{ padding: '0.6rem 0.75rem', color: '#dc3545' }}>입사일 미등록</td>
                    ) : (
                      <>
                        <td style={{ padding: '0.6rem 0.75rem' }}>{u.total_days}일</td>
                        <td style={{ padding: '0.6rem 0.75rem' }}>{u.used_days}일</td>
                        <td style={{ padding: '0.6rem 0.75rem' }}>
                          <span style={{ color: u.remaining_days < 0 ? '#dc3545' : u.remaining_days < 3 ? '#856404' : '#0a3622', fontWeight: 600 }}>
                            {u.remaining_days}일
                          </span>
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem' }}>
                          {u.remaining_days < 0 && <span style={{ fontSize: '0.75rem', color: '#dc3545' }}>마이너스</span>}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
