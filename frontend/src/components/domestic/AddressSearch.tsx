'use client';

import { useState } from 'react';
import { openDaumPostcode } from '@/lib/daum-postcode';

export function AddressSearch({
  zipId,
  addrId,
  detailId,
  zip,
  addr1,
  addr2,
  zipError,
  addrError,
  detailError,
  disabled,
  onDetail,
  onZip,
  onAddr,
  onPick,
  onError,
}: {
  zipId: string;
  addrId: string;
  detailId: string;
  zip: string;
  addr1: string;
  addr2: string;
  zipError?: string;
  addrError?: string;
  detailError?: string;
  disabled?: boolean;
  onDetail: (value: string) => void;
  onZip: (value: string) => void;
  onAddr: (value: string) => void;
  onPick: (value: { zip: string; addr1: string }) => void;
  onError: (message: string) => void;
}) {
  const [searching, setSearching] = useState(false);
  const [manual, setManual] = useState(false);

  async function search() {
    if (searching || disabled) return;
    setSearching(true);
    try {
      await openDaumPostcode((picked) => {
        setManual(false);
        onPick(picked);
      });
    } catch (err) {
      setManual(true);
      onError(err instanceof Error ? err.message : '주소 검색을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="domestic-address">
      <div className="domestic-address-line">
        <label className={`domestic-field w-zip${zipError ? ' is-invalid' : ''}`} htmlFor={zipId}>
          우편번호
          <input
            id={zipId}
            value={zip}
            readOnly={!manual}
            aria-invalid={Boolean(zipError)}
            aria-describedby={zipError ? `${zipId}-error` : undefined}
            onChange={(event) => onZip(event.target.value)}
          />
          {zipError ? <span className="domestic-field-error" id={`${zipId}-error`}>{zipError}</span> : null}
        </label>
        <label className={`domestic-field w-addr${addrError ? ' is-invalid' : ''}`} htmlFor={addrId}>
          주소
          <input
            id={addrId}
            value={addr1}
            readOnly={!manual}
            aria-invalid={Boolean(addrError)}
            aria-describedby={addrError ? `${addrId}-error` : undefined}
            onChange={(event) => onAddr(event.target.value)}
          />
          {addrError ? <span className="domestic-field-error" id={`${addrId}-error`}>{addrError}</span> : null}
        </label>
        <button type="button" className="btn btn-secondary" disabled={disabled || searching} onClick={() => void search()}>
          {searching ? '검색 준비...' : '주소 검색'}
        </button>
        {manual ? null : (
          <button type="button" className="btn btn-ghost" disabled={disabled} onClick={() => setManual(true)}>
            직접 입력
          </button>
        )}
      </div>
      <label className={`domestic-field w-detail${detailError ? ' is-invalid' : ''}`} htmlFor={detailId}>
        상세주소
        <input
          id={detailId}
          value={addr2}
          aria-invalid={Boolean(detailError)}
          aria-describedby={detailError ? `${detailId}-error` : undefined}
          onChange={(event) => onDetail(event.target.value)}
        />
        {detailError ? <span className="domestic-field-error" id={`${detailId}-error`}>{detailError}</span> : null}
      </label>
    </div>
  );
}
