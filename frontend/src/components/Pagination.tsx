import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  /** 1-based current page. */
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

/**
 * Shared client-side pager — page summary, per-page selector, prev/next.
 * Rendered by every DataTable surface. It stays visible even when the table
 * is empty (total === 0 → "1 / 1 · 0 items", prev/next disabled) so an empty
 * Resources/Prompts/Invocations tab looks consistent with a populated Tools
 * tab rather than silently dropping its pager.
 */
export function Pagination({
  page,
  pageCount,
  total,
  pageSize,
  pageSizeOptions = [10, 20, 50, 100],
  onPageChange,
  onPageSizeChange,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>{t("pagination.summary", { page, pageCount, total })}</span>
      <div className="flex items-center gap-2">
        <span>{t("pagination.perPage")}</span>
        <Select value={String(pageSize)} onValueChange={(v) => onPageSizeChange(Number(v))}>
          <SelectTrigger aria-label={t("pagination.perPage")} className="h-8 w-[4.5rem]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {pageSizeOptions.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="icon"
          className="size-8"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label={t("pagination.prev")}
        >
          <ChevronLeft className="size-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="size-8"
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
          aria-label={t("pagination.next")}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
