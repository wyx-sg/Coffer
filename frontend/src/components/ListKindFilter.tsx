// src/components/ListKindFilter.tsx — the Kind filter both resource lists offer: All, Built-in (what Coffer ships) or Custom (what the user added).
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export type KindFilterValue = "all" | "builtin" | "custom";

const KINDS: KindFilterValue[] = ["all", "builtin", "custom"];

interface Props {
  value: KindFilterValue;
  onChange: (value: KindFilterValue) => void;
  /** The list's own words: the control's name, then one per choice. */
  words: { label: string } & Record<KindFilterValue, string>;
}

export function ListKindFilter({ value, onChange, words }: Props) {
  const label = words.label;
  return (
    <Select value={value} onValueChange={(v) => onChange(v as KindFilterValue)}>
      <SelectTrigger aria-label={label} title={label} className="h-control-sm w-auto text-xs">
        <SelectValue>{`${label}: ${words[value]}`}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {KINDS.map((k) => (
          <SelectItem key={k} value={k}>
            {words[k]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
