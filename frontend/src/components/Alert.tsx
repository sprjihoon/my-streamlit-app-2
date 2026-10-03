import { Alert as UiAlert } from '@/components/ui/alert';

interface AlertProps {
  type: 'success' | 'warning' | 'error' | 'info';
  message?: string;
  children?: React.ReactNode;
  onClose?: () => void;
}

export function Alert({ type, message, children, onClose }: AlertProps) {
  return (
    <UiAlert type={type}>
      {message || children}
      {onClose && (
        <button
          onClick={onClose}
          className="tw-absolute tw-right-[10px] tw-top-1/2 tw--translate-y-1/2 tw-cursor-pointer tw-border-0 tw-bg-transparent tw-text-[1.2rem]"
        >
          ×
        </button>
      )}
    </UiAlert>
  );
}

export default Alert;
