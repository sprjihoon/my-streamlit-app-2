import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';

export function DateRangeControl({
  from,
  to,
  onFrom,
  onTo,
}: {
  from: string;
  to: string;
  onFrom: (value: string) => void;
  onTo: (value: string) => void;
}) {
  return (
    <>
      <Field label="시작일" className="tw-mb-0">
        <Input type="date" value={from} onChange={(e) => onFrom(e.target.value)} />
      </Field>
      <Field label="종료일" className="tw-mb-0">
        <Input type="date" value={to} onChange={(e) => onTo(e.target.value)} />
      </Field>
    </>
  );
}
