import {
  LayoutDashboard, ClipboardList, Scissors, Upload, Link2, List, DollarSign,
  BarChart2, FileText, FileSpreadsheet, TrendingUp, CalendarDays,
  Calendar, Receipt, BadgeCheck, Globe, CreditCard, Package, Truck,
  PlusCircle, Users, ScrollText, Settings, AlertTriangle,
} from 'lucide-react';
import type { NavItem } from './types';

export const IC = { size: 14, strokeWidth: 1.75 };

export function canSeeNavItem(user: { is_admin?: boolean; department?: string } | null, item: NavItem) {
  if (user?.is_admin) return true;
  if (item.allowDepartments?.length) {
    const dept = (user?.department || '').replace(/\s/g, '');
    return item.allowDepartments.some((allowed) => {
      const a = allowed.replace(/\s/g, '');
      if (!dept || !a) return false;
      return dept === a || dept.includes(a.replace(/팀$/, '')) || a.includes(dept.replace(/팀$/, ''));
    });
  }
  return !item.adminOnly;
}

// adminOnly: true → 관리자(is_admin)만 표시
// adminOnly 없음 → 모든 로그인 사용자 표시
export const NAV_GROUPS: {
  key: string;
  label: string;
  icon: React.ReactNode;
  items: NavItem[];
}[] = [
  {
    key: 'home',
    label: '기본',
    icon: <LayoutDashboard {...IC} />,
    items: [
      { href: '/', label: '대시보드', icon: <LayoutDashboard {...IC} />, adminOnly: true },
      { href: '/upload', label: '데이터 업로드', icon: <Upload {...IC} />, adminOnly: true },
      { href: '/mapping', label: '업체 매핑 관리', icon: <Link2 {...IC} />, adminOnly: true },
      { href: '/vendors', label: '매핑 리스트', icon: <List {...IC} />, adminOnly: true },
      { href: '/rates', label: '요금표 관리', icon: <DollarSign {...IC} />, adminOnly: true },
      { href: '/insights', label: '데이터 인사이트', icon: <TrendingUp {...IC} /> },
    ],
  },
  {
    key: 'journal',
    label: '일지',
    icon: <ClipboardList {...IC} />,
    items: [
      { href: '/work-log', label: '작업일지', icon: <ClipboardList {...IC} /> },
      { href: '/repair-log', label: '수선작업일지', icon: <Scissors {...IC} /> },
      { href: '/defect-log', label: '불량일지', icon: <AlertTriangle {...IC} /> },
      { href: '/inbound-log', label: '입고일지', icon: <Package {...IC} /> },
      { href: '/inbound-overview', label: '통합현황', icon: <Package {...IC} /> },
      { href: '/journal-settings', label: '일지설정', icon: <Settings {...IC} /> },
    ],
  },
  {
    key: 'return-request',
    label: '회수신청',
    icon: <Truck {...IC} />,
    items: [
      { href: '/return-request', label: '회수신청', icon: <Truck {...IC} /> },
      { href: '/kpost-pickup-list', label: '접수목록', icon: <Truck {...IC} /> },
      { href: '/saved-recipients', label: '저장된 주소지', icon: <Truck {...IC} /> },
    ],
  },
  {
    key: 'domestic-shipping',
    label: '국내출고',
    icon: <Truck {...IC} />,
    items: [
      { href: '/domestic-shipping', label: '출고 접수', icon: <Truck {...IC} /> },
      { href: '/domestic-shipping-list', label: '접수목록', icon: <List {...IC} /> },
      { href: '/domestic-vendors', label: '업체 등록', icon: <List {...IC} /> },
      { href: '/domestic-saved-recipients', label: '저장된 주소지', icon: <Truck {...IC} /> },
    ],
  },
  {
    key: 'overseas-shipping',
    label: '해외배송',
    icon: <Globe {...IC} />,
    items: [
      { href: '/overseas-shipping', label: '해외배송 접수', icon: <Globe {...IC} /> },
      { href: '/overseas-shipping-list', label: '접수목록', icon: <Globe {...IC} /> },
      { href: '/overseas-senders', label: '발송인 목록', icon: <Globe {...IC} /> },
      { href: '/overseas-recipients', label: '수취인 목록', icon: <Globe {...IC} /> },
      { href: '/overseas-hs-codes', label: 'HS코드 목록', icon: <Globe {...IC} /> },
    ],
  },
  {
    key: 'invoice',
    label: '인보이스',
    icon: <BarChart2 {...IC} />,
    items: [
      { href: '/invoice', label: '인보이스 계산', icon: <FileSpreadsheet {...IC} />, adminOnly: true },
      { href: '/invoice-list', label: '인보이스 목록', icon: <List {...IC} />, adminOnly: true },
      { href: '/invoice-analytics', label: '청구금액 분석', icon: <TrendingUp {...IC} /> },
    ],
  },
  {
    key: 'estimate',
    label: '견적서',
    icon: <FileText {...IC} />,
    items: [
      { href: '/estimate', label: '견적서 만들기', icon: <FileText {...IC} /> },
      { href: '/estimate-list', label: '견적서 목록', icon: <List {...IC} /> },
      { href: '/estimate-analytics', label: '견적서 분석', icon: <BarChart2 {...IC} /> },
    ],
  },
  {
    key: 'groupware',
    label: '그룹웨어',
    icon: <CalendarDays {...IC} />,
    items: [
      { href: '/leave', label: '연월차 관리', icon: <CalendarDays {...IC} /> },
      { href: '/leave/calendar', label: '연차 달력', icon: <Calendar {...IC} /> },
      { href: '/receipts', label: '영수증 처리', icon: <Receipt {...IC} /> },
      { href: '/certificates', label: '증명서 발급', icon: <BadgeCheck {...IC} /> },
    ],
  },
  {
    key: 'marketing',
    label: '마케팅',
    icon: <Globe {...IC} />,
    items: [
      { href: '/wp-analytics', label: '사이트 방문 분석', icon: <Globe {...IC} /> },
    ],
  },
];

export const BILLING_INVOICE_NAV_ITEMS: NavItem[] = [
  { href: '/billing-invoice', label: '실 인보이스 관리', icon: <CreditCard {...IC} /> },
  { href: '/billing-invoice/analytics', label: '청구금액 분석', icon: <BarChart2 {...IC} /> },
];

export const ADMIN_NAV_ITEMS: NavItem[] = [
  { href: '/storage', label: '보관료 관리', icon: <Package {...IC} /> },
  { href: '/vendor-charges', label: '추가비용 관리', icon: <PlusCircle {...IC} /> },
  { href: '/users', label: '사용자 관리', icon: <Users {...IC} /> },
  { href: '/logs', label: '활동 로그', icon: <ScrollText {...IC} /> },
  { href: '/settings', label: '회사 설정', icon: <Settings {...IC} /> },
];
