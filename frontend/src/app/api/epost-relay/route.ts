/**
 * 한국우체국 API 중계 라우트 (Seoul ICN 리전에서 실행)
 * Railway 싱가포르 → ship.epost.go.kr 연결 불가 문제 해결용
 * Railway 백엔드가 이 엔드포인트를 경유해 우체국에 요청을 전달한다.
 */

import { NextRequest, NextResponse } from 'next/server';

// 서울(ICN) 리전에서 실행 — 우체국 API는 국내 IP에서만 응답
export const preferredRegion = 'icn1';
export const runtime = 'nodejs';
// Vercel 기본 10초보다 여유 있게
export const maxDuration = 30;

const ALLOWED_HOST = 'ship.epost.go.kr';
const RELAY_SECRET = (process.env.EPOST_RELAY_SECRET ?? '').trim();

export async function POST(req: NextRequest) {
  // 인증
  const secret = req.headers.get('x-relay-secret') ?? '';
  if (!RELAY_SECRET || secret !== RELAY_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: { method?: string; url?: string; form_body?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const { method = 'POST', url, form_body } = body;

  // ship.epost.go.kr 이외 URL 차단
  if (!url || !url.includes(ALLOWED_HOST)) {
    return NextResponse.json({ error: 'Forbidden URL' }, { status: 403 });
  }
  if (!url.startsWith('http://ship.epost.go.kr') && !url.startsWith('https://ship.epost.go.kr')) {
    return NextResponse.json({ error: 'Forbidden URL' }, { status: 403 });
  }

  const fetchMethod = method.toUpperCase();
  const fetchInit: RequestInit = {
    method: fetchMethod,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': 'Mozilla/5.0 (compatible; epost-relay/1.0)',
      'Host': ALLOWED_HOST,
    },
    signal: AbortSignal.timeout(20_000),
    // Next.js fetch 캐시 사용 안 함
    cache: 'no-store',
  };
  if (fetchMethod === 'POST' && form_body) {
    fetchInit.body = form_body;
  }

  try {
    // HTTPS 먼저, 실패 시 HTTP 재시도
    let resp: Response | null = null;
    let lastErr = '';
    for (const base of ['https', 'http']) {
      const targetUrl = url.startsWith('http') ? url : `${base}://${url}`;
      const actualUrl = base === 'https'
        ? targetUrl.replace(/^http:\/\//, 'https://')
        : targetUrl.replace(/^https:\/\//, 'http://');
      try {
        resp = await fetch(actualUrl, fetchInit);
        break;
      } catch (e) {
        lastErr = String(e);
        resp = null;
      }
    }
    if (!resp) {
      return NextResponse.json(
        { error: `우체국 연결 실패: ${lastErr}` },
        { status: 502 },
      );
    }
    const text = await resp.text();
    return new NextResponse(text, {
      status: resp.status,
      headers: {
        'Content-Type': resp.headers.get('Content-Type') ?? 'text/xml; charset=UTF-8',
      },
    });
  } catch (e) {
    return NextResponse.json({ error: `relay error: ${e}` }, { status: 502 });
  }
}
