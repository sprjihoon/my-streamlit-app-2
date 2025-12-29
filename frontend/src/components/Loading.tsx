/**
 * 로딩 컴포넌트
 */

interface LoadingProps {
  text?: string;
}

export function Loading({ text = '로딩 중...' }: LoadingProps) {
  return (
    <div className="loading">
      <div className="spinner"></div>
      <span>{text}</span>
    </div>
  );
}

export default Loading;

