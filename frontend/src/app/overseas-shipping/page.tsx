'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Card from '@/components/Card';
import Alert from '@/components/Alert';
import Loading from '@/components/Loading';
import PageHeader from '@/components/PageHeader';
import AddressSuggestionDialog from '@/components/AddressSuggestionDialog';
import OverseasRecipientPickerModal from '@/components/OverseasRecipientPickerModal';
import {
  createOverseasShipping,
  deleteOverseasSavedAddress,
  deleteOverseasSavedSender,
  getOverseasShippingMeta,
  listOverseasNations,
  listOverseasSavedAddresses,
  listOverseasSavedHs,
  listOverseasSavedSenders,
  previewOverseasShipping,
  quoteOverseasShipping,
  saveOverseasAddress,
  saveOverseasHs,
  saveOverseasSender,
  searchOverseasItemCategories,
  type OverseasDutyQuote,
  type OverseasInvoiceItem,
  type OverseasQuotePart,
  type OverseasSavedAddress,
  type OverseasSavedHs,
  type OverseasSavedSender,
  type OverseasShippingPayload,
} from '@/lib/api';
import { ITEM_CATEGORIES, searchItemCategories, type ItemCategory } from '@/lib/item-categories';
import {
  googleMapsApiKey,
  loadGoogleMapsScript,
  parsePlaceResult,
  supportsAddressValidation,
  validateAddressWithGoogle,
} from '@/lib/google-places';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.55rem 0.7rem',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontFamily: 'inherit',
  fontSize: '0.9rem',
};

const fieldGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '0.75rem',
};

function FormSection({
  title,
  first,
  children,
}: {
  title: string;
  first?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        marginTop: first ? 0 : '1.1rem',
        paddingTop: first ? 0 : '1rem',
        borderTop: first ? 'none' : '2px solid #cbd5e1',
      }}
    >
      <h3
        style={{
          margin: '0 0 0.9rem',
          fontSize: '0.95rem',
          fontWeight: 700,
          color: 'var(--text-primary)',
          letterSpacing: 0,
          textTransform: 'none',
        }}
      >
        {title}
      </h3>
      {children}
    </section>
  );
}

function parseApiError(err: unknown): string {
  if (err instanceof Error) {
    const msg = err.message;
    try {
      const parsed = JSON.parse(msg);
      if (typeof parsed?.detail === 'string') return parsed.detail;
    } catch {
      /* ignore */
    }
    return msg;
  }
  return String(err);
}

function newItem(): OverseasInvoiceItem {
  return { name_en: '', quantity: 1, unit_price_usd: 20, hs_code: '', origin_country: 'KR' };
}

function emptyForm(senderName = '스프링풀필먼트'): OverseasShippingPayload {
  return {
    shipping_method: 'EMS',
    contents_type: 'parcel',
    countrycd: 'JP',
    sender_name: senderName,
    sender_zipcode: '',
    sender_addr1: '',
    sender_addr2: '',
    sender_addr3: '',
    sender_tel: '',
    receivename: '',
    receivetelno: '',
    receivemail: '',
    receivezipcode: '',
    receiveaddr1: '',
    receiveaddr2: '',
    receiveaddr3: '',
    totweight: 500,
    boxlength: 30,
    boxwidth: 25,
    boxheight: 15,
    items: [newItem()],
    notes: '',
    test_mode: false,
    save_address: false,
    save_address_label: '',
    save_address_default: false,
    save_sender: false,
    save_sender_label: '',
    save_sender_default: false,
  };
}

const METHOD_PREMIUM: Record<OverseasShippingPayload['shipping_method'], string> = {
  EMS: '31',
  EMS_PREMIUM: '32',
  KPACKET: '14',
};

const GMAPS_KEY = googleMapsApiKey();

