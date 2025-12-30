'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { getLogs, getLogStats, ActivityLog, LogFilters, LogStats } from '@/lib/api';

export default function LogsPage() {
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [filters, setFilters] = useState<LogFilters | null>(null);
  const [stats, setStats] = useState<LogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  // 필터 상태
  const [periodFrom, setPeriodFrom] = useState('');
  const [periodTo, setPeriodTo] = useState('');
  const [actionType, setActionType] = useState('');
  const [targetType, setTargetType] = useState('');
  const [userNickname, setUserNickname] = useState('');
  const [targetName, setTargetName] = useState('');

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedIsAdmin = localStorage.getItem('isAdmin') === 'true';
    setToken(storedToken);
    setIsAdmin(storedIsAdmin);

    if (!storedIsAdmin) {
      setError('관리자 권한이 필요합니다.');
      setLoading(false);
      return;
    }

    if (storedToken) {
      loadData(storedToken);
    }
  }, []);

  const loadData = async (authToken: string) => {
    try {
      setLoading(true);
      setError(null);

      const [logsRes, statsRes] = await Promise.all([
        getLogs(authToken, {
          period_from: periodFrom || undefined,
          period_to: periodTo || undefined,
          action_type: actionType || undefined,
          target_type: targetType || undefined,
          user_nickname: userNickname || undefined,
          target_name: targetName || undefined,
          limit: 500,
        }),
        getLogStats(authToken),
      ]);

      setLogs(logsRes.logs);
      setFilters(logsRes.filters);
      setStats(statsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    if (token) {
      loadData(token);
    }
  };

  const handleReset = () => {
    setPeriodFrom('');
    setPeriodTo('');
    setActionType('');
    setTargetType('');
    setUserNickname('');
    setTargetName('');
    if (token) {
      setTimeout(() => loadData(token), 100);
    }
  };

  if (!isAdmin) {
    return (
      <div style={{ padding: '2rem' }}>
        <Alert type="error" message="관리자 권한이 필요합니다." onClose={() => {}} />
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '1rem' }}>
        활동 로그
      </h1>

      {error && (
        <Alert type="error" message={error} onClose={() => setError(null)} />
      )}

      {/* 통계 카드 */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <Card title="전체 로그">
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stats.total.toLocaleString()}</p>
          </Card>
          <Card title="오늘 로그">
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#2563eb' }}>{stats.today.toLocaleString()}</p>
          </Card>
          {stats.by_action.slice(0, 3).map((item, idx) => (
            <Card key={idx} title={item.action_type}>
              <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{item.count.toLocaleString()}</p>
            </Card>
          ))}
        </div>
      )}

      {/* 필터 */}
      <Card title="필터">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.5rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>시작일</label>
            <input
              type="date"
              value={periodFrom}
              onChange={(e) => setPeriodFrom(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>종료일</label>
            <input
              type="date"
              value={periodTo}
              onChange={(e) => setPeriodTo(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>액션 유형</label>
            <select
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              {filters?.action_types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>대상 유형</label>
            <select
              value={targetType}
              onChange={(e) => setTargetType(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              {filters?.target_types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>작업자</label>
            <select
              value={userNickname}
              onChange={(e) => setUserNickname(e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            >
              <option value="">전체</option>
              {filters?.users.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>대상명 검색</label>
            <input
              type="text"
              value={targetName}
              onChange={(e) => setTargetName(e.target.value)}
              placeholder="업체명 등"
              style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
            />
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handleSearch}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            검색
          </button>
          <button
            onClick={handleReset}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#6b7280',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            초기화
          </button>
        </div>
      </Card>

      {/* 로그 목록 */}
      <Card title={`로그 목록 (${logs.length}건)`} style={{ marginTop: '1rem' }}>
        {loading ? (
          <Loading />
        ) : logs.length === 0 ? (
          <p style={{ color: '#666' }}>로그가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>시각</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>액션</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>대상 유형</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>대상명</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>작업자</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #ddd' }}>상세</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.log_id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '0.5rem', whiteSpace: 'nowrap' }}>
                      {log.created_at ? new Date(log.created_at).toLocaleString('ko-KR') : '-'}
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.125rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        backgroundColor: getActionColor(log.action_type),
                        color: 'white',
                      }}>
                        {log.action_type}
                      </span>
                    </td>
                    <td style={{ padding: '0.5rem' }}>{log.target_type || '-'}</td>
                    <td style={{ padding: '0.5rem' }}>{log.target_name || '-'}</td>
                    <td style={{ padding: '0.5rem' }}>{log.user_nickname || '-'}</td>
                    <td style={{ padding: '0.5rem', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {log.details || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function getActionColor(action: string): string {
  // 삭제 관련 (빨간색)
  if (action.includes('삭제')) return '#dc2626';
  
  // 확정 관련 (초록색)
  if (action.includes('확정') && !action.includes('미확정')) return '#16a34a';
  
  // 미확정 관련 (주황색)
  if (action.includes('미확정')) return '#f59e0b';
  
  // 수정/업데이트 관련 (파란색)
  if (action.includes('수정')) return '#2563eb';
  
  // 생성 관련 (보라색)
  if (action.includes('생성')) return '#8b5cf6';
  
  // 업로드 관련 (청록색)
  if (action.includes('업로드')) return '#06b6d4';
  
  // 인증 관련 (남색)
  if (action.includes('로그인')) return '#4f46e5';
  if (action.includes('로그아웃')) return '#64748b';
  
  // 거래처 관련 (분홍색)
  if (action.includes('거래처')) return '#ec4899';
  
  // 사용자 관련 (청록색)
  if (action.includes('사용자')) return '#0891b2';
  
  // 기본 색상 (회색)
  return '#6b7280';
}

