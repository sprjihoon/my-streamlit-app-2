'use client';

import { useCallback, useEffect, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import PageHeader from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { A4Preview } from '@/app/employment-contracts/a4-preview';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const PAGE_SIZES = [10, 20, 50];

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

interface MonthOption {
  year: number;
  month: number;
  period_label: string;
  count: number;
}

function won(value: number) {
  return `${Number(value || 0).toLocaleString('ko-KR')}원`;
}

function monthKey(year: number, month: number) {
  return `${year}-${String(month).padStart(2, '0')}`;
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
  const [months, setMonths] = useState<MonthOption[]>([]);
  const [year, setYear] = useState<number | null>(null);
  const [month, setMonth] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    const token = localStorage.getItem('token') || '';
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({
      token,
      page: String(page),
      page_size: String(pageSize),
    });
    if (year) query.set('year', String(year));
    if (month) query.set('month', String(month));
    const res = await fetch(`${API}/payroll-slips?${query.toString()}`);
    if (!res.ok) {
      setLoading(false);
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    const nextMonths: MonthOption[] = data.months || [];
    setMonths(nextMonths);
    if (year === null && month === null && nextMonths.length) {
      setYear(nextMonths[0].year);
      setMonth(nextMonths[0].month);
      setPage(1);
      return;
    }
    setSlips(data.slips || []);
    setTotal(Number(data.total || 0));
    setLoading(false);
  }, [year, month, page, pageSize]);

  useEffect(() => {
    try {
      setIsAdmin(!!JSON.parse(localStorage.getItem('user') || '{}').is_admin);
    } catch {
      setIsAdmin(false);
    }
  }, []);

  useEffect(() => {
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

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const selected = year && month ? monthKey(year, month) : 'all';
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(safePage * pageSize, total);

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
      <Card style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'end' }}>
          <label className="ops-label">
            연월
            <select
              className="ui-control"
              value={selected}
              onChange={(event) => {
                const value = event.target.value;
                setPage(1);
                if (value === 'all') {
                  setYear(0);
                  setMonth(0);
                  return;
                }
                const [nextYear, nextMonth] = value.split('-').map(Number);
                setYear(nextYear);
                setMonth(nextMonth);
              }}
            >
              <option value="all">전체</option>
              {months.map((row) => (
                <option key={monthKey(row.year, row.month)} value={monthKey(row.year, row.month)}>
                  {row.year}년 {String(row.month).padStart(2, '0')}월 ({row.count}명)
                </option>
              ))}
            </select>
          </label>
          <label className="ops-label">
            페이지당
            <select
              className="ui-control"
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>{size}건</option>
              ))}
            </select>
          </label>
        </div>
      </Card>
      {loading ? (
        <Loading text="불러오는 중..." />
      ) : slips.length === 0 ? (
        <Card>
          <p style={{ margin: 0, color: '#6b7280' }}>
            {isAdmin ? '선택한 달의 급여명세서가 없습니다.' : '아직 제공된 급여명세서가 없습니다.'}
          </p>
        </Card>
      ) : (
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.85rem', color: '#6b7280' }}>{from}–{to} / {total}건</span>
            {totalPages > 1 && (
              <div style={{ display: 'flex', gap: '0.35rem', marginLeft: 'auto' }}>
                <Button type="button" variant="secondary" disabled={safePage <= 1} onClick={() => setPage(1)}>처음</Button>
                <Button type="button" variant="secondary" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>이전</Button>
                <span style={{ alignSelf: 'center', fontSize: '0.85rem' }}>{safePage} / {totalPages}</span>
                <Button type="button" variant="secondary" disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)}>다음</Button>
                <Button type="button" variant="secondary" disabled={safePage >= totalPages} onClick={() => setPage(totalPages)}>마지막</Button>
              </div>
            )}
          </div>
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
