// frontend/src/lib/hooks/useFsBrowse.ts
// One directory level of the host filesystem, read through the loopback
// daemon (spec agent-registry "Offer a folder picker for a custom config
// directory"). Backs the in-app folder browser the
// FolderPicker falls back to when this host has no native directory dialog.
import { useQuery } from "@tanstack/react-query";

import { fsApi } from "@/lib/api/fs";
import { fsBrowseKey } from "@/lib/api/queryKeys";

/** `path` null = the daemon's home directory. Each directory caches under its
 *  own key, so stepping back up is instant. `enabled: false` while the dialog
 *  is closed — nothing is fetched for a picker nobody opened. */
export function useFsBrowse(path: string | null, opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: fsBrowseKey(path ?? "~"),
    queryFn: () => fsApi.browse(path),
    enabled: opts.enabled ?? true,
  });
}
