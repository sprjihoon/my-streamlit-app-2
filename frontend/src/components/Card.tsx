/**
 * 카드 컴포넌트
 */

interface CardProps {
  title?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export function Card({ title, children, style }: CardProps) {
  return (
    <div className="card" style={style}>
      {title && <div className="card-header">{title}</div>}
      {children}
    </div>
  );
}

export default Card;

