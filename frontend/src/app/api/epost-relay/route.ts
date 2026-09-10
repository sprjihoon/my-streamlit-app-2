/**
 * 한국우체국 API 중계 라우트 (Seoul ICN 리전에서 실행)
 *
 * 용도 1 — 계약소포 API (ship.epost.go.kr):
 *   Railway 싱가포르 → ship.epost.go.kr 연결 불가 문제 해결용
 *
 * 용도 2 — 공개 종적조회 (service.epost.go.kr):
 *   Railway 싱가포르 → service.epost.go.kr timeout 차단 우회
 *   ICN 리전(서울)에서 직접 호출하므로 국내 IP 제한 통과 가능
 */

import { NextRequest, NextResponse } from 'next/server';

// 서울(ICN) 리전에서 실행 — 우체국 서버는 국내 IP에서만 정상 응답
export const preferredRegion = 'icn1';
export const runtime = 'nodejs';
export const maxDuration = 30;

const RELAY_SECRET = (process.env.EPOST_RELAY_SECRET ?? '').trim();

// 허용 대상 호스트
const ALLOWED_API_HOST     = 'ship.epost.go.kr';
const ALLOWED_TRACE_HOST   = 'service.epost.go.kr';

function isAllowedUrl(url: string, method: string): boolean {
  if (url.includes(ALLOWED_API_HOST)) {
    return url.startsWith(`http://${ALLOWED_API_HOST}`) ||
           url.startsWith(`https://${ALLOWED_API_HOST}`);
  }
  if (url.includes(ALLOWED_TRACE_HOST)) {
    // 종적조회는 GET 전용
    if (method.toUpperCase() !== 'GET') return false;
    return url.startsWith(`http://${ALLOWED_TRACE_HOST}`) ||
           url.startsWith(`https://${ALLOWED_TRACE_HOST}`);
  }
  return false;
}

export async function POST(req: NextRequest) {
  // ── 인증 ──────────────────────────────────────────────────────────────
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
  const fetchMethod = method.toUpperCase();

  if (!url || !isAllowedUrl(url, fetchMethod)) {
    return NextResponse.json({ error: 'Forbidden URL' }, { status: 403 });
  }

  // ── 요청 구성 ─────────────────────────────────────────────────────────
  const isTracing = url.includes(ALLOWED_TRACE_HOST);
  const fetchInit: RequestInit = {
    method: fetchMethod,
    headers: isTracing
      ? {
          'User-Agent': 'Mozilla/5.0 (compatible; epost-relay/1.0)',
          'Accept': 'text/html,application/xhtml+xml',
          'Accept-Language': 'ko-KR,ko;q=0.9',
        }
      : {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': 'Mozilla/5.0 (compatible; epost-relay/1.0)',
          'Host': ALLOWED_API_HOST,
        },
    signal: AbortSignal.timeout(20_000),
    cache: 'no-store',
  };
  if (fetchMethod === 'POST' && form_body) {
    fetchInit.body = form_body;
  }

  // ── 실제 호출 (HTTPS 우선, HTTP fallback) ────────────────────────────
  try {
    let resp: Response | null = null;
    let lastErr = '';
    const protocols = isTracing ? ['https'] : ['https', 'http'];
    for (const base of protocols) {
      const actualUrl = url.startsWith('http')
        ? (base === 'https'
            ? url.replace(/^http:\/\//, 'https://')
            : url.replace(/^https:\/\//, 'http://'))
        : `${base}://${url}`;
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

    // ── 응답 전달 ──────────────────────────────────────────────────────
    // 종적조회 HTML은 EUC-KR 인코딩일 수 있으므로 바이너리 그대로 전달.
    // Python 측에서 직접 디코딩한다.
    if (isTracing) {
      const buffer = await resp.arrayBuffer();
      return new NextResponse(buffer, {
        status: resp.status,
        headers: {
          'Content-Type': resp.headers.get('Content-Type') ?? 'text/html; charset=EUC-KR',
        },
      });
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
