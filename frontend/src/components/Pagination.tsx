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
 * Used by the Observability audit log and the MCP servers list, both of
 * which fetch a capped batch and page through it in the browser.
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
  if (total === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>{t("pagination.summary", { page, pageCount, total })}</span>
      <div className="flex items-center gap-2">
        <span>{t("pagination.perPage")}</span>
        <Select value={String(pageSize)} onValueChange={(v) => onPageSizeChange(Number(v))}>
          <SelectTrigger className="h-8 w-[4.5rem]">
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
