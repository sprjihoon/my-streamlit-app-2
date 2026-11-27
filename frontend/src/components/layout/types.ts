import type { ReactNode } from 'react';

export interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  adminOnly?: boolean;
  workerOnly?: boolean;
  partTimeAccess?: boolean;
  allowDepartments?: string[];
}

export interface User {
  user_id: number;
  username: string;
  nickname: string;
  is_admin: boolean;
  can_manage_part_time?: boolean;
  position?: string;
  department?: string;
  needs_contract?: boolean;
}
