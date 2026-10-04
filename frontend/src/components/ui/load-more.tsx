// src/components/ui/load-more.tsx — the end of a list that grows: an invisible sentinel that loads the next page when scrolled to, and the footer that says what is loaded.
//
// Every list over ~100 rows pages by cursor and loads on scroll (frontend
// conventions §6). `LoadMoreSentinel` is the scroll trigger; `LoadMoreFooter`
// is the fallback that is always visible — "N loaded · Load more" — so a
// reader who cannot scroll to the end (or a browser without
// IntersectionObserver) can still ask, and one who can sees the count.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SentinelProps {
  /** Whether another page exists and none is loading: the sentinel is off otherwise. */
  active: boolean;
  onVisible: () => void;
  /**
   * Changes whenever rows were added (the loaded count): the observer is set
   * up again, so a page that did not fill the viewport asks for the next one.
   */
  version?: number;
  /** Load this far before the sentinel is on screen. */
  rootMargin?: string;
}

/** Calls `onVisible` when it scrolls into view (or is in view when it turns active). */
export function LoadMoreSentinel({
  active,
  onVisible,
  version = 0,
  rootMargin = "240px",
}: SentinelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const latest = useRef(onVisible);
  latest.current = onVisible;

  useEffect(() => {
    const el = ref.current;
    if (!active || !el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) latest.current();
      },
      { rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [active, version, rootMargin]);

  return <div ref={ref} aria-hidden data-load-more-sentinel className="h-px w-full" />;
}

interface FooterProps {
  loaded: number;
  /** The count of every matching row, when known. */
  total?: number;
  hasMore: boolean;
  loading: boolean;
  onMore: () => void;
  /** The button's label; default "Load more". */
  moreLabel?: string;
  /** Load on scroll too (a `LoadMoreSentinel` is rendered above the footer). */
  autoLoad?: boolean;
  /** Text beside the count (e.g. what the next page holds). */
  hint?: React.ReactNode;
  className?: string;
}

/** "N loaded · Load more" (or "Showing N of M" when the total is known), with the sentinel. */
export function LoadMoreFooter({
  loaded,
  total,
  hasMore,
  loading,
  onMore,
  moreLabel,
  autoLoad = false,
  hint,
  className,
}: FooterProps) {
  const { t } = useTranslation();
  if (!hasMore && loaded === 0) return null;
  return (
    <>
      {autoLoad ? (
        <LoadMoreSentinel active={hasMore && !loading} onVisible={onMore} version={loaded} />
      ) : null}
      <div className={cn("flex flex-wrap items-center gap-3 text-xs text-text-muted", className)}>
        <span>
          {total !== undefined
            ? t("pagination.showing", { shown: loaded, total })
            : t("pagination.loaded", { count: loaded })}
        </span>
        {hasMore ? (
          <Button variant="outline" size="sm" loading={loading} onClick={onMore}>
            {loading ? t("pagination.loadingMore") : (moreLabel ?? t("pagination.loadMoreShort"))}
          </Button>
        ) : null}
        {hint}
      </div>
    </>
  );
}
