import React from 'react';
import { Card as UiCard, CardContent, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface CardProps {
  title?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
  actions?: React.ReactNode;
  noPadding?: boolean;
  className?: string;
}

function stripEmoji(str: string): string {
  return str.replace(/^[\p{Emoji_Presentation}\p{Extended_Pictographic}\s]+/u, '').trim();
}

export function Card({ title, children, style, actions, noPadding, className }: CardProps) {
  const cleanTitle = title ? stripEmoji(title) : undefined;
  return (
    <UiCard className={cn(noPadding ? '!tw-p-0' : undefined, className)} style={style}>
      {cleanTitle && (
        <CardHeader className={actions ? 'tw-justify-between' : undefined}>
          <span>{cleanTitle}</span>
          {actions && <div className="tw-flex tw-gap-2">{actions}</div>}
        </CardHeader>
      )}
      <CardContent className={noPadding ? 'tw-px-6 tw-py-5' : undefined}>{children}</CardContent>
    </UiCard>
  );
}

export default Card;
