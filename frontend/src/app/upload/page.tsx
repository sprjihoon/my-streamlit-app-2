'use client';

import { useState, useEffect, useRef } from 'react';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import Alert from '@/components/Alert';
import { uploadFile, getUploadList, deleteUpload } from '@/lib/api';

/**
 * 업로드 타겟 정의 (Streamlit TARGETS와 동일)
 */
const TARGETS = [
  { key: 'inbound_slip', label: '입고전표' },
  { key: 'shipping_stats', label: '배송통계' },
  { key: 'kpost_in', label: '우체국접수' },
  { key: 'kpost_ret', label: '우체국반품' },
  { key: 'work_log', label: '작업일지' },
];

interface UploadRecord {
  id: number;
  filename: string;
  원본명: string;
  table_name: string;
  시작일: string;
  종료일: string;
  업로드시각: string;
}

/**
 * 데이터 업로드 페이지
 * Streamlit 1_upload_manager.py와 동일한 화면 흐름
 */
export default function UploadPage() {
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  
  // 파일 input refs
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({});

  // 업로드 목록 로드
  async function loadUploads() {
    try {
      const data = await getUploadList();
      setUploads(data.uploads || []);
    } catch {
      setMessage({ type: 'error', text: 'API 연결 실패' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUploads();
  }, []);

  // 파일 업로드 처리
  async function handleUpload(table: string, file: File) {
    setUploading(table);
    setMessage(null);
    
    try {
      const result = await uploadFile(file, table);
      
      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        await loadUploads(); // 목록 새로고침
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '업로드 실패' });
    } finally {
      setUploading(null);
      // 파일 input 초기화
      if (fileRefs.current[table]) {
        fileRefs.current[table]!.value = '';
      }
    }
  }

  // 업로드 삭제
  async function handleDelete(id: number) {
    if (!confirm('이 업로드 기록을 삭제하시겠습니까?')) return;
    
    try {
      const result = await deleteUpload(id);
      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        await loadUploads();
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '삭제 실패' });
    }
  }

  // 테이블별 업로드 수
  const tableStats = uploads.reduce((acc, u) => {
    acc[u.table_name] = (acc[u.table_name] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  if (loading) {
    return <Loading text="업로드 목록 로딩 중..." />;
  }

  return (
    <div>
      <h1 style={{ marginBottom: '1rem' }}>📤 원본 데이터 업로드</h1>

      {message && <Alert type={message.type}>{message.text}</Alert>}

      {/* 업로드 영역 (5컬럼 그리드 - Streamlit cols와 동일) */}
      <div className="grid grid-5" style={{ marginBottom: '1rem' }}>
        {TARGETS.map((target) => (
          <Card key={target.key} title={target.label}>
            {/* 파일 업로드 */}
            <div
              className="file-upload"
              onClick={() => fileRefs.current[target.key]?.click()}
            >
              <input
                type="file"
                accept=".xlsx"
                ref={(el) => { fileRefs.current[target.key] = el; }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleUpload(target.key, file);
                }}
              />
              {uploading === target.key ? (
                <span>업로드 중...</span>
              ) : (
                <>
                  <div>📁 엑셀 파일 선택</div>
                  <small className="text-muted">.xlsx</small>
                </>
              )}
            </div>

            {/* 통계 */}
            <div className="metric" style={{ marginTop: '0.5rem' }}>
              <div className="metric-value">{tableStats[target.key] || 0}</div>
              <div className="metric-label">업로드 수</div>
            </div>
          </Card>
        ))}
      </div>

      {/* 업로드 이력 */}
      <Card title="📊 업로드 이력">
        {uploads.length === 0 ? (
          <p className="text-muted">업로드된 파일이 없습니다.</p>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>테이블</th>
                  <th>파일명</th>
                  <th>시작일</th>
                  <th>종료일</th>
                  <th>업로드 시각</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((u) => (
                  <tr key={u.id}>
                    <td>{u.table_name}</td>
                    <td>{u.원본명 || u.filename}</td>
                    <td>{u.시작일 || '-'}</td>
                    <td>{u.종료일 || '-'}</td>
                    <td>{u.업로드시각}</td>
                    <td>
                      <button
                        className="btn btn-danger"
                        onClick={() => handleDelete(u.id)}
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                      >
                        🗑️
                      </button>
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

