import { useTranslation } from "react-i18next";
import { SearchInput } from "@/components/SearchInput";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  search: string;
  onSearchChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
}

/** Search box + status filter above the MCP server list. */
export function ResourcesToolbar({ search, onSearchChange, status, onStatusChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        className="w-full sm:w-80"
        value={search}
        onChange={onSearchChange}
        placeholder={t("resources.search")}
        ariaLabel={t("resources.search")}
      />
      <Select value={status} onValueChange={onStatusChange}>
        <SelectTrigger className="w-40" aria-label={t("resources.statusFilter")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("resources.status.all")}</SelectItem>
          <SelectItem value="enabled">{t("resources.status.enabled")}</SelectItem>
          <SelectItem value="disabled">{t("resources.status.disabled")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
