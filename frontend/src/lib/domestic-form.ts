import { ApiError } from '@/lib/api/client';
import type { DomesticBoxSize, DomesticShipment, DomesticSubmitPayload, DomesticVendor } from '@/lib/api';

export type FieldErrors = Record<string, string>;

export type DomesticBannerKind = 'validation' | 'network' | 'server' | 'uncertain' | 'auth';

export type DomesticBanner = {
  kind: DomesticBannerKind;
  message: string;
  field?: string;
};

export const SHIPMENT_FIELD_ORDER = [
  'vendor_id',
  'recipient_name',
  'recipient_phone',
  'recipient_zip',
  'recipient_addr1',
  'print_sender_name',
  'print_sender_phone',
  'print_sender_zip',
  'print_sender_addr1',
  'goods_name',
  'goods_qty',
  'box_size',
  'label_count',
] as const;

export const VENDOR_FIELD_ORDER = [
  'name',
  'office_ser',
  'sender_name',
  'sender_phone',
  'sender_zip',
  'sender_addr1',
] as const;

export type ListFilters = {
  q: string;
  vendor: string;
  from: string;
  to: string;
  status: '' | 'requested' | 'test' | 'canceled';
};

export function firstField(errors: FieldErrors, order: readonly string[]): string | null {
  for (const key of order) {
    if (errors[key]) return key;
  }
  const keys = Object.keys(errors);
  return keys[0] || null;
}

export function focusDomesticField(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ block: 'center' });
  if (el instanceof HTMLElement) el.focus();
}

function plain(value: string): string {
  return value.replace(/[&=\r\n]/g, ' ').replace(/\s+/g, ' ').trim();
}

function phoneDigits(phone: string): string {
  let digits = phone.replace(/\D/g, '');
  if (digits.startsWith('82') && digits.length >= 11) digits = `0${digits.slice(2)}`;
  return digits.slice(0, 12);
}

function phoneError(phone: string, label: string): string | null {
  if (/^\d{9,12}$/.test(phoneDigits(phone))) return null;
  const current = phone.trim() || '(비어 있음)';
  return `${label}는 숫자 9~12자리여야 합니다. (현재: "${current}") 01012345678 형식으로 입력해주세요.`;
}

function zipDigits(zip: string): string {
  return zip.replace(/\D/g, '').slice(0, 5);
}

function zipError(zip: string, who: string): string | null {
  if (zipDigits(zip).length === 5) return null;
  return `${who} 우편번호 5자리를 입력해주세요.`;
}

function nameError(name: string, who: string): string | null {
  if (plain(name).length >= 1) return null;
  return `${who} 이름을 입력해주세요.`;
}

function addrError(addr: string, who: string): string | null {
  if (addr.trim().length >= 2) return null;
  return `${who} 주소를 입력해주세요.`;
}

function countError(value: number, name: string): string | null {
  if (Number.isInteger(value) && value >= 1 && value <= 99) return null;
  return `${name}는 1에서 99 사이여야 합니다.`;
}

function partyErrors(
  errors: FieldErrors,
  who: string,
  fields: { name: string; phone: string; zip: string; addr1: string },
  values: { name: string; phone: string; zip: string; addr1: string },
) {
  const name = nameError(values.name, who);
  const phone = phoneError(values.phone, `${who} 전화`);
  const zip = zipError(values.zip, who);
  const addr = addrError(values.addr1, who);
  if (name) errors[fields.name] = name;
  if (phone) errors[fields.phone] = phone;
  if (zip) errors[fields.zip] = zip;
  if (addr) errors[fields.addr1] = addr;
}

