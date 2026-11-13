'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import PageHeader from '@/components/ui/page-header';
import { Card } from '@/components/Card';
import { Loading } from '@/components/Loading';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { useYesNo } from '@/components/YesNoDialog';
import {
  getReturnInfoLogs,
  restoreReturnInfoLog,
  type ReturnInfoLogEntry,
} from '@/lib/api';

const ACTIONS = [
  { value: '', label: '전체' },
  { value: 'create', label: '추가' },
  { value: 'update', label: '수정' },
  { value: 'delete', label: '삭제' },
  { value: 'restore', label: '복구' },
] as const;

const SUMMARY = [
  { key: 'update', label: '수정' },
  { key: 'delete', label: '삭제' },
  { key: 'restore', label: '복구' },
  { key: 'create', label: '추가' },
] as const;

function errorText(err: unknown) {
  const raw = err instanceof Error ? err.message : '';
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    if (raw && !raw.startsWith('{')) return raw;
  }
  return '로그를 불러오지 못했습니다.';
}

function showValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '비움';
  const text = String(value);
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

function changeText(entry: ReturnInfoLogEntry) {
  if (!entry.changes?.length) return '-';
  return entry.changes
    .map((change) => `${change.field}: ${showValue(change.before)} → ${showValue(change.after)}`)
    .join('\n');
}

export default function ReturnInfoLogPage() {
  const [draft, setDraft] = useState({ action: '', actor: '', q: '', date_from: '', date_to: '' });
  const [applied, setApplied] = useState(draft);
  const [rows, setRows] = useState<ReturnInfoLogEntry[]>([]);
  const [summary, setSummary] = useState({ create: 0, update: 0, delete: 0, restore: 0 });
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [restoringId, setRestoringId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [version, setVersion] = useState(0);
  const { ask, dialog } = useYesNo();
  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getReturnInfoLogs(applied, page, pageSize)
      .then((data) => {
        if (cancelled) return;
        setRows(Array.isArray(data.rows) ? data.rows : []);
        setTotal(data.total || 0);
        setSummary({
          create: data.summary?.create || 0,
          update: data.summary?.update || 0,
          delete: data.summary?.delete || 0,
          restore: data.summary?.restore || 0,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        setTotal(0);
        setMessage({ type: 'error', text: errorText(err) });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, page, version]);

  async function restore(entry: ReturnInfoLogEntry) {
    if (restoringId !== null) return;
    const confirmed = await ask(`${entry.summary || '삭제한 반품정보'}를 목록으로 되돌립니다.`);
    if (!confirmed) return;
    setRestoringId(entry.id);
    setMessage(null);
    try {
      await restoreReturnInfoLog(entry.id);
      setMessage({ type: 'success', text: '삭제한 반품정보를 목록으로 되돌렸습니다.' });
      setVersion((current) => current + 1);
    } catch (err) {
      setMessage({ type: 'error', text: errorText(err) });
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="반품정보 조회 로그 분석"
        subtitle="누가 반품정보를 추가하고, 고치고, 지웠는지 보고 삭제한 행을 되돌립니다."
      />
      {message ? <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} /> : null}
      <div className="tw-mb-3">
        <Link href="/return-info" className="btn btn-ghost">반품정보 조회로</Link>
      </div>
      <div className="data-kpis">
        {SUMMARY.map((item) => (
          <Card key={item.key} title={item.label}>
            <strong>{summary[item.key]}</strong>
            <span className="data-kpi-hint">현재 조건</span>
          </Card>
        ))}
      </div>
      <Card title="로그 조건">
        <div className="data-filter">
          <div className="data-filter-fields">
            <Field label="작업">
              <Select
                aria-label="작업 종류"
                value={draft.action}
                onChange={(event) => setDraft((current) => ({ ...current, action: event.target.value }))}
              >
                {ACTIONS.map((item) => (
                  <option key={item.value || 'all'} value={item.value}>{item.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="작업자">
              <input
                aria-label="작업자"
                value={draft.actor}
                maxLength={50}
                onChange={(event) => setDraft((current) => ({ ...current, actor: event.target.value }))}
              />
            </Field>
            <Field label="기간 시작">
              <input
                type="date"
                aria-label="로그 시작일"
                value={draft.date_from}
                onChange={(event) => setDraft((current) => ({ ...current, date_from: event.target.value }))}
              />
            </Field>
            <Field label="기간 종료">
              <input
                type="date"
                aria-label="로그 종료일"
                value={draft.date_to}
                onChange={(event) => setDraft((current) => ({ ...current, date_to: event.target.value }))}
              />
            </Field>
            <Field label="내용 검색">
              <input
                aria-label="로그 검색"
                value={draft.q}
                maxLength={100}
                onChange={(event) => setDraft((current) => ({ ...current, q: event.target.value }))}
              />
            </Field>
          </div>
          <div className="data-filter-actions">
            <Button
              type="button"
              onClick={() => {
                setPage(1);
                setApplied(draft);
                setMessage(null);
              }}
            >
              검색
            </Button>
          </div>
        </div>
      </Card>
      <Card title="">
        {loading ? (
          <Loading />
        ) : rows.length === 0 ? (
          <p className="caption">조건에 맞는 작업 로그가 없습니다.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>시각</th>
                  <th>작업자</th>
                  <th>작업</th>
                  <th>대상</th>
                  <th>변경 내용</th>
                  <th>되돌리기</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.created_at || '-'}</td>
                    <td>{entry.actor_name || '-'}</td>
                    <td>{entry.action_label || entry.action}</td>
                    <td>{entry.summary || '-'}</td>
                    <td className="cell-memo">
                      <p className="return-log-changes">{changeText(entry)}</p>
                    </td>
                    <td>
                      {entry.can_restore ? (
                        <Button
                          type="button"
                          variant="secondary"
                          disabled={restoringId === entry.id}
                          aria-label={`${entry.summary || '삭제'} 되돌리기`}
                          onClick={() => void restore(entry)}
                        >
                          {restoringId === entry.id ? '되돌리는 중...' : '되돌리기'}
                        </Button>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
          <Button type="button" variant="ghost" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>이전</Button>
          <span className="caption" style={{ alignSelf: 'center' }}>{page} / {totalPages}</span>
          <Button type="button" variant="ghost" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>다음</Button>
        </div>
      </Card>
      {dialog}
    </div>
  );
}
