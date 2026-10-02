import type { ReactNode } from 'react';

export interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  adminOnly?: boolean;
  allowDepartments?: string[];
}

export interface User {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
  position?: string;
  department?: string;
}
