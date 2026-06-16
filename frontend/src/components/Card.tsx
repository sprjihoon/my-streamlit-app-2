import React from 'react';

interface CardProps {
  title?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
  actions?: React.ReactNode;
  noPadding?: boolean;
}

// 문자열 앞의 이모지 자동 제거
function stripEmoji(str: string): string {
  return str.replace(/^[\p{Emoji_Presentation}\p{Extended_Pictographic}\s]+/u, '').trim();
}

export function Card({ title, children, style, actions, noPadding }: CardProps) {
  const cleanTitle = title ? stripEmoji(title) : undefined;
  return (
    <div className="card" style={{ ...(noPadding ? { padding: 0 } : {}), ...style }}>
      {cleanTitle && (
        <div className="card-header" style={actions ? { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } : undefined}>
          <span>{cleanTitle}</span>
          {actions && <div style={{ display: 'flex', gap: '0.5rem' }}>{actions}</div>}
        </div>
      )}
      <div style={noPadding ? { padding: '1.25rem 1.5rem' } : undefined}>
        {children}
      </div>
    </div>
  );
}

export default Card;
