// frontend/src/pages/settings/SyncSettings.tsx
//
// Settings → Sync (spec vault-export-import). Two cards, and nothing else: the export/import
// card that writes and reads a bundle directory, and the master-key card that
// bootstraps the Fernet key onto the other machine out-of-band. There is no
// remote to configure, no auto-sync to schedule and no conflict to resolve —
// carrying the bundle between machines is the user's business.
import { SyncBundleCard } from "./SyncBundleCard";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

export function SyncSettings() {
  return (
    <div className="space-y-6">
      <SyncBundleCard />
      <SyncMasterKeyCard />
    </div>
  );
}
