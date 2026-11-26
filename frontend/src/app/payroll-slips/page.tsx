'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { A4Preview } from '@/app/employment-contracts/a4-preview';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SlipRow {
  year: number;
  month: number;
  period_label: string;
  released_at: string | null;
  user_id: number;
  employee_name: string;
  affiliation: string;
  net_pay: number;
  mine: boolean;
}

function won(value: number) {
  return `${Number(value || 0).toLocaleString('ko-KR')}원`;
}

async function apiError(res: Response) {
  try {
    const data = await res.json();
    return data.detail || '요청을 처리하지 못했습니다.';
  } catch {
    return '요청을 처리하지 못했습니다.';
  }
}

export default function PayrollSlipsPage() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slips, setSlips] = useState<SlipRow[]>([]);
  const [pages, setPages] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const res = await fetch(`${API}/payroll-slips?token=${encodeURIComponent(token)}`);
    setLoading(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSlips(data.slips || []);
  }, []);

  useEffect(() => {
    try {
      setIsAdmin(!!JSON.parse(localStorage.getItem('user') || '{}').is_admin);
    } catch {
      setIsAdmin(false);
    }
    load();
  }, [load]);

  async function preview(row: SlipRow) {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    const query = isAdmin ? `&employee_name=${encodeURIComponent(row.employee_name)}` : '';
    const res = await fetch(`${API}/payroll-slips/${row.year}/${row.month}/pages?token=${encodeURIComponent(token)}${query}`);
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setPages(data.pages || []);
  }

  function download(row: SlipRow) {
    const token = localStorage.getItem('token') || '';
    const query = isAdmin ? `&employee_name=${encodeURIComponent(row.employee_name)}` : '';
    window.open(`${API}/payroll-slips/${row.year}/${row.month}/pdf?token=${encodeURIComponent(token)}${query}`, '_blank');
  }

  if (pages) {
    return <A4Preview pages={pages} overlay onClose={() => setPages(null)} title="급여명세서" />;
  }

  return (
    <div>
      <PageHeader
        title="급여명세서"
        subtitle={isAdmin ? '그달 급여대장으로 명세서를 만들고 근로자에게 제공합니다.' : '제공된 달의 본인 급여명세서를 확인하고 받을 수 있습니다.'}
      />
      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {loading ? (
        <Loading text="불러오는 중..." />
      ) : slips.length === 0 ? (
        <Card>
          <p style={{ margin: 0, color: '#6b7280' }}>
            {isAdmin ? '아직 만든 급여대장이 없습니다.' : '아직 제공된 급여명세서가 없습니다.'}
          </p>
        </Card>
      ) : (
        <Card>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  {(isAdmin ? ['연월', '성명', '소속', '실수령액', '제공', ''] : ['연월', '임금산정기간', '실수령액', '']).map((head) => (
                    <th key={head || 'actions'}>{head}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {slips.map((row) => (
                  <tr key={`${row.year}-${row.month}-${row.user_id}-${row.employee_name}`}>
                    <td>{row.year}년 {String(row.month).padStart(2, '0')}월</td>
                    {isAdmin ? (
                      <>
                        <td>{row.employee_name}</td>
                        <td>{row.affiliation || '—'}</td>
                        <td>{won(row.net_pay)}</td>
                        <td>{row.released_at ? '제공됨' : '대기'}</td>
                      </>
                    ) : (
                      <>
                        <td>{row.period_label}</td>
                        <td>{won(row.net_pay)}</td>
                      </>
                    )}
                    <td>
                      <Button type="button" variant="secondary" disabled={busy} onClick={() => preview(row)}>미리보기</Button>
                      {' '}
                      <Button type="button" variant="secondary" disabled={busy} onClick={() => download(row)}>PDF</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
