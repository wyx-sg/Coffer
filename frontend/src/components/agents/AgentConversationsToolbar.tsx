// frontend/src/components/agents/AgentConversationsToolbar.tsx
// Filter bar for the conversations tab: free-text search (title or project),
// a project dropdown, and a time-range picker over started_at. Laid out as the
// same inline toolbar the shared DataTable renders, for visual consistency.
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { TimeRangePicker, type TimeRangeValue } from "@/components/TimeRangePicker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  search: string;
  onSearchChange: (v: string) => void;
  project: string;
  onProjectChange: (v: string) => void;
  projectOptions: string[];
  time: TimeRangeValue;
  onTimeChange: (v: TimeRangeValue) => void;
}

export function AgentConversationsToolbar({
  search,
  onSearchChange,
  project,
  onProjectChange,
  projectOptions,
  time,
  onTimeChange,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        value={search}
        onChange={onSearchChange}
        placeholder={t("agents.conversationsTab.searchPlaceholder")}
        ariaLabel={t("agents.conversationsTab.searchPlaceholder")}
        className="w-full sm:max-w-xs"
      />
      <Select value={project} onValueChange={onProjectChange}>
        <SelectTrigger
          aria-label={t("agents.conversationsTab.filterProject")}
          className="h-9 w-auto min-w-[10rem] max-w-xs"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("agents.conversationsTab.allProjects")}</SelectItem>
          {projectOptions.map((p) => (
            <SelectItem key={p} value={p}>
              {p}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <TimeRangePicker
        timeRange={time.timeRange}
        from={time.from}
        to={time.to}
        onChange={onTimeChange}
      />
    </div>
  );
}
