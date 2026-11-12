'use client';

export default function ChinaAddressGuideDialog({ onClose }: { onClose: () => void }) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 90,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="china-guide-title"
        style={{
          width: '100%',
          maxWidth: 480,
          background: 'var(--bg-card)',
          borderRadius: 16,
          boxShadow: 'var(--shadow-lg)',
          padding: '1.15rem 1.2rem 1.1rem',
        }}
      >
        <p id="china-guide-title" style={{ fontWeight: 700, marginBottom: '0.75rem' }}>
          중국 주소 검증 방법
        </p>
        <ol style={{ margin: '0 0 0.9rem', paddingLeft: '1.15rem', display: 'flex', flexDirection: 'column', gap: '0.45rem', lineHeight: 1.45 }}>
          <li>상세주소, 시/구, 성, 우편번호 6자리를 입력합니다. 한자로 넣어도 됩니다.</li>
          <li>중국 주소 검증을 누릅니다.</li>
          <li>건물이 찾아지면 지도의 영문 주소로 바꿀지 물어봅니다. 추천 주소를 쓰면 그 영문으로 접수합니다.</li>
          <li>시/구만 찾아지면 건물 번호는 확인되지 않습니다. 우편번호와 성이 맞으면 접수는 됩니다.</li>
          <li>우편번호와 성이 다르면 접수가 막힙니다. 제안한 성으로 바꾸거나 우편번호를 고칩니다.</li>
        </ol>
        <button type="button" className="btn btn-primary" style={{ width: '100%' }} onClick={onClose}>
          확인
        </button>
      </div>
    </div>
  );
}
