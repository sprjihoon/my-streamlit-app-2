/**
 * 입고 배치 OCR 프록시 (Vercel 서버 → Railway)
 * 브라우저 ↔ Vercel (동일 출처, 가까운 엣지)
 * Vercel  ↔ Railway (서버 간, TCP 안정적)
 */
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 120; // 2분 (GPT-4o 처리 여유)

const RAILWAY = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').trim();

export async function POST(
  req: NextRequest,
  { params }: { params: { batchId: string } }
) {
  const { batchId } = params;
  const auth = req.headers.get('authorization') ?? '';

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: 'multipart 파싱 실패' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${RAILWAY}/inbound/batches/${batchId}/ocr`, {
      method: 'POST',
      headers: { authorization: auth },
      body: formData,
      // @ts-expect-error Next.js fetch duplex 옵션
      duplex: 'half',
    });
    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  } catch (e) {
    return NextResponse.json({ error: `Railway 연결 실패: ${e}` }, { status: 502 });
  }
}
