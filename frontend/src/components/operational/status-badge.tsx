import { Badge } from '@/components/ui/badge';

const STATUS_VARIANT = {
  ocr_pending: 'neutral',
  confirming: 'warning',
  inbound_done: 'info',
  grading: 'grading',
  repairing: 'repairing',
  done: 'success',
  cancelled: 'danger',
  pending: 'warning',
  etc: 'neutral',
} as const;

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const variant = STATUS_VARIANT[status as keyof typeof STATUS_VARIANT] ?? 'neutral';
  return <Badge variant={variant}>{label}</Badge>;
}
