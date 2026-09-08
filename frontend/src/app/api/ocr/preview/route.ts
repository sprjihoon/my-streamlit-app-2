/**
 * OCR 미리보기 프록시 (Vercel 서버 → Railway)
 * 브라우저 ↔ Vercel (동일 출처, 가까운 엣지)
 * Vercel  ↔ Railway (서버 간, TCP 안정적)
 */
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 120; // 2분 (GPT-4o 처리 여유)

const RAILWAY = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').trim();

export async function POST(req: NextRequest) {
  const auth = req.headers.get('authorization') ?? '';

  // 브라우저에서 받은 multipart 그대로 Railway에 전달
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: 'multipart 파싱 실패' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${RAILWAY}/inbound/ocr-preview`, {
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
