import { getWorkLogExportUrl } from './api';

/**
 * 서버가 검색 조건으로 엑셀을 만들어 반환한다.
 * 수선작업일지 엑셀 다운로드와 같은 방식이다.
 */
export async function downloadWorkLogExcel(params: {
  period_from: string;
  period_to: string;
  vendor?: string;
  work_type?: string;
  author?: string;
  source?: string;
}) {
  const url = getWorkLogExportUrl(
    params.period_from,
    params.period_to,
    params.vendor,
    params.work_type,
    params.author,
    params.source,
  );

  const res = await fetch(url);
  if (!res.ok) {
    let detail = '엑셀 생성 실패';
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  const buffer = await res.arrayBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = `work_log_${params.period_from}_${params.period_to}.xlsx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}