export function validateShipment(
  form: DomesticSubmitPayload,
  vendors: DomesticVendor[],
  boxSizes: DomesticBoxSize[],
): FieldErrors {
  const errors: FieldErrors = {};
  const vendor = vendors.find((item) => item.id === form.vendor_id);
  if (!form.vendor_id) {
    errors.vendor_id = '업체를 선택해주세요.';
  } else if (!vendor) {
    errors.vendor_id = '출고 업체를 찾을 수 없습니다.';
  } else if (!String(vendor.office_ser || '').trim()) {
    errors.vendor_id = '공급지번호가 없는 업체는 접수할 수 없습니다.';
  }

  partyErrors(
    errors,
    '받는 사람',
    {
      name: 'recipient_name',
      phone: 'recipient_phone',
      zip: 'recipient_zip',
      addr1: 'recipient_addr1',
    },
    {
      name: form.recipient_name,
      phone: form.recipient_phone,
      zip: form.recipient_zip,
      addr1: form.recipient_addr1,
    },
  );

  if (plain(form.print_sender_name)) {
    const phone = form.print_sender_phone.trim() || vendor?.sender_phone || '';
    const zip = form.print_sender_zip.trim() || vendor?.sender_zip || '';
    const addr1 = form.print_sender_addr1.trim() || vendor?.sender_addr1 || '';
    const senderName = nameError(form.print_sender_name, '보내는 사람');
    const senderPhone = phoneError(phone, '보내는 사람 전화');
    const senderZip = zipError(zip, '보내는 사람');
    const senderAddr = addrError(addr1, '보내는 사람');
    if (senderName) errors.print_sender_name = senderName;
    if (senderPhone) errors.print_sender_phone = senderPhone;
    if (senderZip) errors.print_sender_zip = senderZip;
    if (senderAddr) errors.print_sender_addr1 = senderAddr;
  }

  if (!plain(form.goods_name)) errors.goods_name = '상품명을 입력해주세요.';
  const qty = countError(form.goods_qty, '상품수량');
  const sheets = countError(form.label_count, '송장 갯수');
  if (qty) errors.goods_qty = qty;
  if (sheets) errors.label_count = sheets;
  if (boxSizes.length && !boxSizes.some((size) => size.code === form.box_size)) {
    errors.box_size = `잘못된 박스 규격: ${form.box_size}`;
  }
  return errors;
}

export function validateVendor(form: Omit<DomesticVendor, 'id'>): FieldErrors {
  const errors: FieldErrors = {};
  if (!plain(form.name)) errors.name = '업체명을 입력해주세요.';
  if (!form.office_ser.replace(/\D/g, '')) errors.office_ser = '공급지번호를 입력해주세요.';
  partyErrors(
    errors,
    '보내는 사람',
    {
      name: 'sender_name',
      phone: 'sender_phone',
      zip: 'sender_zip',
      addr1: 'sender_addr1',
    },
    {
      name: form.sender_name,
      phone: form.sender_phone,
      zip: form.sender_zip,
      addr1: form.sender_addr1,
    },
  );
  return errors;
}

function detailMessage(err: ApiError): string {
  try {
    const parsed = JSON.parse(err.message);
    if (typeof parsed?.detail === 'string') return parsed.detail;
  } catch {
    /* 본문이 JSON이 아니면 그대로 보여준다. */
  }
  return err.message || `API Error: ${err.status}`;
}

function shipmentFieldFromMessage(message: string): string | undefined {
  if (message.includes('공급지번호') || message.includes('출고 업체') || message.includes('업체 보내는 사람')) {
    return 'vendor_id';
  }
  if (message.includes('받는 사람 이름')) return 'recipient_name';
  if (message.includes('받는 사람 전화')) return 'recipient_phone';
  if (message.includes('받는 사람 우편번호')) return 'recipient_zip';
  if (message.includes('받는 사람 주소')) return 'recipient_addr1';
  if (message.includes('보내는 사람 이름')) return 'print_sender_name';
  if (message.includes('보내는 사람 전화')) return 'print_sender_phone';
  if (message.includes('보내는 사람 우편번호')) return 'print_sender_zip';
  if (message.includes('보내는 사람 주소')) return 'print_sender_addr1';
  if (message.includes('상품명')) return 'goods_name';
  if (message.includes('상품수량')) return 'goods_qty';
  if (message.includes('송장 갯수')) return 'label_count';
  if (message.includes('박스')) return 'box_size';
  return undefined;
}

