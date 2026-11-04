'use client';

import { useEffect, useRef, useState } from 'react';
import { Alert } from '@/components/Alert';
import { getUploadList, resetTableData, resetTableDataByPeriod, uploadFile } from '@/lib/api';

export function ReturnInfoUpload({ onChanged }: { onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [uploadCount, setUploadCount] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [periodResetting, setPeriodResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    setIsAdmin(localStorage.getItem('isAdmin') === 'true');
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    getUploadList()
      .then((data) => {
        if (cancelled) return;
        const count = (data.uploads || []).filter((row) => row.table_name === 'return_info').length;
        setUploadCount(count);
      })
      .catch(() => {
        if (!cancelled) setUploadCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin, message]);

  if (!isAdmin) return null;

  async function handleUpload(file: File) {
    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
      setMessage({ type: 'error', text: `파일 크기가 너무 큽니다. 최대 100MB까지 업로드 가능합니다. (현재: ${(file.size / 1024 / 1024).toFixed(2)}MB)` });
      return;
    }
    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.xlsx') && !fileName.endsWith('.xls')) {
      setMessage({ type: 'error', text: '엑셀 파일(.xlsx, .xls)만 업로드 가능합니다.' });
      return;
    }
    setUploading(true);
    setMessage(null);
    try {
      const token = localStorage.getItem('token');
      const result = await uploadFile(file, 'return_info', token || undefined);
      if (result.success) {
        setMessage({
          type: result.message.includes('중복') ? 'warning' : 'success',
          text: result.message,
        });
        onChanged();
      } else {
        setMessage({ type: 'error', text: result.message || '업로드 실패' });
      }
    } catch (err) {
      let errorMessage = err instanceof Error ? err.message : '업로드 실패';
      if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
        errorMessage = '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.';
      }
      setMessage({ type: 'error', text: errorMessage });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleReset() {
    setResetting(true);
    setMessage(null);
    try {
      const result = await resetTableData('return_info');
      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        setConfirmReset(false);
        onChanged();
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '초기화 실패' });
    } finally {
      setResetting(false);
    }
  }

  async function handlePeriodReset() {
    if (!dateFrom || !dateTo) {
      setMessage({ type: 'error', text: '시작일과 종료일을 모두 입력해주세요.' });
      return;
    }
    if (dateFrom > dateTo) {
      setMessage({ type: 'error', text: '시작일이 종료일보다 늦을 수 없습니다.' });
      return;
    }
    if (!confirm(`⚠️ [반품정보] ${dateFrom} ~ ${dateTo} 기간의 데이터를 삭제하시겠습니까?\n\n등록일 기준이며, 이 작업은 되돌릴 수 없습니다.`)) return;
    if (!confirm(`정말로 [반품정보] ${dateFrom} ~ ${dateTo} 구간 데이터를 삭제하시겠습니까?`)) return;
    setPeriodResetting(true);
    setMessage(null);
    try {
      const result = await resetTableDataByPeriod('return_info', dateFrom, dateTo);
      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        onChanged();
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '삭제 실패' });
    } finally {
      setPeriodResetting(false);
    }
  }

  return (
    <details className="return-filter-accordion">
      <summary>반품정보 업로드</summary>
      <div className="return-upload-body">
      {message && <Alert type={message.type} message={message.text} onClose={() => setMessage(null)} />}
      <div className="file-upload" onClick={() => fileRef.current?.click()}>
        <input
          type="file"
          accept=".xlsx,.xls"
          aria-label="반품정보 엑셀"
          ref={fileRef}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleUpload(file);
          }}
        />
        {uploading ? (
          <span>업로드 중...</span>
        ) : (
          <>
            <div>엑셀 파일 선택</div>
            <small className="text-muted">.xlsx, .xls</small>
          </>
        )}
      </div>
      <p className="text-muted" style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>
        재입고 대기 엑셀입니다. 기간 삭제는 등록일 기준이고, 모든 칸이 같은 행은 다시 올리지 않습니다.
      </p>
      <div className="metric" style={{ marginTop: '0.5rem' }}>
        <div className="metric-value">{uploadCount}</div>
        <div className="metric-label">업로드 수</div>
      </div>
      {uploadCount > 0 && (
        <button
          type="button"
          onClick={() => setConfirmReset(true)}
          style={{
            marginTop: '0.5rem',
            padding: '0.25rem 0.5rem',
            fontSize: '0.75rem',
            backgroundColor: '#ff5722',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            width: '100%',
          }}
        >
          데이터 초기화
        </button>
      )}
      {confirmReset && (
        <div role="alertdialog" aria-label="데이터 초기화 확인" style={{ marginTop: '0.5rem' }}>
          <Alert type="warning" message="반품정보 데이터를 모두 삭제합니다. 이 작업은 되돌릴 수 없습니다." />
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setConfirmReset(false)}
              disabled={resetting}
              style={{
                flex: 1,
                padding: '0.4rem 0.5rem',
                fontSize: '0.8rem',
                backgroundColor: '#e5e7eb',
                color: '#111827',
                border: 'none',
                borderRadius: '4px',
                cursor: resetting ? 'not-allowed' : 'pointer',
              }}
            >
              취소
            </button>
            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={resetting}
              style={{
                flex: 1,
                padding: '0.4rem 0.5rem',
                fontSize: '0.8rem',
                backgroundColor: resetting ? '#ccc' : '#e53935',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: resetting ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              {resetting ? '삭제 중...' : '삭제 확인'}
            </button>
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end', marginTop: '0.85rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>등록일 시작</label>
          <input type="date" aria-label="반품정보 삭제 시작일" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>등록일 종료</label>
          <input type="date" aria-label="반품정보 삭제 종료일" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
        <button
          type="button"
          onClick={() => void handlePeriodReset()}
          disabled={periodResetting || !dateFrom || !dateTo}
          style={{
            padding: '0.45rem 1rem',
            backgroundColor: periodResetting || !dateFrom || !dateTo ? '#ccc' : '#e53935',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: periodResetting || !dateFrom || !dateTo ? 'not-allowed' : 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
          }}
        >
          {periodResetting ? '삭제 중...' : '기간 데이터 삭제'}
        </button>
      </div>
      <p style={{ marginTop: '0.5rem', marginBottom: 0, fontSize: '0.78rem', color: '#666' }}>
        * 반품정보는 등록일 기준으로 삭제됩니다.
      </p>
      </div>
    </details>
  );
}
