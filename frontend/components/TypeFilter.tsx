"use client";

import { RATE_TYPES, rateTypeLabel } from "@/lib/types";
import { Select } from "./Select";

interface Props {
  value: string; // "" = all
  onChange: (value: string) => void;
  includeAll?: boolean;
  label?: string;
  id: string;
}

export function TypeFilter({ value, onChange, includeAll = true, label, id }: Props) {
  return (
    <Select id={id} label={label} value={value} onChange={onChange}>
      {includeAll && <option value="">All rate types</option>}
      {RATE_TYPES.map((t) => (
        <option key={t} value={t}>
          {rateTypeLabel(t)}
        </option>
      ))}
    </Select>
  );
}
