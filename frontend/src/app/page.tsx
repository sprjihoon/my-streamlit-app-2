'use client';

import { useState, useEffect } from 'react';
import Card from '@/components/Card';
import Loading from '@/components/Loading';
import Alert from '@/components/Alert';
import PageHeader from '@/components/PageHeader';
import { Button } from '@/components/ui/button';
import { Metric } from '@/components/ui/metric';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { checkHealth, getUploadList } from '@/lib/api';

/**
 * 대시보드 페이지 (홈)
 * 기존 대시보드와 동일한 화면 흐름
 */
export default function Dashboard() {
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null);
  const [uploads, setUploads] = useState<Array<{ table_name: string; 원본명: string; 업로드시각: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 초기 데이터 로드
  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        
        // 헬스체크
        const healthData = await checkHealth();
        setHealth(healthData);
        
        // 업로드 목록
        const uploadData = await getUploadList();
        setUploads(uploadData.uploads || []);
        
      } catch (err) {
        setError(err instanceof Error ? err.message : 'API 연결 실패');
      } finally {
        setLoading(false);
      }
    }
    
    loadData();
  }, []);

  // 테이블별 업로드 현황 집계
  const tableStats = uploads.reduce((acc, u) => {
    acc[u.table_name] = (acc[u.table_name] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  if (loading) {
    return <Loading text="대시보드 로딩 중..." />;
  }

  return (
    <div>
      <PageHeader title="대시보드" subtitle="시스템 현황 및 빠른 작업" />

      {error && <Alert type="error">{error}</Alert>}

      {/* API 상태 */}
      <Card title="API 상태">
        {health ? (
          <div className="flex gap-1">
            <Metric
              value="●"
              label={`상태: ${health.status}`}
              valueClassName="!tw-text-[1.2rem] !tw-text-tillion-success"
            />
            <Metric value={health.version} label="버전" />
          </div>
        ) : (
          <Alert type="warning">API 서버에 연결할 수 없습니다.</Alert>
        )}
      </Card>

      {/* 데이터 현황 */}
      <Card title="데이터 현황">
        <div className="grid grid-5">
          {[
            { key: 'inbound_slip', label: '입고전표' },
            { key: 'shipping_stats', label: '배송통계' },
            { key: 'kpost_in', label: '우체국접수' },
            { key: 'kpost_ret', label: '우체국반품' },
            { key: 'work_log', label: '작업일지' },
          ].map((t) => (
            <Metric key={t.key} value={tableStats[t.key] || 0} label={t.label} />
          ))}
        </div>
      </Card>

      {/* 최근 업로드 */}
      <Card title="최근 업로드">
        {uploads.length === 0 ? (
          <p className="text-muted">업로드된 파일이 없습니다.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>테이블</TableHead>
                <TableHead>파일명</TableHead>
                <TableHead>업로드 시각</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {uploads.slice(0, 5).map((u, i) => (
                <TableRow key={i}>
                  <TableCell>{u.table_name}</TableCell>
                  <TableCell>{u.원본명 || '-'}</TableCell>
                  <TableCell>{u.업로드시각}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* 빠른 링크 */}
      <Card title="빠른 작업">
        <div className="flex gap-1">
          <Button variant="primary" asChild><a href="/upload">데이터 업로드</a></Button>
          <Button variant="secondary" asChild><a href="/return-request">회수신청</a></Button>
          <Button variant="secondary" asChild><a href="/overseas-shipping">해외배송</a></Button>
          <Button variant="success" asChild><a href="/invoice">인보이스 계산</a></Button>
          <Button variant="secondary" asChild><a href="/invoice-list">인보이스 목록</a></Button>
        </div>
      </Card>
    </div>
  );
}

