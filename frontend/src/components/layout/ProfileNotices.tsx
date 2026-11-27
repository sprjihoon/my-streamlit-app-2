'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
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
    setOpen(false);
    const token = localStorage.getItem('token');
    if (!token) {
      setItems([]);
      return;
    }
    let cancelled = false;
    fetch(`${API_URL}/employment-contracts/notices?token=${encodeURIComponent(token)}`)
      .then((res) => (res.ok ? res.json() : { items: [] }))
      .then((data) => {
        if (!cancelled) setItems(Array.isArray(data.items) ? data.items : []);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (items.length === 0) return null;

  const total = items.reduce((sum, item) => sum + (Number(item.count) || 1), 0);

  return (
    <div className="sidebar-notice">
      <button
        type="button"
        className="sidebar-notice-btn"
        aria-expanded={open}
        aria-label={`알림 ${total}건`}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={14} strokeWidth={2} />
        <span className="sidebar-notice-count">{total}</span>
      </button>
      {open && (
        <div className="sidebar-notice-list" role="menu">
          {items.map((item) => (
            <Link
              key={item.id}
              href={item.href}
              className="sidebar-notice-item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              <span className="sidebar-notice-title">
                {item.title}
                {item.count > 1 ? ` ${item.count}` : ''}
              </span>
              <span className="sidebar-notice-message">{item.message}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
