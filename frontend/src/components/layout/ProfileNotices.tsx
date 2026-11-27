'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bell } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Notice = {
  id: string;
  title: string;
  message: string;
  href: string;
  count: number;
};

export function ProfileNotices({ pathname }: { pathname: string }) {
  const [items, setItems] = useState<Notice[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setItems([]);
      setOpen(false);
      return;
    }
    let cancelled = false;
    fetch(`${API_URL}/employment-contracts/notices?token=${encodeURIComponent(token)}`)
      .then((res) => (res.ok ? res.json() : { items: [] }))
      .then((data) => {
        if (cancelled) return;
        const next = Array.isArray(data.items) ? data.items as Notice[] : [];
        setItems(next);
        const key = next.map((item) => item.id).join(',');
        const seen = sessionStorage.getItem('profile-notice-seen');
        setOpen(next.length > 0 && seen !== key);
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
          setOpen(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (items.length === 0) return null;

  const total = items.reduce((sum, item) => sum + (Number(item.count) || 1), 0);

  function dismiss() {
    sessionStorage.setItem('profile-notice-seen', items.map((item) => item.id).join(','));
    setOpen(false);
  }

  const modal = open ? (
    <div
      className="profile-notice-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) dismiss();
      }}
    >
      <div className="profile-notice-modal" role="dialog" aria-modal="true" aria-labelledby="profile-notice-title">
        <div className="profile-notice-head">
          <h2 id="profile-notice-title">알림 {total}건</h2>
          <button type="button" onClick={dismiss}>닫기</button>
        </div>
        <div className="profile-notice-body">
          {items.map((item) => (
            <Link key={item.id} href={item.href} className="profile-notice-item" onClick={dismiss}>
              <span className="profile-notice-title">
                {item.title}
                {item.count > 1 ? ` ${item.count}건` : ''}
              </span>
              <span className="profile-notice-message">{item.message}</span>
              <span className="profile-notice-go">메뉴로 이동</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div className="sidebar-notice">
      <button
        type="button"
        className="sidebar-notice-btn"
        aria-expanded={open}
        aria-label={`알림 ${total}건`}
        onClick={() => setOpen(true)}
      >
        <Bell size={14} strokeWidth={2} />
        <span className="sidebar-notice-count">{total}</span>
      </button>
      {modal && typeof document !== 'undefined' ? createPortal(modal, document.body) : modal}
    </div>
  );
}
