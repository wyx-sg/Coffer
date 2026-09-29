// src/pages/SecretsPage.tsx — PLACEHOLDER for the Secrets page, replaced by its own work item in this release.
import { KeyRound } from "lucide-react";

import { PlaceholderPage } from "@/components/PlaceholderPage";
import { PendingApprovalsEntry } from "@/components/credentials/PendingApprovalsEntry";

// PLACEHOLDER: renders "coming in this release" until the Secrets page lands.
// The one live piece already here: the way back to what waits for approval.
export function SecretsPage() {
  return (
    <div className="space-y-4">
      <PendingApprovalsEntry />
      <PlaceholderPage icon={KeyRound} titleKey="secrets.title" />
    </div>
  );
}