function vendorFieldFromMessage(message: string): string | undefined {
  if (message.includes('업체명')) return 'name';
  if (message.includes('공급지')) return 'office_ser';
  if (message.includes('이름')) return 'sender_name';
  if (message.includes('전화')) return 'sender_phone';
  if (message.includes('우편번호')) return 'sender_zip';
  if (message.includes('주소')) return 'sender_addr1';
  return undefined;
}

export function classifyDomesticError(err: unknown, scope: 'shipment' | 'vendor'): DomesticBanner {
  if (err instanceof ApiError) {
    const message = detailMessage(err);
    const field = scope === 'shipment' ? shipmentFieldFromMessage(message) : vendorFieldFromMessage(message);
    if (err.status === 400) return { kind: 'validation', message, field };
    if (err.status === 401 || err.status === 403) return { kind: 'auth', message, field };
    return { kind: 'server', message, field };
  }
  const message = err instanceof Error ? err.message : String(err);
  if (message.includes('출고 목록에서 송장 생성 여부')) {
    return { kind: 'uncertain', message };
  }
  if (
    message.includes('서버에 연결할 수 없습니다')
    || message.includes('Failed to fetch')
    || message.includes('NetworkError')
    || message.includes('Load failed')
  ) {
    return { kind: 'network', message };
  }
  return { kind: 'server', message };
}

export function domesticStatusLabel(item: {
  status: string;
  is_test: boolean;
  treat_status?: string | null;
  treat_status_name?: string | null;
}) {
  if (item.status === 'canceled') return '취소';
  if (item.is_test) return '테스트';
  const delivery = (item.treat_status_name || item.treat_status || '').trim();
  return delivery || '접수';
}

export function emptyListFilters(): ListFilters {
  return { q: '', vendor: '', from: '', to: '', status: '' };
}

export function readListFilters(search: string): ListFilters {
  const params = new URLSearchParams(search);
  const status = params.get('status') || '';
  return {
    q: params.get('q') || '',
    vendor: params.get('vendor') || '',
    from: params.get('from') || '',
    to: params.get('to') || '',
    status: status === 'requested' || status === 'test' || status === 'canceled' ? status : '',
  };
}

export function listFiltersQuery(filters: ListFilters): string {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.vendor) params.set('vendor', filters.vendor);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  if (filters.status) params.set('status', filters.status);
  return params.toString();
}

export function replaceListFilters(filters: ListFilters) {
  const query = listFiltersQuery(filters);
  const path = window.location.pathname;
  window.history.replaceState(null, '', query ? `${path}?${query}` : path);
}

export function listReturnHref(search: string): string {
  const query = listFiltersQuery(readListFilters(search));
  return query ? `/domestic-shipping-list?${query}` : '/domestic-shipping-list';
}

export function filtersActive(filters: ListFilters): boolean {
  return Boolean(filters.q || filters.vendor || filters.from || filters.to || filters.status);
}

export function filterShipments(items: DomesticShipment[], filters: ListFilters): DomesticShipment[] {
  const q = filters.q.trim().toLowerCase();
  return items.filter((item) => {
    if (filters.vendor && String(item.vendor_id) !== filters.vendor) return false;
    if (filters.status === 'canceled' && item.status !== 'canceled') return false;
    if (filters.status === 'test' && !(item.is_test && item.status !== 'canceled')) return false;
    if (filters.status === 'requested' && !(!item.is_test && item.status !== 'canceled')) return false;
    const day = (item.created_at || '').slice(0, 10);
    if ((filters.from || filters.to) && !day) return false;
    if (filters.from && day < filters.from) return false;
    if (filters.to && day > filters.to) return false;
    if (!q) return true;
    return [item.tracking_no, item.order_no, item.recipient_name, item.vendor_name]
      .join('\n')
      .toLowerCase()
      .includes(q);
  });
}
