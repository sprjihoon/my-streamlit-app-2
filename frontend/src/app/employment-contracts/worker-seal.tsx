'use client';

import { useEffect, useRef, useState } from 'react';
import { Card } from '@/components/Card';
import { Button } from '@/components/ui/button';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface WorkerSealProps {
  userId: number;
  name: string;
  revision?: number;
}

async function apiError(res: Response) {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    if (typeof data?.detail === 'string') return data.detail;
  } catch {
    /* 본문이 JSON이 아니면 그대로 보여 준다 */
  }
  return text || '요청에 실패했습니다.';
}

export function WorkerSeal({ userId, name, revision = 0 }: WorkerSealProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const [samples, setSamples] = useState<{ name: string; grid: string; ring: string } | null>(null);
  const [saved, setSaved] = useState<{ kind: string; image: string }>({ kind: '', image: '' });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    let ignore = false;
    fetch(`${API}/employment-contracts/users/${userId}/mark?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (!res.ok || ignore) return;
        const data = await res.json();
        setSaved({ kind: data.kind || '', image: data.image || '' });
      })
      .catch(() => undefined);
    return () => {
      ignore = true;
    };
  }, [userId]);

  useEffect(() => {
    const token = localStorage.getItem('token') || '';
    let ignore = false;
    fetch(`${API}/employment-contracts/users/${userId}/mark-samples?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (ignore) return;
        if (!res.ok) {
          setSamples(null);
          setError(await apiError(res));
          return;
        }
        setError(null);
        setSamples(await res.json());
      })
      .catch(() => undefined);
    return () => {
      ignore = true;
    };
  }, [userId, name, revision]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }, []);

  async function saveKind(kind: 'grid' | 'ring' | 'upload' | 'signature', imageBase64 = '') {
    const token = localStorage.getItem('token') || '';
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await fetch(`${API}/employment-contracts/users/${userId}/mark?token=${encodeURIComponent(token)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, image_base64: imageBase64 }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    const data = await res.json();
    setSaved({ kind: data.kind, image: data.image });
    const whose = data.name ? `${data.name} 이름 도장` : '도장';
    setNotice(kind === 'signature' ? '싸인을 저장했습니다. 날인하면 서명란에 올라갑니다.' : `${whose}을 저장했습니다. 날인하면 서명란에 올라갑니다.`);
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 1_200_000) {
      setError('도장 파일은 1.2MB 이하로 올려 주세요.');
      return;
    }
    const encoded = await fileToBase64(file);
    await saveKind('upload', encoded);
  }

  function pointOf(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const box = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - box.left) / box.width) * canvas.width,
      y: ((event.clientY - box.top) / box.height) * canvas.height,
    };
  }

  function startDraw(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    canvas.setPointerCapture(event.pointerId);
    const point = pointOf(event);
    ctx.strokeStyle = '#1a1a1a';
    ctx.lineWidth = 3.2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(point.x, point.y);
    drawing.current = true;
  }

  function moveDraw(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const point = pointOf(event);
    ctx.lineTo(point.x, point.y);
    ctx.stroke();
  }

  function endDraw() {
    drawing.current = false;
  }

  function clearSign() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  async function saveSign() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const blank = document.createElement('canvas');
    blank.width = canvas.width;
    blank.height = canvas.height;
    if (canvas.toDataURL() === blank.toDataURL()) {
      setError('싸인을 먼저 그려 주세요.');
      return;
    }
    const encoded = canvas.toDataURL('image/png').split(',')[1] || '';
    await saveKind('signature', encoded);
  }

  return (
    <Card>
      <h3 style={{ marginTop: 0 }}>도장 · 싸인</h3>
      <p style={{ marginTop: 0, color: '#334155', fontSize: '0.9rem' }}>
        도장은 본인 성명으로만 만들어집니다. 저장해 두면 회사가 날인할 때 근로계약서·동의서·서약서의 을 서명란에 올라갑니다.
      </p>
      {error && <p style={{ color: '#b91c1c' }}>{error}</p>}
      {notice && <p style={{ color: '#166534' }}>{notice}</p>}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: 6 }}>지금 등록된 것</div>
          {saved.image ? (
            <img
              alt="등록한 도장 또는 싸인"
              src={`data:image/png;base64,${saved.image}`}
              style={{ width: 96, height: 96, objectFit: 'contain', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8 }}
            />
          ) : (
            <div style={{ width: 96, height: 96, display: 'grid', placeItems: 'center', color: '#94a3b8', border: '1px dashed #cbd5e1', borderRadius: 8, fontSize: '0.8rem' }}>
              없음
            </div>
          )}
        </div>
      </div>

      <h4 style={{ marginBottom: '0.4rem' }}>내 이름 도장</h4>
      {samples ? (
        <p style={{ marginTop: 0, color: '#334155', fontSize: '0.9rem' }}>
          <strong>{samples.name}</strong> 이름으로 만든 도장입니다. 다른 이름으로는 만들지 않습니다.
          {name.trim() && name.trim() !== samples.name ? ' 성명을 바꿨으면 위의 기재를 저장하세요. 저장한 이름으로 다시 그려집니다.' : ''}
        </p>
      ) : (
        <p style={{ marginTop: 0, color: '#64748b', fontSize: '0.82rem' }}>성명을 저장하면 그 이름으로 도장 두 가지가 나옵니다.</p>
      )}
      {samples && (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginTop: '0.8rem' }}>
          <SealChoice label="글자 도장" image={samples.grid} disabled={busy} onUse={() => saveKind('grid')} />
          <SealChoice label="겹원 도장" image={samples.ring} disabled={busy} onUse={() => saveKind('ring')} />
        </div>
      )}

      <h4 style={{ margin: '1.1rem 0 0.4rem' }}>내 도장 파일</h4>
      <input
        type="file"
        accept="image/png,image/jpeg"
        disabled={busy}
        onChange={(event) => onFile(event.target.files?.[0])}
      />

      <h4 style={{ margin: '1.1rem 0 0.4rem' }}>싸인</h4>
      <canvas
        ref={canvasRef}
        width={560}
        height={150}
        style={{ width: '100%', maxWidth: 560, height: 150, touchAction: 'none', background: '#fff', border: '1px solid #cbd5e1', borderRadius: 8, cursor: 'crosshair' }}
        onPointerDown={startDraw}
        onPointerMove={moveDraw}
        onPointerUp={endDraw}
        onPointerCancel={endDraw}
      />
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.6rem' }}>
        <Button type="button" variant="secondary" disabled={busy} onClick={clearSign}>다시 그리기</Button>
        <Button type="button" variant="primary" disabled={busy} onClick={saveSign}>이 싸인 저장</Button>
      </div>
    </Card>
  );
}

function SealChoice({
  label,
  image,
  disabled,
  onUse,
}: {
  label: string;
  image: string;
  disabled: boolean;
  onUse: () => void;
}) {
  return (
    <div style={{ textAlign: 'center' }}>
      <img
        alt={label}
        src={`data:image/png;base64,${image}`}
        style={{ width: 120, height: 120, objectFit: 'contain', background: '#fff' }}
      />
      <div>
        <Button type="button" variant="primary" disabled={disabled} onClick={onUse}>{label} 저장</Button>
      </div>
    </div>
  );
}

function fileToBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || '');
      resolve(value.includes(',') ? value.split(',')[1] : value);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
