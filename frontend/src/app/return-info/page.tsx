'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import PageHeader from '@/components/ui/page-header';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { TableSummary } from '@/components/data';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { ReturnInfoUpload } from '@/components/return-info-upload';
import { ReturnInfoCreateModal } from '@/components/return-info-create-modal';
import { ReturnInfoEditModal } from '@/components/return-info-edit-modal';
import { useYesNo } from '@/components/YesNoDialog';
import {
  RETURN_INFO_COLUMNS,
  RETURN_INFO_DATE_COLUMNS,
  downloadReturnInfoExcel,
  downloadReturnInfoReport,
  deleteReturnInfo,
  getReturnInfo,
  getReturnInfoOptions,
  updateReturnInfoDefect,
  type ReturnInfoChoices,
  type ReturnInfoFilters,
} from '@/lib/api';

const DATE_COLUMNS = new Set<string>(RETURN_INFO_DATE_COLUMNS);
const CHOICE_COLUMNS = ['판매처', '상품명', '공급처'] as const;
const MULTI_COLUMNS = ['판매처', '공급처'] as const;
const WIDE_COLUMNS = new Set(['반품메모', '수정사항메모']);
const SHORT_COLUMNS = new Set(['상태', '등록자', '관리번호', '주문번호', '수령자', '수량', '불량']);
const DEFECT_CHOICES = ['정상', '불량'] as const;
const LIST_COLUMNS = ['등록일', '관리번호', '판매처', '상품명', '수량', '불량', '수정사항메모', '공급처'] as const;
const LIST_CLASS: Record<string, string> = {
  등록일: 'return-col-date',
  관리번호: 'return-col-id',
  판매처: 'return-col-party',
  상품명: 'return-col-name',
  수량: 'return-col-qty',
  불량: 'return-col-flag',
  수정사항메모: 'return-col-memo',
  공급처: 'return-col-party',
};
const PAGE_SIZES = [20, 50, 100];

function rowId(row: Record<string, string | number | null>) {
  const value = row.id;
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null;
}

function errorText(err: unknown) {
  const raw = err instanceof Error ? err.message : '';
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    if (raw && !raw.startsWith('{')) return raw;
  }
  return '불량을 바꾸지 못했습니다.';
}

function todayKst() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
}

