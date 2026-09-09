import { getDefectLogExportUrl } from './api';

/**
 * 서버가 직접 사진 파일을 읽어 엑셀을 만들어 반환한다.
 * 불량일지 전용 — 수선작업일지와 동일한 서버사이드 처리 방식.
 */
export async function downloadDefectLogExcel(params: {
  period_from: string;
  period_to: string;
  vendor?: string;
  defect?: string;
  result?: string;
  author?: string;
}) {
  const url = getDefectLogExportUrl(
    params.period_from,
    params.period_to,
    params.vendor,
    params.defect,
    params.result,
    params.author,
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
  link.download = `defect_log_${params.period_from}_${params.period_to}.xlsx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}
