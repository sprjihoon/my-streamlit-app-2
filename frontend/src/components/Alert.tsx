/**
 * 알림 컴포넌트
 */

interface AlertProps {
  type: 'success' | 'warning' | 'error' | 'info';
  message?: string;
  children?: React.ReactNode;
  onClose?: () => void;
}

export function Alert({ type, message, children, onClose }: AlertProps) {
  return (
    <div className={`alert alert-${type}`} style={{ position: 'relative', marginBottom: '1rem' }}>
      {message || children}
      {onClose && (
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            right: '10px',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '1.2rem',
          }}
        >
          ×
        </button>
      )}
    </div>
  );
}

export default Alert;