function defaultFilters(): ReturnInfoFilters {
  const filters: ReturnInfoFilters = { q: '' };
  const today = todayKst();
  RETURN_INFO_COLUMNS.forEach((column) => {
    if (DATE_COLUMNS.has(column)) {
      filters[`${column}_from`] = column === '등록일' ? today : '';
      filters[`${column}_to`] = column === '등록일' ? today : '';
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
  const [draft, setDraft] = useState<ReturnInfoFilters>(defaultFilters);
  const [applied, setApplied] = useState<ReturnInfoFilters>(defaultFilters);
  const [columns, setColumns] = useState<string[]>([...RETURN_INFO_COLUMNS]);
  const [rows, setRows] = useState<Array<Record<string, string | number | null>>>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [listVersion, setListVersion] = useState(0);
  const [choices, setChoices] = useState<ReturnInfoChoices>({ 판매처: [], 상품명: [], 공급처: [] });
  const [choiceQuery, setChoiceQuery] = useState<Record<string, string>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [defectChoice, setDefectChoice] = useState<'' | '정상' | '불량'>('');
  const [editMemo, setEditMemo] = useState('');
  const [savingDefect, setSavingDefect] = useState(false);
  const [editRow, setEditRow] = useState<Record<string, string | number | null> | null>(null);
  const [savingRow, setSavingRow] = useState<number | null>(null);
  const savingDefectRef = useRef(false);
  const savingRowRef = useRef<number | null>(null);
  const pageCheckRef = useRef<HTMLInputElement>(null);
  const { ask, dialog } = useYesNo();

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
  }, [applied, page, pageSize, listVersion]);

  useEffect(() => {
    let cancelled = false;
    getReturnInfoOptions()
      .then((data) => {
        if (cancelled) return;
        setChoices({
          판매처: Array.isArray(data?.판매처) ? data.판매처 : [],
          상품명: Array.isArray(data?.상품명) ? data.상품명 : [],
          공급처: Array.isArray(data?.공급처) ? data.공급처 : [],
        });
      })
      .catch(() => {
        if (!cancelled) setChoices({ 판매처: [], 상품명: [], 공급처: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [listVersion]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const tableColumns = LIST_COLUMNS.filter((column) => columns.includes(column));
  const extraColumns = columns.filter((column) => !RETURN_INFO_COLUMNS.includes(column as typeof RETURN_INFO_COLUMNS[number]));
  const dateActive = RETURN_INFO_DATE_COLUMNS.some((column) => draft[`${column}_from`] || draft[`${column}_to`]);
  const conditionColumns = [
    ...RETURN_INFO_COLUMNS.filter((column) => !DATE_COLUMNS.has(column) && column !== 'CS이력'),
    ...extraColumns,
  ];
  const lookupColumns = ['판매처', '공급처', '상품명', '바코드', '옵션'];
  const orderedConditionColumns = [
    ...[...SHORT_COLUMNS].filter((column) => conditionColumns.includes(column)),
    ...lookupColumns.filter((column) => conditionColumns.includes(column)),
    ...conditionColumns.filter((column) => !SHORT_COLUMNS.has(column) && !lookupColumns.includes(column) && column !== '반품메모'),
    ...conditionColumns.filter((column) => column === '반품메모'),
  ];
  const conditionActive = conditionColumns.some((column) => (draft[column] || '').trim());
  const pageIds = rows.map(rowId).filter((id): id is number => id !== null);
  const selectedCount = pageIds.filter((id) => selected.has(id)).length;
  const allChecked = pageIds.length > 0 && selectedCount === pageIds.length;

  useEffect(() => {
    if (pageCheckRef.current) {
      pageCheckRef.current.indeterminate = selectedCount > 0 && !allChecked;
    }
  }, [selectedCount, allChecked]);

  function toggleId(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function togglePage(checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => {
        if (checked) next.add(id);
        else next.delete(id);
      });
      return next;
    });
  }

  async function applyDefect() {
    if (savingDefectRef.current) return;
    const ids = pageIds.filter((id) => selected.has(id));
    if (ids.length === 0) {
      setMessage({ type: 'error', text: '변경할 행을 선택해 주세요.' });
      return;
    }
    if (defectChoice !== '정상' && defectChoice !== '불량') {
      setMessage({ type: 'error', text: '불량을 정상 또는 불량으로 선택해 주세요.' });
      return;
    }
    const memo = editMemo.trim();
    const confirmed = await ask(
      [
        `선택한 ${ids.length}건의 불량을 ${defectChoice}으로 바꿉니다.`,
        memo ? `수정사항메모: ${memo}` : '수정사항메모는 비워 두면 기존 메모를 유지합니다.',
      ].join('\n'),
    );
    if (!confirmed) return;
    savingDefectRef.current = true;
    setSavingDefect(true);
    setMessage(null);
    try {
      const result = await updateReturnInfoDefect(ids, defectChoice, memo);
      setSelected(new Set());
      setEditMemo('');
      setMessage({ type: 'success', text: `${result.updated}건의 불량을 ${defectChoice}으로 바꿨습니다.` });
      setListVersion((current) => current + 1);
    } catch (err) {
      setMessage({ type: 'error', text: errorText(err) });
    } finally {
      savingDefectRef.current = false;
      setSavingDefect(false);
    }
  }

  function rowLabel(row: Record<string, string | number | null>) {
    const number = cellText(row.관리번호);
    if (number !== '-') return number;
    const name = cellText(row.상품명);
    return name !== '-' ? name : '이 행';
  }

  async function removeRow(row: Record<string, string | number | null>) {
    const id = rowId(row);
    if (id === null || savingRowRef.current !== null) return;
    const confirmed = await ask(`${rowLabel(row)} 반품정보를 목록에서 지웁니다.\n로그 분석에서 되돌릴 수 있습니다.`);
    if (!confirmed) return;
    savingRowRef.current = id;
    setSavingRow(id);
    setMessage(null);
    try {
      await deleteReturnInfo(id);
      setSelected((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
      setMessage({ type: 'success', text: `${rowLabel(row)} 행을 지웠습니다. 로그 분석에서 되돌릴 수 있습니다.` });
      setListVersion((current) => current + 1);
    } catch (err) {
      setMessage({ type: 'error', text: errorText(err) });
    } finally {
      savingRowRef.current = null;
      setSavingRow(null);
    }
  }

  function updateDraft(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function search() {
    const next = { ...draft };
    MULTI_COLUMNS.forEach((column) => {
      const picked = (next[column] || '').split('\n').map((part) => part.trim()).filter(Boolean);
      const typed = (choiceQuery[column] || '').trim();
      if (picked.length === 0 && typed) next[column] = typed;
    });
    setPage(1);
    setApplied(next);
    setMessage(null);
  }

  function resetFilters() {
    const cleared = defaultFilters();
    setDraft(cleared);
    setApplied(cleared);
    setChoiceQuery({});
    setPage(1);
    setMessage(null);
  }

  function renderConditionField(column: string) {
    const fieldClass = WIDE_COLUMNS.has(column)
      ? 'return-filter-wide'
      : SHORT_COLUMNS.has(column)
        ? 'return-filter-short'
        : CHOICE_COLUMNS.includes(column as typeof CHOICE_COLUMNS[number])
          ? 'return-filter-choice'
          : undefined;
    if (CHOICE_COLUMNS.includes(column as typeof CHOICE_COLUMNS[number])) {
      const options = choices[column as typeof CHOICE_COLUMNS[number]] || [];
      const multi = MULTI_COLUMNS.includes(column as typeof MULTI_COLUMNS[number]);
      const current = draft[column] || '';
      const selected = multi
        ? current.split('\n').map((part) => part.trim()).filter(Boolean)
        : [];
      const typed = multi ? (choiceQuery[column] || '') : current;
      const needle = typed.trim().toLowerCase();
      const matches = needle
        ? options.filter((option) => option.toLowerCase().includes(needle) && !selected.includes(option))
        : [];
      function addValue(value: string) {
        if (selected.includes(value)) return;
        updateDraft(column, [...selected, value].join('\n'));
        setChoiceQuery((currentQuery) => ({ ...currentQuery, [column]: '' }));
      }
      function removeValue(value: string) {
        updateDraft(column, selected.filter((item) => item !== value).join('\n'));
      }
      return (
        <Field key={column} label={column} className={fieldClass}>
          <div className="return-choice">
            {multi ? (
              <div className="return-choice-field">
                {selected.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className="return-choice-entered"
                    aria-label={`${column} ${value} 빼기`}
                    onClick={() => removeValue(value)}
                  >
                    {value}
                  </button>
                ))}
                <input
                  type="text"
                  aria-label={column}
                  value={typed}
                  placeholder={selected.length ? '이어서 찾기' : '글자 입력'}
                  onChange={(event) => setChoiceQuery((currentQuery) => ({ ...currentQuery, [column]: event.target.value }))}
                />
              </div>
            ) : (
              <input
                type="text"
                aria-label={column}
                list={`return-choice-${column}`}
                value={typed}
                placeholder="글자 입력"
                onChange={(event) => updateDraft(column, event.target.value)}
              />
            )}
            {multi ? null : (
              <datalist id={`return-choice-${column}`}>
                {options.map((value) => (
                  <option key={value} value={value} />
                ))}
              </datalist>
            )}
            {multi && matches.length > 0 ? (
              <div className="return-choice-picked">
                {matches.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className="return-choice-suggest"
                    aria-label={`${column} ${value} 추가`}
                    onClick={() => addValue(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            ) : null}
            {!multi && matches.length === 1 && matches[0] !== typed.trim() ? (
              <button
                type="button"
                className="return-choice-suggest"
                onClick={() => updateDraft(column, matches[0])}
              >
                {matches[0]}
              </button>
            ) : null}
            {!multi && matches.length > 1 ? (
              <select
                aria-label={`${column} 비슷한 값`}
                value={matches.includes(typed.trim()) ? typed.trim() : ''}
                onChange={(event) => updateDraft(column, event.target.value)}
              >
                <option value="">비슷한 값 선택</option>
                {matches.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            ) : null}
          </div>
        </Field>
      );
    }
    return (
      <Field key={column} label={column} className={fieldClass}>
        <input
          type="text"
          aria-label={column}
          value={draft[column] || ''}
          onChange={(event) => updateDraft(column, event.target.value)}
          placeholder="포함 검색"
        />
      </Field>
    );
  }

  return (
    <div>
      <PageHeader title="반품정보 조회" subtitle="재입고 대기 엑셀의 헤더 그대로 찾고 내려받습니다." />

      {message && <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />}

      <ReturnInfoUpload onChanged={() => setListVersion((current) => current + 1)} />

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
            <details className="return-filter-accordion">
              <summary>날짜{dateActive ? ' · 선택됨' : ''}</summary>
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
            </details>
            <details className="return-filter-accordion">
              <summary>조건{conditionActive ? ' · 선택됨' : ''}</summary>
              <div className="return-filter-fields">
                {orderedConditionColumns.filter((column) => SHORT_COLUMNS.has(column)).map((column) => renderConditionField(column))}
              </div>
              <div className="return-filter-fields">
                {orderedConditionColumns.filter((column) => !SHORT_COLUMNS.has(column)).map((column) => renderConditionField(column))}
              </div>
            </details>
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
              <Button
                type="button"
                variant="secondary"
                disabled={reporting}
                onClick={async () => {
                  setReporting(true);
                  setMessage(null);
                  try {
                    await downloadReturnInfoReport(applied);
                    setMessage({ type: 'success', text: '보고서를 저장했습니다.' });
                  } catch (err) {
                    setMessage({ type: 'error', text: err instanceof Error ? err.message : '보고서 생성 실패' });
                  } finally {
                    setReporting(false);
                  }
                }}
              >
                {reporting ? '보고서 만드는 중...' : '보고서 다운로드'}
              </Button>
            </div>
            <p className="caption tw-mb-0 tw-mt-2">
              전체 검색은 모든 칸을 보고, 아래 조건과 함께 쓰면 둘 다 맞는 행만 남습니다. 날짜는 위가 시작, 아래가 종료이고, 등록일은 오늘로 잡혀 있습니다. 비우면 전체 기간입니다. 엑셀과 보고서는 화면 페이지와 관계없이 이 조건의 전체 건을 담습니다.
            </p>
          </Card>

          <div className="tw-mb-2 tw-mt-3 tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2">
            <TableSummary>
              반품정보 {rows.length}/{total}건 · {page}/{totalPages}페이지
            </TableSummary>
            <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2">
              <Button type="button" onClick={() => setCreateOpen(true)}>직접 입력</Button>
              <Link href="/return-info-log" className="btn btn-secondary">로그 분석</Link>
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
          </div>

          {createOpen ? (
            <ReturnInfoCreateModal
              onClose={() => setCreateOpen(false)}
              onSaved={() => {
                setCreateOpen(false);
                setMessage({ type: 'success', text: '반품정보를 추가했습니다. 목록에 수동 입력으로 표시됩니다.' });
                setListVersion((current) => current + 1);
              }}
            />
          ) : null}
          {editRow ? (
            <ReturnInfoEditModal
              row={editRow}
              onClose={() => setEditRow(null)}
              onSaved={(changed) => {
                setEditRow(null);
                setMessage({
                  type: 'success',
                  text: changed ? '상세 내용을 저장했습니다. 로그 분석에서 누가 바꿨는지 볼 수 있습니다.' : '바뀐 내용이 없습니다.',
                });
                if (changed) setListVersion((current) => current + 1);
              }}
            />
          ) : null}

          <Card title="">
            {loading ? (
              <Loading />
            ) : rows.length === 0 ? (
              <p className="caption">조건에 맞는 반품정보가 없습니다.</p>
            ) : (
              <>
              {selectedCount > 0 ? (
                <div className="return-defect-bar">
                  <Field label="불량" className="return-defect-choice">
                    <Select
                      aria-label="변경할 불량"
                      value={defectChoice}
                      onChange={(event) => setDefectChoice(event.target.value as '' | '정상' | '불량')}
                    >
                      <option value="">선택</option>
                      {DEFECT_CHOICES.map((value) => (
                        <option key={value} value={value}>{value}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="수정사항메모" className="return-defect-memo">
                    <input
                      aria-label="수정사항메모 입력"
                      value={editMemo}
                      maxLength={4000}
                      placeholder="선택한 행에 같이 남길 메모"
                      onChange={(event) => setEditMemo(event.target.value)}
                    />
                  </Field>
                  <Button
                    type="button"
                    disabled={savingDefect || defectChoice === ''}
                    onClick={applyDefect}
                  >
                    {savingDefect ? '변경하는 중...' : `선택 ${selectedCount}건 변경`}
                  </Button>
                </div>
              ) : (
                <p className="caption tw-mb-2 tw-mt-0">
                  여러 행은 체크한 뒤 불량만 한 번에 바꿉니다. 주문번호, 바코드, CS이력 등 나머지 항목은 수정에서 봅니다.
                </p>
              )}
              <div className="return-sheet">
                <table>
                  <thead>
                    <tr>
                      <th className="return-col-check">
                        <input
                          ref={pageCheckRef}
                          type="checkbox"
                          className="return-row-check"
                          aria-label="이 페이지 모두 선택"
                          checked={allChecked}
                          disabled={pageIds.length === 0}
                          onChange={(event) => togglePage(event.target.checked)}
                        />
                      </th>
                      <th className="return-col-actions">작업</th>
                      {tableColumns.map((column) => (
                        <th key={column} className={LIST_CLASS[column]}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => {
                      const id = rowId(row);
                      return (
                      <tr key={id ?? `${row.관리번호 ?? ''}-${index}`}>
                        <td className="return-col-check">
                          <input
                            type="checkbox"
                            className="return-row-check"
                            aria-label={cellText(row.상품명) !== '-' ? `${cellText(row.상품명)} 선택` : '이 행 선택'}
                            checked={id !== null && selected.has(id)}
                            disabled={id === null}
                            onChange={() => {
                              if (id !== null) toggleId(id);
                            }}
                          />
                        </td>
                        <td className="return-col-actions">
                          {id === null ? '-' : (
                            <div className="return-row-actions">
                              <Button
                                type="button"
                                variant="secondary"
                                disabled={savingRow === id}
                                aria-label={`${rowLabel(row)} 수정`}
                                onClick={() => setEditRow(row)}
                              >
                                수정
                              </Button>
                              <Button
                                type="button"
                                variant="danger"
                                disabled={savingRow === id}
                                aria-label={`${rowLabel(row)} 삭제`}
                                onClick={() => void removeRow(row)}
                              >
                                삭제
                              </Button>
                            </div>
                          )}
                        </td>
                        {tableColumns.map((column) => (
                          <td
                            key={column}
                            className={LIST_CLASS[column]}
                            title={cellText(row[column])}
                          >
                            {column === '상품명' && row['입력구분'] === '수동 입력' ? (
                              <span className="return-name-line">
                                <span className="return-source-manual">수동</span>
                                <span>{cellText(row[column])}</span>
                              </span>
                            ) : (
                              cellText(row[column])
                            )}
                          </td>
                        ))}
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              </>
            )}

            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
              <Button type="button" variant="ghost" disabled={page <= 1} onClick={() => setPage(1)}>처음</Button>
              <Button type="button" variant="ghost" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>이전</Button>
              <span className="caption" style={{ alignSelf: 'center' }}>{page} / {totalPages}</span>
              <Button type="button" variant="ghost" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>다음</Button>
              <Button type="button" variant="ghost" disabled={page >= totalPages} onClick={() => setPage(totalPages)}>마지막</Button>
            </div>
          </Card>
          {dialog}
    </div>
  );
}
