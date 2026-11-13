'use client';

import { useEffect, useRef, useState } from 'react';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import {
  RETURN_INFO_COLUMNS,
  RETURN_INFO_DATE_COLUMNS,
  createReturnInfo,
} from '@/lib/api';

const DATE_COLUMNS = new Set<string>(RETURN_INFO_DATE_COLUMNS);
const MEMO_COLUMN = '수정사항메모';
const FORM_COLUMNS = RETURN_INFO_COLUMNS.flatMap((column) => (
  column === '반품메모' ? [column, MEMO_COLUMN] : [column]
));
const WIDE_COLUMNS = new Set(['CS이력', '반품메모', MEMO_COLUMN]);
const CONTENT_COLUMNS = FORM_COLUMNS.filter((column) => column !== '등록일' && column !== '등록자');

function todayValue() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

function authorName() {
  if (typeof window === 'undefined') return '';
  try {
    const user = JSON.parse(localStorage.getItem('user') || 'null');
    return typeof user?.nickname === 'string' ? user.nickname : '';
  } catch {
    return '';
  }
}

function blankFields() {
  const fields: Record<string, string> = {};
  FORM_COLUMNS.forEach((column) => {
    fields[column] = '';
  });
  fields['등록일'] = todayValue();
  fields['등록자'] = authorName();
  return fields;
}

function errorText(err: unknown) {
  const raw = err instanceof Error ? err.message : '';
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    if (raw && !raw.startsWith('{')) return raw;
  }
  return '반품정보를 저장하지 못했습니다.';
}

export function ReturnInfoCreateModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [fields, setFields] = useState(blankFields);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => {
      dialogRef.current?.querySelector('input, textarea')?.focus();
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
    const registered = (fields['등록일'] || '').trim();
    if (!registered) {
      setError('등록일을 입력해 주세요.');
      return;
    }
    const hasContent = CONTENT_COLUMNS.some((column) => (fields[column] || '').trim() !== '');
    if (!hasContent) {
      setError('등록일 외에 내용을 하나 이상 입력해 주세요.');
      return;
    }
    const quantity = (fields['수량'] || '').trim();
    if (quantity && !/^\d+$/.test(quantity)) {
      setError('수량은 0 이상의 정수로 입력해 주세요.');
      return;
    }
    const payload: Record<string, string | number | null> = {};
    FORM_COLUMNS.forEach((column) => {
      const value = (fields[column] || '').trim();
      if (column === '수량') {
        payload[column] = value === '' ? null : Number(value);
        return;
      }
      payload[column] = value === '' ? null : value;
    });
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      await createReturnInfo(payload);
      onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

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
        aria-labelledby="return-info-create-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="data-modal-head">
          <h2 id="return-info-create-title">반품정보 직접 입력</h2>
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving} aria-label="직접 입력 닫기">
            닫기
          </Button>
        </div>
        <div className="data-modal-body">
          <p className="caption tw-mt-0">
            엑셀과 같은 항목을 한 건 저장합니다. 등록일은 필수이고, 저장한 행은 목록에 수동 입력으로 표시됩니다.
          </p>
          {error ? <Alert type="error" message={error} onClose={() => setError(null)} /> : null}
          <div className="return-create-grid">
            {FORM_COLUMNS.map((column) => (
              <Field
                key={column}
                label={column}
                required={column === '등록일'}
                className={WIDE_COLUMNS.has(column) ? 'return-create-wide' : undefined}
              >
                {WIDE_COLUMNS.has(column) ? (
                  <textarea
                    aria-label={`직접입력 ${column}`}
                    value={fields[column] || ''}
                    onChange={(event) => updateField(column, event.target.value)}
                  />
                ) : (
                  <input
                    type={DATE_COLUMNS.has(column) ? 'date' : column === '수량' ? 'number' : 'text'}
                    aria-label={`직접입력 ${column}`}
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
