"use client";

import { RATE_TYPES, rateTypeLabel } from "@/lib/types";
import { Select } from "./Select";

export interface ProviderOption {
  slug: string;
  name: string;
}

interface Props {
  providers: ProviderOption[];
  provider: string;
  type: string;
  onProviderChange: (slug: string) => void;
  onTypeChange: (type: string) => void;
}

export function ProviderTypePicker({
  providers,
  provider,
  type,
  onProviderChange,
  onTypeChange,
}: Props) {
  return (
    <div className="flex flex-wrap gap-3">
      <Select
        label="Provider"
        value={provider}
        onChange={onProviderChange}
        disabled={providers.length === 0}
      >
        {providers.map((p) => (
          <option key={p.slug} value={p.slug}>
            {p.name}
          </option>
        ))}
      </Select>
      <Select label="Rate type" value={type} onChange={onTypeChange}>
        {RATE_TYPES.map((t) => (
          <option key={t} value={t}>
            {rateTypeLabel(t)}
          </option>
        ))}
      </Select>
    </div>
  );
}
