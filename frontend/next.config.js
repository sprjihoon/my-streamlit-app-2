/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  
  // Standalone 빌드: Docker(Railway)용. Vercel은 자체 서빙 방식을 사용하므로 제외
  ...(process.env.VERCEL ? {} : { output: 'standalone' }),
  
  // 환경변수
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  
  // 이미지 최적화 (필요시)
  images: {
    unoptimized: true,  // 정적 export 시 필요
  },
  
  // 개발환경 프록시 (CORS 우회용)
  async rewrites() {
    // 프로덕션에서는 프록시 불필요 (직접 API 호출)
    if (process.env.NODE_ENV === 'production') {
      return [];
    }
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ];
  },
  
  // 보안 헤더
  async headers() {
    return [
      {
        // 견적서 페이지는 iframe 허용 (워드프레스 등 외부 삽입용)
        source: '/estimate',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: 'frame-ancestors *',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin',
          },
        ],
      },
      {
        // 그 외 페이지는 iframe 차단
        source: '/((?!estimate).*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
