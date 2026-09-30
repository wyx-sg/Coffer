// src/lib/hooks/useSecurity.ts — queries and mutations behind Settings › Security:
// rotating the daemon token, the master key's fingerprint, export and import,
// and revealing an exported key file in the file manager.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { resetApiClient } from "@/lib/api/client";
import { translateApiError } from "@/lib/api/errors";
import { fsApi } from "@/lib/api/fs";
import {
  secretsKey,
  secretSettingsKey,
  syncKey,
  syncKeyFingerprintKey,
} from "@/lib/api/queryKeys";
import { securityApi } from "@/lib/api/security";
import { getCofferBaseUrl, setDaemonConnection } from "@/lib/auth";
import { exportMasterKeyBackup } from "@/lib/tauri";

/**
 * Rotate the daemon's access token and INSTALL the new one, so this page's
 * next request carries it with no reload (spec web-ui "Show, copy and rotate
 * the access token on Settings › Security").
 *
 * The install happens inside `mutationFn`, before the mutation resolves: a
 * query refetching in the same tick as `onSuccess` would otherwise still send
 * the revoked token. A failed rotation installs nothing — the old token is
 * still the daemon's, and the page keeps using it.
 *
 * No toast on error: the confirmation dialog renders the failure inline and
 * stays open (ConfirmDialog closes only on success).
 */
export function useRotateDaemonToken() {
  return useMutation({
    mutationFn: async () => {
      const { token } = await securityApi.rotateToken();
      const baseUrl = getCofferBaseUrl();
      // A null base URL cannot have reached the call above; the guard only
      // keeps the types honest.
      if (baseUrl !== null) setDaemonConnection(baseUrl, token);
      resetApiClient();
      return token;
    },
  });
}

/** Select a file the daemon just wrote in Finder (the exported master key). */
export function useRevealPath() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (path: string) => fsApi.reveal(path),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** This machine's master key fingerprint (12 hex characters). Null when it holds none. */
export function useMasterKeyFingerprint() {
  return useQuery({
    queryKey: syncKeyFingerprintKey,
    queryFn: () => securityApi.keyFingerprint(),
  });
}

/**
 * Write a passphrase-protected backup through the desktop shell, which runs
 * the presence check and the folder picker. The key never reaches the page;
 * the page learns where the file went. No toast on error: the export dialog
 * shows the failure inline and stays open.
 */
export function useExportMasterKey() {
  return useMutation({
    mutationFn: (passphrase: string) => exportMasterKeyBackup(passphrase),
  });
}

/** Whose key a picked file holds, beside this machine's — replaces nothing. */
export function usePreviewKeyImport() {
  return useMutation({
    mutationFn: (material: string) => securityApi.previewKeyImport(material),
  });
}

/**
 * Install the key a picked file holds. Afterwards the fingerprint, the round's
 * locked refs and the Secrets list (what reads as missing) are all stale.
 */
export function useImportKeyFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ material, passphrase }: { material: string; passphrase: string | null }) =>
      securityApi.importKey(material, passphrase),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: syncKey });
      void qc.invalidateQueries({ queryKey: secretsKey });
      void qc.invalidateQueries({ queryKey: secretSettingsKey });
    },
  });
}
