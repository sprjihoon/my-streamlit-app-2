'use client';

import { useEffect, useRef, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import {
  RETURN_INFO_COLUMNS,
  RETURN_INFO_DATE_COLUMNS,
  updateReturnInfo,
} from '@/lib/api';

const DATE_COLUMNS = new Set<string>(RETURN_INFO_DATE_COLUMNS);
const WIDE_COLUMNS = new Set(['CS이력', '반품메모', '수정사항메모']);
const EDIT_COLUMNS = [...RETURN_INFO_COLUMNS, '수정사항메모'];
const DEFECT_CHOICES = ['정상', '불량'] as const;

function fieldValue(column: string, value: string | number | null | undefined) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  if (DATE_COLUMNS.has(column)) return text.slice(0, 10);
  return text;
}

function errorText(err: unknown) {
  const raw = err instanceof Error ? err.message : '';
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    if (raw && !raw.startsWith('{')) return raw;
  }
  return '반품정보를 수정하지 못했습니다.';
}

export function ReturnInfoEditModal({
  row,
  onClose,
  onSaved,
}: {
  row: Record<string, string | number | null>;
  onClose: () => void;
  onSaved: (changed: boolean) => void;
}) {
  const [fields, setFields] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    EDIT_COLUMNS.forEach((column) => {
      initial[column] = fieldValue(column, row[column]);
    });
    return initial;
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => {
      dialogRef.current?.querySelector('input, textarea, select')?.focus();
    }, 0);
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !savingRef.current) onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('keydown', onKeyDown);
      previous?.focus();
    };
  }, [onClose]);

  function updateField(column: string, value: string) {
    setFields((current) => ({ ...current, [column]: value }));
  }

  async function save() {
    if (savingRef.current) return;
    const payload: Record<string, string | number | null> = {};
    EDIT_COLUMNS.forEach((column) => {
      const next = (fields[column] || '').trim();
      const previous = fieldValue(column, row[column]).trim();
      if (next === previous) return;
      if (column === '수량') {
        payload[column] = next === '' ? null : Number(next);
        return;
      }
      payload[column] = next === '' ? null : next;
    });
    if (Object.keys(payload).length === 0) {
      onSaved(false);
      return;
    }
    const quantity = (fields['수량'] || '').trim();
    if (quantity && !/^\d+$/.test(quantity)) {
      setError('수량은 0 이상의 정수로 입력해 주세요.');
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const result = await updateReturnInfo(Number(row.id), payload);
      onSaved(result.changed);
    } catch (err) {
      setError(errorText(err));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  const titleName = fieldValue('상품명', row.상품명) || '반품정보';

  return (
    <div
      className="data-modal-backdrop"
      onClick={() => {
        if (!savingRef.current) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="data-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="return-info-edit-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="data-modal-head">
          <h2 id="return-info-edit-title">반품정보 상세 수정</h2>
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving} aria-label="상세 수정 닫기">
            닫기
          </Button>
        </div>
        <div className="data-modal-body">
          <p className="caption tw-mt-0">
            {titleName}의 항목을 각각 고칩니다. 저장하면 바뀐 칸만 반영되고 로그에 남습니다.
          </p>
          {error ? <Alert type="error" message={error} onClose={() => setError(null)} /> : null}
          <div className="return-create-grid">
            {EDIT_COLUMNS.map((column) => (
              <Field
                key={column}
                label={column}
                className={WIDE_COLUMNS.has(column) ? 'return-create-wide' : undefined}
              >
                {column === '불량' ? (
                  <Select
                    aria-label="상세 불량"
                    value={DEFECT_CHOICES.includes(fields[column] as typeof DEFECT_CHOICES[number]) ? fields[column] : ''}
                    onChange={(event) => updateField(column, event.target.value)}
                  >
                    <option value="">{fields[column] && !DEFECT_CHOICES.includes(fields[column] as typeof DEFECT_CHOICES[number]) ? fields[column] : '선택'}</option>
                    {DEFECT_CHOICES.map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </Select>
                ) : WIDE_COLUMNS.has(column) ? (
                  <textarea
                    aria-label={`상세 ${column}`}
                    value={fields[column] || ''}
                    onChange={(event) => updateField(column, event.target.value)}
                  />
                ) : (
                  <input
                    type={DATE_COLUMNS.has(column) ? 'date' : column === '수량' ? 'number' : 'text'}
                    aria-label={`상세 ${column}`}
                    value={fields[column] || ''}
                    min={column === '수량' ? 0 : undefined}
                    step={column === '수량' ? 1 : undefined}
                    autoComplete="off"
                    onChange={(event) => updateField(column, event.target.value)}
                  />
                )}
              </Field>
            ))}
          </div>
        </div>
        <div className="data-modal-foot">
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button type="button" onClick={() => void save()} disabled={saving}>
            {saving ? '저장 중...' : '저장'}
          </Button>
        </div>
      </div>
    </div>
  );
}
