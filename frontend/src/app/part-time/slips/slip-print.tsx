'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/ui/button';
import { API, hoursText, won } from '../model';

export interface PrintSlipLine {
  work_date: string;
  hours: number;
  start_time?: string;
  end_time?: string;
  shift_label?: string;
  pay: number;
}

export interface PrintSlip {
  worker_id: number;
  name: string;
  reported: boolean;
  hourly_wage: number;
  work_days: number;
  average_hours: number;
  basic_hours: number;
  base_pay: number;
  weekly_holiday_hours: number;
  weekly_holiday_pay: number;
  taxable_pay: number;
  nontaxable_pay: number;
  income_tax: number;
  local_tax: number;
  employment_insurance: number;
  pension: number;
  health: number;
  care: number;
  deduction_total: number;
  net_pay: number;
  lines: PrintSlipLine[];
}

const PRINT_STYLE = `
.slip-print-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  overflow: auto;
  background: rgba(16, 18, 32, 0.62);
  padding: 16px 12px 40px;
}
.slip-print-bar {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  width: min(210mm, 100%);
  margin: 0 auto 12px;
}
.slip-sheet {
  width: min(210mm, 100%);
  min-height: 277mm;
  margin: 0 auto 16px;
  box-sizing: border-box;
  background: #fff;
  color: #111;
  padding: 14mm 14mm 16mm;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  font-size: 12px;
  line-height: 1.45;
}
.slip-sheet h1 {
  margin: 0;
  font-size: 22px;
  letter-spacing: 0.12em;
  text-align: center;
}
.slip-company, .slip-period {
  text-align: center;
  color: #374151;
}
.slip-company { font-weight: 700; font-size: 14px; }
.slip-who {
  display: flex;
  justify-content: space-between;
  margin: 14px 0 10px;
  padding: 8px 10px;
  border: 1px solid #111;
}
.slip-sheet table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 10px;
}
.slip-sheet th, .slip-sheet td {
  border: 1px solid #d1d5db;
  padding: 4px 8px;
  text-align: left;
}
.slip-sheet td:last-child, .slip-sheet th:last-child { text-align: right; }
.slip-sheet th { background: #f3f4f6; font-weight: 700; }
.slip-net {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 0 12px;
  padding: 10px 12px;
  border: 2px solid #111;
  font-size: 16px;
  font-weight: 800;
}
.slip-foot { margin: 8px 0 0; color: #6b7280; font-size: 11px; }
@media print {
  body * { visibility: hidden !important; }
  #part-time-slip-print, #part-time-slip-print * { visibility: visible !important; }
  #part-time-slip-print { position: absolute; left: 0; top: 0; width: 100%; background: #fff; }
  .slip-print-bar { display: none !important; }
  .slip-print-backdrop { position: static; background: #fff; padding: 0; overflow: visible; }
  .slip-sheet {
    width: auto;
    min-height: 0;
    margin: 0;
    padding: 0;
    box-shadow: none;
    page-break-after: always;
    break-after: page;
  }
  .slip-sheet:last-child { page-break-after: auto; break-after: auto; }
  @page { size: A4 portrait; margin: 12mm; }
}
`;

function moneyRows(slip: PrintSlip) {
  const pay = [
    ['근무수당', slip.base_pay],
    ['주휴수당', slip.weekly_holiday_pay],
    ['총지급액', slip.taxable_pay + slip.nontaxable_pay],
  ] as const;
  const cuts = slip.reported
    ? [
        ['소득세', slip.income_tax],
        ['지방소득세', slip.local_tax],
        ['고용보험', slip.employment_insurance],
        ['국민연금', slip.pension],
        ['건강보험', slip.health],
        ['장기요양보험', slip.care],
      ]
    : [
        ['소득세 3%', slip.income_tax],
        ['지방소득세 0.3%', slip.local_tax],
      ];
  return { pay, cuts: [...cuts, ['공제합계', slip.deduction_total]] as const };
}

function SlipSheet({ slip, year, month, company }: { slip: PrintSlip; year: number; month: number; company: string }) {
  const { pay, cuts } = moneyRows(slip);
  return (
    <article className="slip-sheet">
      <div className="slip-company">{company}</div>
      <h1>급여명세서</h1>
      <div className="slip-period">{year}년 {month}월</div>
      <div className="slip-who">
        <span>성명 <strong>{slip.name}</strong></span>
        <span>시급 {won(slip.hourly_wage)}</span>
        <span>근로 {slip.work_days}일 / {hoursText(slip.basic_hours)}시간</span>
      </div>
      <table>
        <thead><tr><th>지급 항목</th><th>금액</th></tr></thead>
        <tbody>
          {pay.map(([label, value]) => (
            <tr key={label}><td>{label}</td><td>{won(value)}</td></tr>
          ))}
        </tbody>
      </table>
      <table>
        <thead><tr><th>공제 항목</th><th>금액</th></tr></thead>
        <tbody>
          {cuts.map(([label, value]) => (
            <tr key={label}><td>{label}</td><td>{won(value)}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="slip-net">
        <span>실지급액</span>
        <span>{won(slip.net_pay)}</span>
      </div>
      <table>
        <thead>
          <tr><th>근무일</th><th>근무시간</th><th>시간</th><th>근무수당</th></tr>
        </thead>
        <tbody>
          {slip.lines.map((line) => (
            <tr key={line.work_date}>
              <td>{line.work_date}</td>
              <td style={{ textAlign: 'left' }}>
                {line.shift_label || [line.start_time, line.end_time].filter(Boolean).join('~') || '—'}
              </td>
              <td>{hoursText(line.hours)}</td>
              <td>{won(line.pay)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="slip-foot">
        {slip.reported
          ? '실지급액은 총지급액에서 일용근로소득세와 근로자 보험료를 뺀 금액입니다.'
          : '실지급액은 총지급액에서 소득세 3%와 지방소득세 0.3%를 뺀 금액입니다. 4대보험은 빼지 않습니다.'}
      </p>
    </article>
  );
}

export function PartTimeSlipPrint({
  slips,
  year,
  month,
  onClose,
}: {
  slips: PrintSlip[];
  year: number;
  month: number;
  onClose: () => void;
}) {
  const [company, setCompany] = useState('틸리언');

  useEffect(() => {
    const style = document.createElement('style');
    style.setAttribute('data-part-time-slip-print', '1');
    style.textContent = PRINT_STYLE;
    document.head.appendChild(style);
    fetch(`${API}/settings/company`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.company_name) setCompany(data.company_name);
      })
      .catch(() => {});
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => {
      style.remove();
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return createPortal(
    <div className="slip-print-backdrop" role="dialog" aria-modal="true" aria-label="급여명세서 출력">
      <div className="slip-print-bar">
        <Button type="button" variant="primary" onClick={() => window.print()}>인쇄</Button>
        <Button type="button" variant="secondary" onClick={onClose}>닫기</Button>
      </div>
      <div id="part-time-slip-print">
        {slips.map((slip) => (
          <SlipSheet key={slip.worker_id} slip={slip} year={year} month={month} company={company} />
        ))}
      </div>
    </div>,
    document.body,
  );
}
