'use client';

import { useEffect, useState } from 'react';
import PageHeader from '@/components/ui/page-header';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { TableSummary } from '@/components/data';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import {
  RETURN_INFO_COLUMNS,
  RETURN_INFO_DATE_COLUMNS,
  downloadReturnInfoExcel,
  getReturnInfo,
  type ReturnInfoFilters,
} from '@/lib/api';

const DATE_COLUMNS = new Set<string>(RETURN_INFO_DATE_COLUMNS);
const WIDE_COLUMNS = new Set(['CS이력', '반품메모']);
const PAGE_SIZES = [20, 50, 100];

function emptyFilters(): ReturnInfoFilters {
  const filters: ReturnInfoFilters = { q: '' };
  RETURN_INFO_COLUMNS.forEach((column) => {
    if (DATE_COLUMNS.has(column)) {
      filters[`${column}_from`] = '';
      filters[`${column}_to`] = '';
    } else {
      filters[column] = '';
    }
  });
  return filters;
}

function cellText(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
}

export default function ReturnInfoPage() {
  const [draft, setDraft] = useState<ReturnInfoFilters>(emptyFilters);
  const [applied, setApplied] = useState<ReturnInfoFilters>(emptyFilters);
  const [columns, setColumns] = useState<string[]>([...RETURN_INFO_COLUMNS]);
  const [rows, setRows] = useState<Array<Record<string, string | number | null>>>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getReturnInfo(applied, page, pageSize)
      .then((data) => {
        if (cancelled) return;
        setColumns(data.columns?.length ? data.columns : [...RETURN_INFO_COLUMNS]);
        setRows(data.rows || []);
        setTotal(data.total || 0);
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        setTotal(0);
        setMessage({ type: 'error', text: err instanceof Error ? err.message : '조회 실패' });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const extraColumns = columns.filter((column) => !RETURN_INFO_COLUMNS.includes(column as typeof RETURN_INFO_COLUMNS[number]));

  function updateDraft(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function search() {
    setPage(1);
    setApplied({ ...draft });
    setMessage(null);
  }

  function resetFilters() {
    const cleared = emptyFilters();
    setDraft(cleared);
    setApplied(cleared);
    setPage(1);
    setMessage(null);
  }

  return (
    <div>
      <PageHeader title="반품정보 조회" subtitle="재입고 대기 엑셀의 헤더 그대로 찾고 내려받습니다." />

      {message && <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />}

          <Card title="필터">
            <div className="return-filter-block">
              <Field label="전체 검색" hint="아무개를 치면 아무개입고, 아무개반송, 아무개1처럼 그 글자가 들어 있는 칸을 모두 찾습니다.">
                <input
                  type="search"
                  aria-label="전체 검색"
                  value={draft.q || ''}
                  maxLength={100}
                  placeholder="찾을 단어"
                  onChange={(event) => updateDraft('q', event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') search();
                  }}
                />
              </Field>
            </div>
            <div className="return-filter-block">
              <h2>날짜</h2>
              <div className="return-filter-dates">
                {RETURN_INFO_DATE_COLUMNS.map((column) => (
                  <Field key={column} label={column}>
                    <div className="return-filter-range">
                      <input
                        type="date"
                        aria-label={`${column} 시작`}
                        value={draft[`${column}_from`] || ''}
                        onChange={(event) => updateDraft(`${column}_from`, event.target.value)}
                      />
                      <input
                        type="date"
                        aria-label={`${column} 종료`}
                        value={draft[`${column}_to`] || ''}
                        onChange={(event) => updateDraft(`${column}_to`, event.target.value)}
                      />
                    </div>
                  </Field>
                ))}
              </div>
            </div>
            <div className="return-filter-block">
              <h2>조건</h2>
              <div className="return-filter-fields">
                {RETURN_INFO_COLUMNS.filter((column) => !DATE_COLUMNS.has(column)).map((column) => (
                  <Field key={column} label={column} className={WIDE_COLUMNS.has(column) ? 'return-filter-wide' : undefined}>
                    <input
                      type="text"
                      aria-label={column}
                      value={draft[column] || ''}
                      onChange={(event) => updateDraft(column, event.target.value)}
                      placeholder="포함 검색"
                    />
                  </Field>
                ))}
                {extraColumns.map((column) => (
                  <Field key={column} label={column}>
                    <input
                      type="text"
                      aria-label={column}
                      value={draft[column] || ''}
                      onChange={(event) => updateDraft(column, event.target.value)}
                      placeholder="포함 검색"
                    />
                  </Field>
                ))}
              </div>
            </div>
            <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2">
              <Button type="button" onClick={search}>검색</Button>
              <Button type="button" variant="ghost" onClick={resetFilters}>초기화</Button>
              <Button
                type="button"
                variant="secondary"
                disabled={exporting}
                onClick={async () => {
                  setExporting(true);
                  setMessage(null);
                  try {
                    await downloadReturnInfoExcel(applied);
                    setMessage({ type: 'success', text: '엑셀을 저장했습니다.' });
                  } catch (err) {
                    setMessage({ type: 'error', text: err instanceof Error ? err.message : '엑셀 생성 실패' });
                  } finally {
                    setExporting(false);
                  }
                }}
              >
                {exporting ? '엑셀 만드는 중...' : '엑셀 다운로드'}
              </Button>
            </div>
            <p className="caption tw-mb-0 tw-mt-2">
              전체 검색은 모든 칸을 보고, 아래 조건과 함께 쓰면 둘 다 맞는 행만 남습니다. 날짜는 위가 시작, 아래가 종료입니다. 엑셀은 화면 페이지와 관계없이 이 조건의 전체 건을 담습니다.
            </p>
          </Card>

          <div className="tw-mb-2 tw-mt-3 tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2">
            <TableSummary>
              반품정보 {rows.length}/{total}건 · {page}/{totalPages}페이지
            </TableSummary>
            <Field label="페이지당" className="tw-mb-0">
              <Select
                aria-label="페이지당"
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setPage(1);
                }}
              >
                {PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>{size}개</option>
                ))}
              </Select>
            </Field>
          </div>

          <Card title="">
            {loading ? (
              <Loading />
            ) : rows.length === 0 ? (
              <p className="caption">조건에 맞는 반품정보가 없습니다.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      {columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={`${row.관리번호 ?? ''}-${index}`}>
                        {columns.map((column) => (
                          <td key={column} className={column === 'CS이력' || column === '반품메모' ? 'cell-truncate' : undefined} title={cellText(row[column])}>
                            {cellText(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <Button type="button" variant="ghost" disabled={page <= 1} onClick={() => setPage(1)}>처음</Button>
              <Button type="button" variant="ghost" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>이전</Button>
              <span className="caption" style={{ alignSelf: 'center' }}>{page} / {totalPages}</span>
              <Button type="button" variant="ghost" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>다음</Button>
              <Button type="button" variant="ghost" disabled={page >= totalPages} onClick={() => setPage(totalPages)}>마지막</Button>
            </div>
          </Card>
    </div>
  );
}
