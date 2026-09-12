// frontend/src/pages/settings/SyncSettings.tsx
//
// Settings → Sync (spec vault-export-import). Three cards: the export/import card that
// writes and reads a bundle directory, the master-key card that bootstraps the
// Fernet key onto the other machine out-of-band, and the backup card that
// configures the one git remote exports are pushed to on a timer.
//
// Backup is one-way and never automatic in the other direction: Coffer pushes
// on a schedule, and restores only when the user asks. There is still no
// convergence, no merging and no arbitration between machines — carrying a
// bundle between them by hand remains the user's business.
import { SyncBackupCard } from "./SyncBackupCard";
import { SyncBundleCard } from "./SyncBundleCard";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

export function SyncSettings() {
  return (
    <div className="space-y-6">
      <SyncBundleCard />
      <SyncBackupCard />
      <SyncMasterKeyCard />
    </div>
  );
}