export default function OverseasShippingPage() {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [printId, setPrintId] = useState<number | null>(null);
  const [liveReady, setLiveReady] = useState(false);
  const [defaultSender, setDefaultSender] = useState('스프링풀필먼트');
  const [senderAddr, setSenderAddr] = useState('');
  const [methods, setMethods] = useState<Array<{ code: string; name: string; desc: string }>>([]);
  const [nations, setNations] = useState<Array<{ nationcd: string; nationnm: string; nationfn: string }>>([]);
  const [nationsFallback, setNationsFallback] = useState(false);
  const [nationQuery, setNationQuery] = useState('');
  const [quoteFee, setQuoteFee] = useState<number | null>(null);
  const [quoteLive, setQuoteLive] = useState(false);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [quoteDuty, setQuoteDuty] = useState<OverseasDutyQuote | null>(null);
  const [quoteTotal, setQuoteTotal] = useState<number | null>(null);
  const [quoteParcel, setQuoteParcel] = useState<OverseasQuotePart | null>(null);
  const [quoteDocument, setQuoteDocument] = useState<OverseasQuotePart | null>(null);
  const [savedAddresses, setSavedAddresses] = useState<OverseasSavedAddress[]>([]);
  const [selectedSavedId, setSelectedSavedId] = useState('');
  const [recipientPickerOpen, setRecipientPickerOpen] = useState(false);
  const [savedSenders, setSavedSenders] = useState<OverseasSavedSender[]>([]);
  const [selectedSenderId, setSelectedSenderId] = useState('');
  const [savedHs, setSavedHs] = useState<ItemCategory[]>([]);
  const [form, setForm] = useState<OverseasShippingPayload>(emptyForm());
  const [hsQuery, setHsQuery] = useState<Record<number, string>>({});
  const [hsOpen, setHsOpen] = useState<number | null>(null);
  const [hsMatches, setHsMatches] = useState<Record<number, ItemCategory[]>>({});
  const hsTimer = useRef<Record<number, number>>({});
  const [validating, setValidating] = useState(false);
  const [addressHint, setAddressHint] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<{
    original: { addr3: string; addr2: string; addr1: string; zip: string };
    suggested: { addr3: string; addr2: string; addr1: string; zip: string; formattedAddress?: string };
  } | null>(null);

  const addr3Ref = useRef<HTMLInputElement>(null);
  const autocompleteRef = useRef<{ setComponentRestrictions: (opts: { country: string }) => void } | null>(null);
  const countryRef = useRef(form.countrycd);
  countryRef.current = form.countrycd;
  const formRef = useRef(form);
  formRef.current = form;
  const nationsRef = useRef(nations);
  nationsRef.current = nations;
  const validateRef = useRef<(opts?: {
    addr3?: string;
    addr2?: string;
    addr1?: string;
    zip?: string;
    countrycd?: string;
    silent?: boolean;
  }) => Promise<void>>(async () => {});

  async function reloadSaved(auth: string) {
    const [addrRes, senderRes, hsRes] = await Promise.all([
      listOverseasSavedAddresses(auth),
      listOverseasSavedSenders(auth),
      listOverseasSavedHs(auth),
    ]);
    setSavedAddresses(addrRes.items || []);
    setSavedSenders(senderRes.items || []);
    setSavedHs(
      (hsRes.items || []).map((h: OverseasSavedHs) => ({
        id: `saved-${h.id}`,
        name_ko: h.name_ko || h.label,
        name_en: h.name_en,
        hs_code: h.hs_code,
        group: h.group_name || '저장품목',
        origin_country: h.origin_country,
        saved: true,
        saved_id: h.id,
        label: h.label,
      })),
    );
    return { addresses: addrRes.items || [], senders: senderRes.items || [] };
  }

  useEffect(() => {
    const stored = localStorage.getItem('token') || '';
    setToken(stored);
    if (!stored) {
      setError('로그인이 필요합니다.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const meta = await getOverseasShippingMeta(stored);
        setLiveReady(meta.live_ready);
        setMethods(meta.methods || []);
        setDefaultSender(meta.sender.name);
        setSenderAddr(meta.sender.addr);
        setForm((prev) => ({
          ...prev,
          sender_name: prev.sender_name || meta.sender.name,
          sender_zipcode: prev.sender_zipcode || meta.sender.zip || '',
          sender_addr1: prev.sender_addr1 || meta.sender.addr1 || '',
          sender_addr2: prev.sender_addr2 || meta.sender.addr2 || '',
          sender_addr3: prev.sender_addr3 || meta.sender.addr3 || '',
          sender_tel: prev.sender_tel || meta.sender.tel || '',
        }));
        const [nationRes, lists] = await Promise.all([
          listOverseasNations(stored, METHOD_PREMIUM.EMS),
          reloadSaved(stored),
        ]);
        const nationItems = nationRes.items || [];
        setNations(nationItems);
        setNationsFallback(!!nationRes.fallback);
        const defSender = lists.senders.find((a) => a.is_default);
        if (defSender) applySender(defSender);
        const def = lists.addresses.find((a) => a.is_default);
        if (def) applySaved(def);
        const keepCountry = def?.countrycd;
        if (keepCountry && !nationItems.some((n) => n.nationcd === keepCountry) && nationItems[0]) {
          setForm((prev) => ({ ...prev, countrycd: nationItems[0].nationcd }));
        }
      } catch (err) {
        setError(parseApiError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!GMAPS_KEY || !addr3Ref.current) return;
    let cancelled = false;
    loadGoogleMapsScript(GMAPS_KEY)
      .then(() => {
        if (cancelled || !addr3Ref.current || !window.google?.maps?.places) return;
        if (autocompleteRef.current) {
          autocompleteRef.current.setComponentRestrictions({ country: countryRef.current.toLowerCase() });
          return;
        }
        const ac = new window.google.maps.places.Autocomplete(addr3Ref.current, {
          types: ['address'],
          componentRestrictions: { country: countryRef.current.toLowerCase() },
          fields: ['address_components', 'formatted_address'],
        });
        autocompleteRef.current = ac;
        ac.addListener('place_changed', () => {
          const place = ac.getPlace();
          if (!place.address_components) return;
          const parsed = parsePlaceResult(place, countryRef.current);
          setForm((prev) => ({
            ...prev,
            receiveaddr3: parsed.addr3 || prev.receiveaddr3,
            receiveaddr2: parsed.addr2 || prev.receiveaddr2,
            receiveaddr1: parsed.addr1 || prev.receiveaddr1,
            receivezipcode: parsed.zip || prev.receivezipcode,
          }));
          void validateRef.current({
            addr3: parsed.addr3 || formRef.current.receiveaddr3,
            addr2: parsed.addr2 || formRef.current.receiveaddr2,
            addr1: parsed.addr1 || formRef.current.receiveaddr1,
            zip: parsed.zip || formRef.current.receivezipcode,
            countrycd: countryRef.current,
          });
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [form.countrycd, loading]);

  useEffect(() => {
    if (!token || loading || !form.countrycd || form.totweight < 1) {
      if (form.totweight < 1) {
        setQuoteFee(null);
        setQuoteError(null);
        setQuoteDuty(null);
        setQuoteTotal(null);
        setQuoteParcel(null);
        setQuoteDocument(null);
      }
      return;
    }
    const customsValue = form.items.reduce(
      (sum, item) => sum + Number(item.unit_price_usd || 0) * Number(item.quantity || 0),
      0,
    );
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setQuoteLoading(true);
      try {
        const res = await quoteOverseasShipping(token, {
          shipping_method: form.shipping_method,
          contents_type: form.contents_type || 'parcel',
          countrycd: form.countrycd,
          totweight: form.totweight,
          boxlength: form.boxlength,
          boxwidth: form.boxwidth,
          boxheight: form.boxheight,
          customs_value_usd: customsValue,
        });
        if (cancelled) return;
        setQuoteLive(!!res.live);
        setQuoteDuty(res.duty || null);
        setQuoteTotal(res.payableTotal ?? null);
        setQuoteParcel(res.parcel || null);
        setQuoteDocument(res.document ?? null);
        if (res.ok && res.totalFee != null) {
          setQuoteFee(res.totalFee);
          setQuoteError(null);
        } else {
          setQuoteFee(null);
          setQuoteError(res.error || '해당 국가 또는 서비스 요금을 조회할 수 없습니다.');
        }
      } catch (err) {
        if (!cancelled) {
          setQuoteFee(null);
          setQuoteDuty(null);
          setQuoteTotal(null);
          setQuoteParcel(null);
          setQuoteDocument(null);
          setQuoteError(parseApiError(err));
        }
      } finally {
        if (!cancelled) setQuoteLoading(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [token, loading, form.shipping_method, form.contents_type, form.countrycd, form.totweight, form.boxlength, form.boxwidth, form.boxheight, form.items]);

  const triggerAddressValidation = useCallback(async (override?: {
    addr3?: string;
    addr2?: string;
    addr1?: string;
    zip?: string;
    countrycd?: string;
    silent?: boolean;
  }) => {
    const current = formRef.current;
    const addr3 = (override?.addr3 ?? current.receiveaddr3).trim();
    const addr2 = override?.addr2 ?? current.receiveaddr2;
    const addr1 = override?.addr1 ?? current.receiveaddr1;
    const zip = override?.zip ?? current.receivezipcode;
    const countrycd = override?.countrycd ?? current.countrycd;
    const silent = !!override?.silent;

    if (!GMAPS_KEY) {
      if (!silent) window.alert('구글 주소키가 없어 검증할 수 없습니다.');
      return;
    }
    if (!addr3) {
      if (!silent) window.alert('수취인 상세주소를 입력한 뒤 검증하세요.');
      return;
    }
    if (!supportsAddressValidation(countrycd)) {
      if (!silent) window.alert(`${countrycd} 국가는 구글 주소검증을 지원하지 않습니다.`);
      return;
    }

    setValidating(true);
    setAddressHint(null);
    try {
      const result = await validateAddressWithGoogle(GMAPS_KEY, {
        addr3,
        addr2,
        addr1,
        zip,
        countryCode: countrycd,
      });
      if (!result) {
        if (!silent) window.alert('구글 주소검증에 실패했습니다. 주소를 다시 확인해주세요.');
        return;
      }
      if (result.isSame) {
        setAddressHint('구글 주소와 일치합니다.');
        if (!silent) window.alert('구글 주소검증 완료. 입력 주소가 추천 주소와 같습니다.');
        return;
      }
      setSuggestion({
        original: { addr3, addr2, addr1, zip },
        suggested: {
          addr3: result.suggestedAddr3,
          addr2: result.suggestedAddr2,
          addr1: result.suggestedAddr1,
          zip: result.suggestedZip,
          formattedAddress: result.formattedAddress,
        },
      });
    } finally {
      setValidating(false);
    }
  }, []);

  validateRef.current = triggerAddressValidation;

  function applySaved(item: OverseasSavedAddress) {
    setSelectedSavedId(String(item.id));
    const allowed = nationsRef.current.some((n) => n.nationcd === item.countrycd) || nationsRef.current.length === 0;
    if (!allowed) {
      window.alert(`${item.label} 의 국가 ${item.countrycd} 는 현재 배송방법으로 발송할 수 없습니다. 배송방법 또는 국가를 바꿔주세요.`);
    }
    setForm((prev) => ({
      ...prev,
      countrycd: allowed ? item.countrycd : prev.countrycd,
      receivename: item.recipient_name,
      receivetelno: item.recipient_phone,
      receivemail: item.recipient_email,
      receivezipcode: item.zipcode,
      receiveaddr1: item.addr1,
      receiveaddr2: item.addr2,
      receiveaddr3: item.addr3,
    }));
  }

  function applySender(item: OverseasSavedSender) {
    setSelectedSenderId(String(item.id));
    setForm((prev) => ({
      ...prev,
      sender_name: item.name,
      sender_tel: item.phone,
      sender_zipcode: item.zipcode,
      sender_addr1: item.addr1,
      sender_addr2: item.addr2,
      sender_addr3: item.addr3,
    }));
  }

  async function changeMethod(code: OverseasShippingPayload['shipping_method']) {
    setForm((prev) => ({
      ...prev,
      shipping_method: code,
      contents_type: code === 'KPACKET' ? 'parcel' : (prev.contents_type || 'parcel'),
    }));
    if (!token) return;
    try {
      const nationRes = await listOverseasNations(token, METHOD_PREMIUM[code]);
      const items = nationRes.items || [];
      setNations(items);
      setNationsFallback(!!nationRes.fallback);
      setNationQuery('');
      const current = formRef.current.countrycd;
      const ok = items.some((n) => n.nationcd === current);
      const nextCountry = ok ? current : (items[0]?.nationcd || '');
      if (!ok && current && nextCountry && current !== nextCountry) {
        window.alert(`${current} 는 이 배송방법 발송 가능 국가가 아닙니다. ${nextCountry} 로 바꿉니다.`);
      }
      setForm((prev) => ({
        ...prev,
        shipping_method: code,
        contents_type: code === 'KPACKET' ? 'parcel' : (prev.contents_type || 'parcel'),
        countrycd: nextCountry,
      }));
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  function updateItem(index: number, patch: Partial<OverseasInvoiceItem>) {
    setForm((prev) => ({
      ...prev,
      items: prev.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    }));
  }

  function pickCategory(index: number, cat: ItemCategory) {
    updateItem(index, {
      name_en: cat.id === 'other' ? '' : cat.name_en,
      hs_code: cat.hs_code,
      origin_country: cat.origin_country || 'KR',
    });
    setHsQuery((prev) => ({ ...prev, [index]: '' }));
    setHsOpen(null);
  }

  function searchHs(index: number, query: string) {
    setHsQuery((prev) => ({ ...prev, [index]: query }));
    setHsOpen(index);
    const local = searchItemCategories(query, savedHs).slice(0, 12);
    setHsMatches((prev) => ({ ...prev, [index]: local }));
    if (!token) return;
    window.clearTimeout(hsTimer.current[index]);
    hsTimer.current[index] = window.setTimeout(async () => {
      try {
        const res = await searchOverseasItemCategories(token, query);
        const remote: ItemCategory[] = (res.items || []).map((item) => ({
          id: item.id,
          name_ko: item.name_ko,
          name_en: item.name_en,
          hs_code: item.hs_code,
          group: item.group,
        }));
        const seen = new Set<string>();
        const merged: ItemCategory[] = [];
        for (const cat of [...local.filter((c) => c.saved), ...remote, ...local]) {
          const key = `${cat.hs_code}|${cat.name_en}|${cat.id}`;
          if (seen.has(key)) continue;
          seen.add(key);
          merged.push(cat);
        }
        setHsMatches((prev) => ({ ...prev, [index]: merged.slice(0, 20) }));
      } catch {
        /* keep local */
      }
    }, 220);
  }

  async function handleSaveAddressNow() {
    if (!token) return;
    setError(null);
    setSuccess(null);
    try {
      await saveOverseasAddress(token, {
        label: (form.save_address_label || form.receivename || '').trim() || '해외주소',
        recipient_name: form.receivename,
        recipient_phone: form.receivetelno,
        recipient_email: form.receivemail,
        countrycd: form.countrycd,
        zipcode: form.receivezipcode,
        addr1: form.receiveaddr1,
        addr2: form.receiveaddr2,
        addr3: form.receiveaddr3,
        is_default: !!form.save_address_default,
      });
      setSuccess('수취인을 저장했습니다.');
      await reloadSaved(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleSaveSenderNow() {
    if (!token) return;
    setError(null);
    setSuccess(null);
    try {
      await saveOverseasSender(token, {
        label: (form.save_sender_label || form.sender_name || '').trim() || defaultSender,
        name: (form.sender_name || '').trim() || defaultSender,
        phone: form.sender_tel || '',
        zipcode: form.sender_zipcode || '',
        addr1: form.sender_addr1 || '',
        addr2: form.sender_addr2 || '',
        addr3: form.sender_addr3 || '',
        is_default: !!form.save_sender_default,
      });
      setSuccess('발송인을 저장했습니다.');
      await reloadSaved(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleSaveHs(index: number) {
    if (!token) return;
    const item = form.items[index];
    setError(null);
    setSuccess(null);
    try {
      await saveOverseasHs(token, {
        label: item.name_en,
        name_ko: item.name_en,
        name_en: item.name_en,
        hs_code: item.hs_code || '',
        origin_country: item.origin_country || 'KR',
        group_name: '저장품목',
      });
      setSuccess(`HS ${item.hs_code} 를 저장했습니다. 다음 접수부터 검색됩니다.`);
      await reloadSaved(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleDeleteSaved() {
    if (!token || !selectedSavedId) return;
    if (!window.confirm('선택한 저장 주소를 삭제할까요?')) return;
    try {
      await deleteOverseasSavedAddress(token, Number(selectedSavedId));
      setSelectedSavedId('');
      await reloadSaved(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleDeleteSavedSender() {
    if (!token || !selectedSenderId) return;
    if (!window.confirm('선택한 발송인을 삭제할까요?')) return;
    try {
      await deleteOverseasSavedSender(token, Number(selectedSenderId));
      setSelectedSenderId('');
      await reloadSaved(token);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function handleSubmit() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    setPrintId(null);
    try {
      const previewRes = await previewOverseasShipping(token, form);
      const p = previewRes.preview;
      const feeText = p.expected_fee != null ? `${p.expected_fee.toLocaleString()}원` : '조회 실패(접수는 가능)';
      const duty = p.duty;
      const dutyLine = duty?.dutyPrepaid && duty.depositKrw
        ? `\n관세 선납(DDP): ${duty.depositKrw.toLocaleString()}원` +
          (duty.estimateUsd ? ` (USD ${duty.estimateUsd.toFixed(2)})` : '') +
          (duty.ddpPath === 'premium' ? ' · FedEx DDP' : '') +
          (duty.bufferKrw ? `\n버퍼 10%: ${duty.bufferKrw.toLocaleString()}원 (DDP에 포함)` : '')
        : duty?.ineligibleReason
          ? `\n관세 선납: ${duty.ineligibleReason}`
          : '';
      const totalLine = p.expected_fee != null && duty?.dutyPrepaid
        ? `\n합계: ${(p.expected_fee + duty.depositKrw).toLocaleString()}원`
        : '';
      const mode = liveReady && !form.test_mode ? '실접수' : '테스트 접수';
      const ok = window.confirm(
        `${mode} 할까요?\n\n` +
          `발송인: ${p.sender_name}\n` +
          `배송: ${p.shipping_method_name} ${p.contents_label || '화물'} / ${p.countrycd}\n` +
          `수취인: ${p.recipient_name}\n` +
          `주소: ${p.recipient_addr}\n` +
          (p.contents_type === 'document'
            ? `무게: ${p.totweight}g (서류)\n`
            : `무게: ${p.totweight}g · ${p.boxlength}×${p.boxwidth}×${p.boxheight}cm\n`) +
          `예상요금: ${feeText}${dutyLine}${totalLine}\n\n결제 없이 우체국에 바로 접수됩니다.`,
      );
      if (!ok) return;
      const result = await createOverseasShipping(token, form);
      if (result.id) setPrintId(result.id);
      if (result.duplicate_guard) {
        setSuccess(`오늘 같은 수취인으로 이미 접수된 건이 있습니다. 등기번호 ${result.tracking_no}`);
      } else {
        const label = result.is_test ? '테스트 접수' : '우체국 접수';
        setSuccess(`${label} 완료. 등기번호 ${result.tracking_no}${result.ems_fee ? ` · 요금 ${Number(result.ems_fee).toLocaleString()}원` : ''}. 출력서류는 아래 버튼 또는 접수목록에서 다시 인쇄할 수 있습니다.`);
        const senderName = form.sender_name || defaultSender;
        const next = emptyForm(senderName);
        next.sender_zipcode = form.sender_zipcode;
        next.sender_addr1 = form.sender_addr1;
        next.sender_addr2 = form.sender_addr2;
        next.sender_addr3 = form.sender_addr3;
        next.sender_tel = form.sender_tel;
        setForm(next);
        setSelectedSavedId('');
        await reloadSaved(token);
      }
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading text="해외배송 접수 로딩 중..." />;

  const q = nationQuery.trim().toLowerCase();
  const filteredNations = q
    ? nations.filter((n) => `${n.nationcd} ${n.nationnm} ${n.nationfn}`.toLowerCase().includes(q))
    : nations;
  const nationOptions = filteredNations.some((n) => n.nationcd === form.countrycd)
    ? filteredNations
    : nations.filter((n) => n.nationcd === form.countrycd).concat(filteredNations);

  const methodName = methods.find((m) => m.code === form.shipping_method)?.name || form.shipping_method;
  const canDocument = form.shipping_method !== 'KPACKET';
  const isDocument = canDocument && form.contents_type === 'document';
  const selectedSaved = savedAddresses.find((a) => String(a.id) === selectedSavedId);

  function setContentsType(kind: 'parcel' | 'document') {
    if (kind === 'document' && !canDocument) {
      window.alert('K-Packet은 화물만 접수할 수 있습니다.');
      return;
    }
    setForm((prev) => ({ ...prev, contents_type: kind }));
  }

  return (
    <div className="overseas-page">
      <PageHeader
        title="해외배송 접수"
        subtitle="창고에서 EMS / EMS 프리미엄 / K-Packet를 결제 없이 바로 접수합니다."
      />

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}
      {printId && (
        <p style={{ margin: '0 0 1rem' }}>
          <a href={`/overseas-print/${printId}`} className="btn btn-primary" target="_blank" rel="noreferrer">
            출력서류 인쇄
          </a>
        </p>
      )}
      {suggestion && (
        <AddressSuggestionDialog
          original={suggestion.original}
          suggested={suggestion.suggested}
          onKeepOriginal={() => setSuggestion(null)}
          onUseSuggested={() => {
            setForm((prev) => ({
              ...prev,
              receiveaddr3: suggestion.suggested.addr3 || prev.receiveaddr3,
              receiveaddr2: suggestion.suggested.addr2 || prev.receiveaddr2,
              receiveaddr1: suggestion.suggested.addr1 || prev.receiveaddr1,
              receivezipcode: suggestion.suggested.zip || prev.receivezipcode,
            }));
            setSuggestion(null);
          }}
        />
      )}
      {recipientPickerOpen && (
        <OverseasRecipientPickerModal
          items={savedAddresses}
          selectedId={selectedSavedId}
          onClose={() => setRecipientPickerOpen(false)}
          onSelect={(item) => {
            applySaved(item);
            setRecipientPickerOpen(false);
          }}
        />
      )}

      <div className="overseas-intake">
      <div>
      <Card title="접수 정보">
        <p className="text-muted" style={{ marginBottom: '1rem' }}>
          {liveReady ? `실접수 가능 · 기본 발송지 ${senderAddr}` : `EMS 키가 없어 테스트 접수로 저장됩니다. 기본 발송지 ${senderAddr}`}
          {GMAPS_KEY ? ' · 구글 주소검색 가능' : ' · 구글 주소키 없음(직접 입력)'}
        </p>

        <FormSection title="발송인" first>
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ flex: '1 1 240px' }}>
            저장된 발송인
            <select
              style={inputStyle}
              value={selectedSenderId}
              onChange={(e) => {
                const item = savedSenders.find((a) => String(a.id) === e.target.value);
                if (item) applySender(item);
                else setSelectedSenderId('');
              }}
            >
              <option value="">{savedSenders.length ? '발송인을 선택하면 자동입력됩니다' : '저장된 발송인이 없습니다'}</option>
              {savedSenders.map((a) => (
                <option key={a.id} value={String(a.id)}>
                  {a.is_default ? '[기본] ' : ''}{a.label} · {a.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-secondary" onClick={handleSaveSenderNow}>발송인 저장</button>
          <button type="button" className="btn btn-secondary" disabled={!selectedSenderId} onClick={handleDeleteSavedSender}>삭제</button>
          <a href="/overseas-senders" className="btn btn-secondary">목록</a>
        </div>
        <div style={fieldGrid}>
          <label>
            발송인 이름
            <input
              style={inputStyle}
              value={form.sender_name || ''}
              placeholder={defaultSender}
              onChange={(e) => setForm((p) => ({ ...p, sender_name: e.target.value }))}
            />
          </label>
          <label>
            발송인 전화
            <input
              style={inputStyle}
              value={form.sender_tel || ''}
              placeholder="+8210..."
              onChange={(e) => setForm((p) => ({ ...p, sender_tel: e.target.value }))}
            />
          </label>
          <label>
            발송인 우편번호
            <input
              style={inputStyle}
              value={form.sender_zipcode || ''}
              onChange={(e) => setForm((p) => ({ ...p, sender_zipcode: e.target.value }))}
            />
          </label>
          <label>
            발송인 시/도
            <input
              style={inputStyle}
              value={form.sender_addr1 || ''}
              onChange={(e) => setForm((p) => ({ ...p, sender_addr1: e.target.value }))}
            />
          </label>
          <label>
            발송인 구/군
            <input
              style={inputStyle}
              value={form.sender_addr2 || ''}
              onChange={(e) => setForm((p) => ({ ...p, sender_addr2: e.target.value }))}
            />
          </label>
          <label>
            발송인 상세주소
            <input
              style={inputStyle}
              value={form.sender_addr3 || ''}
              onChange={(e) => setForm((p) => ({ ...p, sender_addr3: e.target.value }))}
            />
          </label>
          <label>
            발송인 별칭
            <input
              style={inputStyle}
              value={form.save_sender_label || ''}
              placeholder="스프링풀필먼트"
              onChange={(e) => setForm((p) => ({ ...p, save_sender_label: e.target.value }))}
            />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '1.4rem' }}>
            <input
              type="checkbox"
              checked={!!form.save_sender}
              onChange={(e) => setForm((p) => ({ ...p, save_sender: e.target.checked }))}
            />
            접수와 함께 발송인 저장
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              checked={!!form.save_sender_default}
              onChange={(e) => setForm((p) => ({ ...p, save_sender_default: e.target.checked }))}
            />
            기본 발송인으로 지정
          </label>
        </div>
        </FormSection>

        <FormSection title="수취인">
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ flex: '1 1 260px' }}>
            저장된 수취인
            <button
              type="button"
              onClick={() => setRecipientPickerOpen(true)}
              style={{
                ...inputStyle,
                textAlign: 'left',
                background: '#fff',
                cursor: 'pointer',
                color: selectedSaved ? 'inherit' : 'var(--text-muted)',
              }}
            >
              {selectedSaved
                ? `${selectedSaved.is_default ? '[기본] ' : ''}${selectedSaved.label} · ${selectedSaved.countrycd} · ${selectedSaved.recipient_name}`
                : (savedAddresses.length ? '목록에서 수취인을 선택하세요' : '저장된 수취인이 없습니다')}
            </button>
          </label>
          <button type="button" className="btn btn-primary" onClick={() => setRecipientPickerOpen(true)}>목록</button>
          <button type="button" className="btn btn-secondary" onClick={handleSaveAddressNow}>수취인 저장</button>
          <button type="button" className="btn btn-secondary" disabled={!selectedSavedId} onClick={handleDeleteSaved}>삭제</button>
        </div>

        <div style={fieldGrid}>
          <label>
            배송방법
            <select
              style={inputStyle}
              value={form.shipping_method}
              onChange={(e) => changeMethod(e.target.value as OverseasShippingPayload['shipping_method'])}
            >
              {(methods.length ? methods : [
                { code: 'EMS', name: 'EMS', desc: '' },
                { code: 'EMS_PREMIUM', name: 'EMS 프리미엄', desc: '' },
                { code: 'KPACKET', name: 'K-Packet', desc: '' },
              ]).map((m) => (
                <option key={m.code} value={m.code}>
                  {m.name}{m.desc ? ` · ${m.desc}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label>
            국가
            <input
              style={{ ...inputStyle, marginBottom: '0.35rem' }}
              value={nationQuery}
              placeholder="국가명·코드 검색 (예: 일본, JP)"
              onChange={(e) => setNationQuery(e.target.value)}
            />
            <select
              style={inputStyle}
              value={form.countrycd}
              onChange={(e) => setForm((p) => ({ ...p, countrycd: e.target.value }))}
            >
              {nationOptions.length === 0 ? (
                <option value={form.countrycd || ''}>발송 가능 국가가 없습니다</option>
              ) : (
                nationOptions.map((n) => (
                  <option key={n.nationcd} value={n.nationcd}>
                    {n.nationnm || n.nationfn || n.nationcd} ({n.nationcd})
                  </option>
                ))
              )}
            </select>
            <span className="text-muted" style={{ fontSize: '0.78rem' }}>
              {nationsFallback ? '우체국 국가목록을 받지 못해 임시 목록입니다.' : '우체국 API 발송가능국'} · {nations.length}개
            </span>
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>우편물 종류</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn"
                onClick={() => setContentsType('parcel')}
                style={{
                  flex: 1,
                  border: !isDocument ? '2px solid #0f172a' : '1px solid var(--border)',
                  background: !isDocument ? '#0f172a' : '#fff',
                  color: !isDocument ? '#fff' : 'inherit',
                  fontWeight: 700,
                }}
              >
                화물 (비서류)
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setContentsType('document')}
                disabled={!canDocument}
                style={{
                  flex: 1,
                  border: isDocument ? '2px solid #0f172a' : '1px solid var(--border)',
                  background: isDocument ? '#0f172a' : '#fff',
                  color: isDocument ? '#fff' : 'inherit',
                  fontWeight: 700,
                  opacity: canDocument ? 1 : 0.45,
                }}
              >
                서류
              </button>
            </div>
            <span className="text-muted" style={{ fontSize: '0.78rem' }}>
              {canDocument
                ? '화물·서류 요금이 다릅니다. 선택한 유형으로 접수됩니다.'
                : 'K-Packet은 화물만 가능합니다.'}
            </span>
          </div>
          <label>
            수취인 이름 (영문)
            <input
              style={inputStyle}
              value={form.receivename}
              placeholder="Hong Gildong"
              onChange={(e) => setForm((p) => ({ ...p, receivename: e.target.value }))}
            />
          </label>
          <label>
            연락처
            <input
              style={inputStyle}
              value={form.receivetelno}
              placeholder="+819012345678"
              onChange={(e) => setForm((p) => ({ ...p, receivetelno: e.target.value }))}
            />
          </label>
          <label>
            이메일
            <input
              style={inputStyle}
              value={form.receivemail}
              onChange={(e) => setForm((p) => ({ ...p, receivemail: e.target.value }))}
            />
          </label>
          <label>
            우편번호
            <input
              style={inputStyle}
              value={form.receivezipcode}
              onChange={(e) => setForm((p) => ({ ...p, receivezipcode: e.target.value }))}
              onBlur={() => void triggerAddressValidation({ silent: true })}
            />
          </label>
          <label>
            주/도 (영문){validating ? ' · 확인 중...' : ''}
            <input
              style={inputStyle}
              value={form.receiveaddr1}
              placeholder="Tokyo"
              onChange={(e) => setForm((p) => ({ ...p, receiveaddr1: e.target.value }))}
            />
          </label>
          <label>
            시/군 (영문)
            <input
              style={inputStyle}
              value={form.receiveaddr2}
              placeholder="Shibuya-ku"
              onChange={(e) => setForm((p) => ({ ...p, receiveaddr2: e.target.value }))}
            />
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <label>
              상세주소 (영문){GMAPS_KEY ? ' · 구글 검색' : ''}{validating ? ' · 검증 중...' : ''}
              <input
                ref={addr3Ref}
                style={inputStyle}
                value={form.receiveaddr3}
                placeholder="1-2-3 Example Street Apt 101"
                autoComplete="off"
                onChange={(e) => setForm((p) => ({ ...p, receiveaddr3: e.target.value }))}
                onBlur={() => void triggerAddressValidation({ silent: true })}
              />
            </label>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginTop: '0.55rem' }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void triggerAddressValidation()}
                disabled={validating || !GMAPS_KEY}
                style={{ minWidth: 140 }}
              >
                {validating ? '검증 중...' : '구글 주소 검증'}
              </button>
              {addressHint && <span className="text-muted">{addressHint}</span>}
              {!GMAPS_KEY && <span className="text-muted">구글 주소키가 없어 검증할 수 없습니다.</span>}
            </div>
          </div>
          <label>
            주소록 별칭
            <input
              style={inputStyle}
              value={form.save_address_label || ''}
              placeholder="일본 오사카 창고"
              onChange={(e) => setForm((p) => ({ ...p, save_address_label: e.target.value }))}
            />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '1.4rem' }}>
            <input
              type="checkbox"
              checked={!!form.save_address}
              onChange={(e) => setForm((p) => ({ ...p, save_address: e.target.checked }))}
            />
            접수와 함께 수취인 저장
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              checked={!!form.save_address_default}
              onChange={(e) => setForm((p) => ({ ...p, save_address_default: e.target.checked }))}
            />
            기본 수취인으로 지정
          </label>
        </div>
        </FormSection>

        <FormSection title="중량 · 사이즈">
        <div style={{
          display: 'grid',
          gridTemplateColumns: isDocument ? '1fr 1fr' : '1.2fr repeat(3, 1fr)',
          gap: '0.75rem',
        }}>
          <label>
            총중량 (g)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.totweight}
              onChange={(e) => setForm((p) => ({ ...p, totweight: parseInt(e.target.value, 10) || 0 }))}
            />
            {isDocument && (
              <span className="text-muted" style={{ fontSize: '0.78rem' }}>
                서류 요금은 300g~2kg 구간으로 계산됩니다
                {form.shipping_method === 'EMS_PREMIUM' ? ' · 프리미엄 서류 최대 500g' : ' · EMS 서류 최대 2kg'}
              </span>
            )}
          </label>
          {isDocument ? (
            <div className="text-muted" style={{ fontSize: '0.85rem', alignSelf: 'center' }}>
              서류는 박스 크기·부피중량을 적용하지 않습니다.
            </div>
          ) : (
            <>
          <label>
            가로 (cm)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.boxlength}
              onChange={(e) => setForm((p) => ({ ...p, boxlength: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
          <label>
            세로 (cm)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.boxwidth}
              onChange={(e) => setForm((p) => ({ ...p, boxwidth: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
          <label>
            높이 (cm)
            <input
              type="number"
              min={1}
              style={inputStyle}
              value={form.boxheight}
              onChange={(e) => setForm((p) => ({ ...p, boxheight: parseInt(e.target.value, 10) || 0 }))}
            />
          </label>
            </>
          )}
          <label style={{ gridColumn: '1 / -1' }}>
            메모
            <input
              style={inputStyle}
              value={form.notes}
              onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
            />
          </label>
        </div>
        </FormSection>
      </Card>

      <Card title="세관 인보이스">
        <p className="text-muted" style={{ marginBottom: '0.75rem' }}>
          {isDocument
            ? '서류도 내용품명(영문)을 입력하세요. 예: Documents. '
            : '한글·영문·HS 6자리로 검색하면 저장된 품목과 HS 목록이 나옵니다. '}
          <a href="/overseas-hs-codes">HS코드 목록</a>
        </p>
        {form.items.map((item, i) => {
          const q = hsQuery[i] ?? '';
          const matches = (hsMatches[i] || searchItemCategories(q || item.name_en || item.hs_code || '', savedHs)).slice(0, 12);
          return (
            <div
              key={i}
              className="overseas-item-row"
            >
              <label style={{ position: 'relative' }}>
                품목 (한글/영문/HS 검색)
                <input
                  style={inputStyle}
                  value={item.name_en}
                  placeholder="의류, Clothing, 610910"
                  onFocus={() => searchHs(i, q || item.name_en || item.hs_code || '')}
                  onChange={(e) => {
                    updateItem(i, { name_en: e.target.value });
                    searchHs(i, e.target.value);
                    const hit = [...savedHs, ...ITEM_CATEGORIES].find((c) => c.name_en.toLowerCase() === e.target.value.toLowerCase());
                    if (hit?.hs_code) updateItem(i, { name_en: e.target.value, hs_code: hit.hs_code, origin_country: hit.origin_country || item.origin_country });
                  }}
                />
                {hsOpen === i && matches.length > 0 && (
                  <div style={{
                    position: 'absolute',
                    zIndex: 20,
                    top: '100%',
                    left: 0,
                    right: 0,
                    background: '#fff',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    maxHeight: 220,
                    overflowY: 'auto',
                    boxShadow: 'var(--shadow-md)',
                  }}>
                    {matches.map((cat) => (
                      <button
                        key={cat.id}
                        type="button"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => pickCategory(i, cat)}
                        style={{
                          display: 'block',
                          width: '100%',
                          textAlign: 'left',
                          padding: '0.45rem 0.7rem',
                          border: 0,
                          background: cat.name_en === item.name_en ? 'var(--color-brand-light)' : '#fff',
                          cursor: 'pointer',
                        }}
                      >
                        {cat.saved ? '[저장] ' : ''}{cat.name_ko} · {cat.name_en}
                        {cat.hs_code ? ` · HS ${cat.hs_code}` : ''}
                      </button>
                    ))}
                  </div>
                )}
              </label>
              <label>
                수량
                <input
                  type="number"
                  min={1}
                  style={inputStyle}
                  value={item.quantity}
                  onChange={(e) => updateItem(i, { quantity: parseInt(e.target.value, 10) || 1 })}
                />
              </label>
              <label>
                단가 USD
                <input
                  type="number"
                  min={0.01}
                  step="0.01"
                  style={inputStyle}
                  value={item.unit_price_usd}
                  onChange={(e) => updateItem(i, { unit_price_usd: parseFloat(e.target.value) || 0 })}
                />
              </label>
              <label>
                HS코드
                <input
                  style={inputStyle}
                  value={item.hs_code || ''}
                  placeholder="6자리"
                  onFocus={() => searchHs(i, item.hs_code || q || item.name_en || '')}
                  onChange={(e) => {
                    const hs = e.target.value.replace(/\D/g, '');
                    updateItem(i, { hs_code: hs });
                    searchHs(i, hs);
                    const hit = [...savedHs, ...ITEM_CATEGORIES].find((c) => c.hs_code === hs);
                    if (hit) updateItem(i, { hs_code: hs, name_en: item.name_en || hit.name_en });
                  }}
                />
              </label>
              <label>
                원산지
                <input style={inputStyle} value={item.origin_country || 'KR'} onChange={(e) => updateItem(i, { origin_country: e.target.value })} />
              </label>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleSaveHs(i)}
              >
                HS 저장
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={form.items.length <= 1}
                onClick={() => setForm((p) => ({ ...p, items: p.items.filter((_, idx) => idx !== i) }))}
              >
                삭제
              </button>
            </div>
          );
        })}
        <button type="button" className="btn btn-secondary" onClick={() => setForm((p) => ({ ...p, items: [...p.items, newItem()] }))}>
          품목 추가
        </button>
      </Card>

      </div>
      <aside className="overseas-intake-aside">
      <Card title="배송요금">
        <div style={{
          display: 'grid',
          gap: 8,
          background: quoteError && quoteFee == null ? '#fef2f2' : 'transparent',
          borderRadius: 8,
        }}>
          <button
            type="button"
            className={`fee-choice${!isDocument ? ' is-selected' : ''}`}
            onClick={() => setContentsType('parcel')}
          >
            <span>
              <span className="fee-choice-label">화물</span>
            </span>
            {quoteLoading && !quoteParcel ? (
              <span className="text-muted">조회 중</span>
            ) : quoteParcel && !quoteParcel.ok ? (
              <span style={{ color: '#b91c1c', fontWeight: 600, fontSize: '0.8rem' }}>{quoteParcel.error}</span>
            ) : quoteParcel?.totalFee != null ? (
              <span className="fee-choice-price">{quoteParcel.totalFee.toLocaleString()}원</span>
            ) : (
              <span className="text-muted">중량 입력</span>
            )}
          </button>
          {canDocument && (
            <button
              type="button"
              className={`fee-choice${isDocument ? ' is-selected' : ''}`}
              onClick={() => setContentsType('document')}
            >
              <span>
                <span className="fee-choice-label">서류</span>
                {quoteDocument?.ok && quoteDocument.totweight ? (
                  <span className="fee-choice-note">{quoteDocument.totweight}g 구간</span>
                ) : null}
              </span>
              {quoteLoading && !quoteDocument ? (
                <span className="text-muted">조회 중</span>
              ) : quoteDocument && !quoteDocument.ok ? (
                <span style={{ color: '#b91c1c', fontWeight: 600, fontSize: '0.8rem' }}>{quoteDocument.error}</span>
              ) : quoteDocument?.totalFee != null ? (
                <span className="fee-choice-price">{quoteDocument.totalFee.toLocaleString()}원</span>
              ) : (
                <span className="text-muted">중량 입력</span>
              )}
            </button>
          )}
        </div>
        {quoteLoading && quoteFee == null ? (
          <div style={{ marginTop: 8, fontSize: '0.9rem' }}>요금 조회 중...</div>
        ) : quoteError && quoteFee == null ? (
          <div style={{ marginTop: 8, color: '#b91c1c', fontWeight: 600 }}>{quoteError}</div>
        ) : quoteFee != null ? (
          <div className="fee-lines">
            <div className="fee-line">
              <span>우체국 배송비</span>
              <strong>{quoteFee.toLocaleString()}원</strong>
            </div>
            {quoteDuty?.dutyPrepaid && quoteDuty.depositKrw > 0 && (
              <>
                <div className="fee-line">
                  <span>
                    관세 선납
                    <span className="fee-choice-note">
                      {quoteDuty.ddpPath === 'premium' ? 'FedEx' : '우체국'}
                      {quoteDuty.estimateUsd > 0 ? ` · USD ${quoteDuty.estimateUsd.toFixed(2)}` : ''}
                    </span>
                  </span>
                  <strong>{quoteDuty.depositKrw.toLocaleString()}원</strong>
                </div>
                {quoteDuty.bufferKrw ? (
                  <div className="fee-line is-sub">
                    <span>버퍼 10% (포함)</span>
                    <strong>{quoteDuty.bufferKrw.toLocaleString()}원</strong>
                  </div>
                ) : null}
              </>
            )}
            {quoteDuty?.ineligibleReason && (
              <div style={{ fontSize: '0.8rem', color: '#b45309', fontWeight: 600 }}>
                {quoteDuty.ineligibleReason}
              </div>
            )}
            {quoteDuty && ['US', 'GB'].includes(form.countrycd) && !(quoteDuty.dutyPrepaid || quoteDuty.ineligibleReason) && (
              <div className="text-muted" style={{ fontSize: '0.8rem' }}>
                신고가액을 입력하면 관세 선납이 나옵니다.
              </div>
            )}
            <div className="fee-line is-total">
              <span>합계</span>
              <strong>{(quoteTotal ?? quoteFee).toLocaleString()}원</strong>
            </div>
            <div className="fee-meta">
              {isDocument ? '서류' : '화물'} · {methodName} · {form.countrycd} · {form.totweight}g
              <br />
              {quoteLive ? '우체국 요금' : '테스트 요금'} · 후납 · 고객 결제 없음
            </div>
          </div>
        ) : (
          <div className="text-muted" style={{ marginTop: 8 }}>중량을 입력하면 우체국 요금이 표시됩니다.</div>
        )}
      </Card>

      <Card title="접수">
        {liveReady && (
          <label style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={!!form.test_mode}
              onChange={(e) => setForm((p) => ({ ...p, test_mode: e.target.checked }))}
            />
            테스트 접수 (우체국에 실제 신청하지 않음)
          </label>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
          <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={saving} style={{ width: '100%' }}>
            {saving ? '접수 중...' : liveReady && !form.test_mode ? '해외배송 접수' : '테스트 접수'}
          </button>
          <div className="fee-links">
            <a href="/overseas-shipping-list" className="btn btn-secondary">접수목록</a>
            <a href="/overseas-senders" className="btn btn-secondary">발송인</a>
            <a href="/overseas-recipients" className="btn btn-secondary">수취인</a>
            <a href="/overseas-hs-codes" className="btn btn-secondary">HS코드</a>
          </div>
        </div>
      </Card>
      </aside>
      </div>
    </div>
  );
}
