'use client';

import { useCallback, useEffect, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import {
  cancelKpostPickup,
  listKpostPickups,
  type KpostPickupItem,
} from '@/lib/api';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
};

function parseApiError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    /* ignore */
  }
  return raw;
}

export default function KpostPickupListPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [items, setItems] = useState<KpostPickupItem[]>([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [recipientFilter, setRecipientFilter] = useState('');

  const loadList = useCallback(
    async (auth: string, filters?: { dateFrom?: string; dateTo?: string; recipientName?: string }) => {
      const data = await listKpostPickups(auth, filters);
      setItems(data.items || []);
    },
    []
  );

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        await loadList(stored);
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [loadList]);

  async function handleFilter() {
    setError(null);
    try {
      const filters = {
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        recipientName: recipientFilter || undefined,
      };
      await loadList(token, filters);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleCancel(id: number, tracking: string) {
    if (!window.confirm(`송장 ${tracking || id} 회수신청을 취소할까요?`)) return;
    setError(null);
    try {
      const result = await cancelKpostPickup(token, id);
      setSuccess(result.message || '회수신청을 취소했습니다.');
      const filters = {
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        recipientName: recipientFilter || undefined,
      };
      await loadList(token, filters);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  if (loading) return <Loading text="회수신청 목록 로딩 중..." />;

  return (
    <div>
      <PageHeader title="회수신청 목록" subtitle="우체국 회수신청 접수 내역을 조회하고 관리합니다." />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <Card title="회수신청 목록">
        <div
          style={{
            marginBottom: '1rem',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr auto',
            gap: '0.5rem',
            alignItems: 'end',
          }}
        >
          <label>
            수거일 (시작)
            <input type="date" style={inputStyle} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            수거일 (종료)
            <input type="date" style={inputStyle} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label>
            수취인
            <input
              style={inputStyle}
              value={recipientFilter}
              onChange={(e) => setRecipientFilter(e.target.value)}
              placeholder="수취인 이름 검색"
            />
          </label>
          <button type="button" className="btn btn-secondary" onClick={handleFilter}>
            조회
          </button>
        </div>
        {items.length === 0 ? (
          <p className="text-muted">접수 내역이 없습니다.</p>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>송장</th>
                  <th>수취인</th>
                  <th>주소</th>
                  <th>수거일</th>
                  <th>박스</th>
                  <th>상태</th>
                  <th>작성</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {item.tracking_no || '-'}
                      {item.is_test ? ' (테스트)' : ''}
                    </td>
                    <td>
                      {item.recipient_name}
                      <div className="text-muted">{item.recipient_phone}</div>
                    </td>
                    <td>
                      [{item.zipcode}] {item.addr1} {item.addr2}
                    </td>
                    <td>{item.pickup_date}</td>
                    <td>
                      {item.box_size} × {item.box_quantity || 1}
                    </td>
                    <td>{item.status === 'canceled' ? '취소' : item.treat_status_name || item.status}</td>
                    <td>
                      {item.created_by}
                      <div className="text-muted">{item.created_at?.replace('T', ' ').slice(0, 16)}</div>
                    </td>
                    <td>
                      {item.status === 'requested' && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => handleCancel(item.id, item.tracking_no)}
                        >
                          취소
                        </button>
                      )}
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
