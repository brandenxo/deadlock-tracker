import type { UtcDate } from "../types";

// Only covered dates are offered, so a range can never include a partial day.
export function RangePicker({
  covered,
  from,
  to,
  onChange,
}: {
  covered: UtcDate[];
  from: UtcDate;
  to: UtcDate;
  onChange: (from: UtcDate, to: UtcDate) => void;
}) {
  return (
    <fieldset className="range">
      <legend>Match dates (UTC)</legend>
      <label>
        From
        <select value={from} onChange={(e) => onChange(e.target.value, e.target.value > to ? e.target.value : to)}>
          {covered.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </label>
      <label>
        To
        <select value={to} onChange={(e) => onChange(from, e.target.value)}>
          {covered.filter((d) => d >= from).map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </label>
      <button type="button" className="link"
        onClick={() => onChange(covered[0] ?? from, covered[covered.length - 1] ?? to)}>
        All covered dates
      </button>
    </fieldset>
  );
}
