// frontend/src/components/skills/skillFileHelpers.ts
// The Files card's open file, kept in `?file=` (absent for the default).
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";

/** The file a skill opens on: its SKILL.md, the one file every skill has. */
const DEFAULT_FILE = "SKILL.md";

/** The open file, kept in `?file=` so a reload or a link lands on the same file. */
export function useSelectedFile() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("file") ?? DEFAULT_FILE;
  const select = (path: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (path === DEFAULT_FILE) next.delete("file");
        else next.set("file", path);
        return next;
      },
      { replace: true },
    );
  return { selected, select };
}
