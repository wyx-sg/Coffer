// frontend/src/lib/hooks/useEditors.ts
// Detected GUI editors for the preferred-editor picker (Settings → General).
// The daemon enumerates what's installed (a browser can't); the chosen value
// itself stays client-side in localStorage (see lib/preferences.ts).
import { useQuery } from "@tanstack/react-query";

import { fsApi, type EditorOption } from "@/lib/api/fs";

/** Reactive list of installed GUI editors. Empty/failed → picker shows just the
 *  system-default + custom options (detection is best-effort, never blocking). */
export function useDetectedEditors() {
  return useQuery<EditorOption[]>({
    queryKey: ["fs", "editors"],
    queryFn: () => fsApi.listEditors(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
