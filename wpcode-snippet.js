/**
 * WPCode 스니펫 - spring3pl.co.kr WordPress 방문자 추적
 * ──────────────────────────────────────────────────────
 * WPCode 플러그인에서 "Header" 위치에 JavaScript 타입으로 붙여넣으세요.
 * API_BASE 값을 실제 배포된 API 주소로 변경하세요.
 */
(function () {
  'use strict';

  var API_BASE = 'https://my-streamlit-app-2-production.up.railway.app';

  // ── 세션 ID 생성/유지 ──────────────────────────────────
  function getOrCreateSessionId() {
    var key = 'wp_session_id';
    var id = sessionStorage.getItem(key);
    if (!id) {
      id = 'wp_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
      sessionStorage.setItem(key, id);
    }
    return id;
  }

  var sessionId = getOrCreateSessionId();
  var pageEnteredAt = Date.now();
  var scrollDepth = 0;
  var milestone10s = false;
  var milestone30s = false;
  var visitLogged = false;

  // ── sendBeacon 폴백 헬퍼 ──────────────────────────────
  function sendData(url, payload) {
    var json = JSON.stringify(payload);
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, json);
        return;
      }
    } catch (e) {}
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(json);
    } catch (e) {}
  }

  // ── 체류시간 하트비트 ─────────────────────────────────
  function sendHeartbeat() {
    var elapsed = Math.floor((Date.now() - pageEnteredAt) / 1000);
    if (elapsed <= 0) return;
    sendData(API_BASE + '/estimate-analytics/heartbeat', {
      session_id: sessionId,
      duration_seconds: elapsed,
    });
  }

  // ── 인게이지먼트 전송 ─────────────────────────────────
  function sendEngagement() {
    sendData(API_BASE + '/estimate-analytics/engagement', {
      session_id: sessionId,
      scroll_depth: scrollDepth,
      milestone_10s: milestone10s,
      milestone_30s: milestone30s,
    });
  }

  // ── 스크롤 깊이 추적 ─────────────────────────────────
  function onScroll() {
    var el = document.documentElement;
    var scrolled = (el.scrollTop || document.body.scrollTop) + el.clientHeight;
    var total = el.scrollHeight;
    if (total <= 0) return;
    var depth = Math.round((scrolled / total) * 100);
    if (depth > scrollDepth) scrollDepth = Math.min(depth, 100);
  }
  window.addEventListener('scroll', onScroll, { passive: true });

  // ── 10초 / 30초 마일스톤 ─────────────────────────────
  setTimeout(function () { milestone10s = true; }, 10000);
  setTimeout(function () { milestone30s = true; }, 30000);

  // ── 30초마다 하트비트 ─────────────────────────────────
  setInterval(sendHeartbeat, 30000);

  // ── 페이지 이탈 시 전송 ───────────────────────────────
  window.addEventListener('beforeunload', function () {
    sendHeartbeat();
    sendEngagement();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      sendHeartbeat();
      sendEngagement();
    }
  });

  // ── 방문 로그 전송 ─────────────────────────────────────
  function logVisit() {
    if (visitLogged) return;
    visitLogged = true;

    var urlParams = new URLSearchParams(window.location.search);
    var isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    var isMobile = isTouchDevice && window.innerWidth < 768;

    var payload = {
      page_url: window.location.href,
      referrer: document.referrer || null,
      user_agent: navigator.userAgent,
      screen_width: window.screen.width,
      screen_height: window.screen.height,
      language: navigator.language,
      timezone: (Intl && Intl.DateTimeFormat
        ? Intl.DateTimeFormat().resolvedOptions().timeZone
        : 'Asia/Seoul'),
      platform: navigator.platform || null,
      vendor: navigator.vendor || null,
      session_id: sessionId,
      is_touch_device: isTouchDevice,
      is_mobile: isMobile,
      inner_width: window.innerWidth,
      inner_height: window.innerHeight,
      utm_source: urlParams.get('utm_source'),
      utm_medium: urlParams.get('utm_medium'),
      utm_campaign: urlParams.get('utm_campaign'),
      utm_content: urlParams.get('utm_content'),
      utm_term: urlParams.get('utm_term'),
    };

    try {
      fetch(API_BASE + '/estimate-analytics/visit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      });
    } catch (e) {}
  }

  // DOM 준비 후 실행
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', logVisit);
  } else {
    logVisit();
  }
})();
