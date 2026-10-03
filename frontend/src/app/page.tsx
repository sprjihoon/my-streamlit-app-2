'use client';

import { useState, useEffect } from 'react';
import Loading from '@/components/Loading';
import Alert from '@/components/Alert';
import PageHeader from '@/components/PageHeader';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Metric } from '@/components/ui/metric';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { checkHealth, getUploadList } from '@/lib/api';

const DATASETS = [
  { key: 'inbound_slip', label: '입고전표' },
  { key: 'shipping_stats', label: '배송통계' },
  { key: 'kpost_in', label: '우체국접수' },
  { key: 'kpost_ret', label: '우체국반품' },
  { key: 'work_log', label: '작업일지' },
];

export default function Dashboard() {
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null);
  const [uploads, setUploads] = useState<Array<{ table_name: string; 원본명: string; 업로드시각: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const healthData = await checkHealth();
        setHealth(healthData);
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

  const tableStats = uploads.reduce((acc, u) => {
    acc[u.table_name] = (acc[u.table_name] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  if (loading) {
    return <Loading text="대시보드 로딩 중..." />;
  }

  return (
    <div>
      <PageHeader
        title="대시보드"
        subtitle="업로드 현황과 바로 이어서 할 작업"
        actions={
          health ? (
            <Badge variant="success">
              <span className="status-dot" />
              {health.status} · v{health.version}
            </Badge>
          ) : (
            <Badge variant="warning">API 연결 없음</Badge>
          )
        }
      />

      {error && <Alert type="error">{error}</Alert>}
      {!health && !error && <Alert type="warning">API 서버에 연결할 수 없습니다.</Alert>}

      <h2 className="section-title">데이터 현황</h2>
      <div className="dashboard-metrics">
        {DATASETS.map((t) => (
          <Metric key={t.key} value={tableStats[t.key] || 0} label={t.label} />
        ))}
      </div>

      <section className="surface">
        <div className="surface-header">
          <h2>최근 업로드</h2>
          <span className="caption">{uploads.length}건</span>
        </div>
        {uploads.length === 0 ? (
          <p className="caption">업로드된 파일이 없습니다.</p>
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
                  <TableCell truncate>{u.원본명 || '-'}</TableCell>
                  <TableCell>{u.업로드시각}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <section className="surface">
        <div className="surface-header">
          <h2>빠른 작업</h2>
          <span className="caption">자주 여는 화면</span>
        </div>
        <div className="flex flex-wrap gap-05">
          <Button variant="primary" asChild><a href="/upload">데이터 업로드</a></Button>
          <Button variant="secondary" asChild><a href="/return-request">회수신청</a></Button>
          <Button variant="secondary" asChild><a href="/overseas-shipping">해외배송</a></Button>
          <Button variant="secondary" asChild><a href="/invoice">인보이스 계산</a></Button>
          <Button variant="ghost" asChild><a href="/invoice-list">인보이스 목록</a></Button>
        </div>
      </section>
    </div>
  );
}
