import type { RepairLog } from './api';
import { getRepairLogs, repairImageUrl } from './api';

const TEXT_HEADERS = ['날짜', '업체명', '제품명', '옵션', '바코드', '불량명', '작업', '수량', '비용', '비고', '작성자'];
const EXCEL_LOG_LIMIT = 400;

function workPhotoNames(log: RepairLog): string[] {
  return [
    log.before_image,
    log.after_image,
    ...(log.extra_images || []),
  ].filter((name): name is string => !!name);
}

function imageExtension(name: string, contentType: string): 'jpeg' | 'png' | 'gif' {
  const lower = `${name} ${contentType}`.toLowerCase();
  if (lower.includes('png')) return 'png';
  if (lower.includes('gif')) return 'gif';
  return 'jpeg';
}

async function fetchPhoto(name: string): Promise<{ buffer: ArrayBuffer; extension: 'jpeg' | 'png' | 'gif' } | null> {
  const url = repairImageUrl(name);
  if (!url) return null;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const buffer = await res.arrayBuffer();
    if (buffer.byteLength < 32) return null;
    return { buffer, extension: imageExtension(name, res.headers.get('content-type') || '') };
  } catch {
    return null;
  }
}

export async function downloadRepairLogExcel(params: {
  period_from: string;
  period_to: string;
  vendor?: string;
  work_type?: string;
  defect?: string;
  author?: string;
}) {
  const list = await getRepairLogs({ ...params, limit: EXCEL_LOG_LIMIT, offset: 0 });
  if (!list.logs.length) {
    throw new Error('해당 조건의 수선일지가 없습니다.');
  }
  if (list.total > EXCEL_LOG_LIMIT) {
    throw new Error(
      `사진 포함 엑셀은 한 번에 ${EXCEL_LOG_LIMIT}건까지입니다. 업체나 기간을 더 좁혀 주세요. (현재 ${list.total}건)`
    );
  }

  const ExcelJS = (await import('exceljs')).default;
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('수선일지');
  const maxPhotos = Math.max(1, ...list.logs.map((log) => workPhotoNames(log).length));
  const photoHeaders = Array.from({ length: maxPhotos }, (_, i) => `사진${i + 1}`);

  ws.columns = [
    ...TEXT_HEADERS.map((header, i) => ({
      header,
      key: header,
      width: [12, 16, 18, 12, 16, 12, 12, 8, 12, 16, 10][i],
    })),
    ...photoHeaders.map((header) => ({ header, key: header, width: 14 })),
  ];
  const headerRow = ws.getRow(1);
  headerRow.font = { bold: true, color: { argb: 'FFFFFFFF' } };
  headerRow.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1E3A5F' } };
  headerRow.alignment = { vertical: 'middle', horizontal: 'center' };
  headerRow.height = 22;

  for (let i = 0; i < list.logs.length; i++) {
    const log = list.logs[i];
    const row = ws.addRow(TEXT_HEADERS.map((key) => log[key as keyof RepairLog] ?? ''));
    const names = workPhotoNames(log);
    row.height = names.length ? 68 : 18;
    row.alignment = { vertical: 'middle', wrapText: true };
    const photos = await Promise.all(names.map(fetchPhoto));
    photos.forEach((photo, photoIndex) => {
      if (!photo) return;
      const bytes = new Uint8Array(photo.buffer);
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
      }
      const imageId = wb.addImage({
        base64: btoa(binary),
        extension: photo.extension,
      });
      ws.addImage(imageId, {
        tl: { col: TEXT_HEADERS.length + photoIndex, row: i + 1 },
        ext: { width: 84, height: 84 },
        editAs: 'oneCell',
      });
    });
  }

  const summary = wb.addWorksheet('업체별 요약');
  summary.columns = [
    { header: '업체명', key: '업체명', width: 18 },
    { header: '건수', key: '건수', width: 10 },
    { header: '수량', key: '수량', width: 10 },
    { header: '금액', key: '금액', width: 14 },
  ];
  const grouped = new Map<string, { count: number; qty: number; amount: number }>();
  for (const log of list.logs) {
    const name = (log.업체명 || '미지정').trim() || '미지정';
    const cur = grouped.get(name) || { count: 0, qty: 0, amount: 0 };
    cur.count += 1;
    cur.qty += Number(log.수량 || 0);
    cur.amount += Number(log.비용 || 0);
    grouped.set(name, cur);
  }
  for (const [name, cur] of grouped) {
    summary.addRow({ 업체명: name, 건수: cur.count, 수량: cur.qty, 금액: cur.amount });
  }

  const buffer = await wb.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = `repair_log_${params.period_from}_${params.period_to}.xlsx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}
