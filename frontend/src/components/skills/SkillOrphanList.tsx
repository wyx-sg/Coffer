// frontend/src/components/skills/SkillOrphanList.tsx
// "Not in your library N" under the library (canvas 4.3.28): folders in
// Coffer's skills store that no skill claims — copied in by hand or left by an
// interrupted import. No agent gets them. A row opens the folder in the
// reading pane (`/skills?orphan=<name>`), where it can be added or moved out.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useSkillOrphans } from "@/lib/hooks/useSkillCopies";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

interface Props {
  /** The orphan open in the reading pane, highlighted here. */
  selected: string | null;
}

export function SkillOrphanList({ selected }: Props) {
  const { t } = useTranslation();
  const { data: orphans = [] } = useSkillOrphans();
  if (orphans.length === 0) return null;
  return (
    <>
      <h2 className="flex items-center px-2.5 pb-1 pt-4 text-2xs font-semibold text-text-muted">
        {t("skills.orphan.section")}
        <span className="ml-auto font-book">{orphans.length}</span>
      </h2>
      <ul className="flex flex-col gap-0.5" aria-label={t("skills.orphan.section")}>
        {orphans.map((o) => (
          <li key={o.name}>
            <Link
              to={`/skills?orphan=${encodeURIComponent(o.name)}`}
              aria-current={selected === o.name ? "page" : undefined}
              className={cn(
                "flex flex-col gap-0.5 rounded-lg px-2.5 py-2 transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
                selected === o.name ? "bg-surface-selected" : "hover:bg-surface-hover",
              )}
            >
              <span className="truncate font-mono text-xs font-label text-text">{o.name}</span>
              <span className={cn("truncate text-xs", toneTextClass("warn"))}>
                {t("skills.orphan.row")}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
