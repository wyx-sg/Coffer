// frontend/src/components/settings/ProviderDetailHeader.tsx
// Header of the connection detail page, rendered through the shared PageHeader
// like every other detail surface: the back link, the name, the protocol chip
// + Active pill beside it, and the actions that change the connection itself —
// the shared ScopeControl first (where this connection's REACH — disabled,
// every agent, or a chosen set — is both SHOWN and changed), then Edit (the
// existing ProviderForm, in a dialog owned here so the page file stays lean)
// and Delete (confirmed by the page). It replaced a read-only
// badge: the list could flip a provider and its own page could not, and a badge
// next to the control would have stated the same state twice. `provider` now
// declares per-agent scope, so this is the three-segment control and the ONLY
// place a connection's agent set is edited — the Edit dialog deliberately has no
// control of its own. The description sits in the Configuration card rather than
// here, so it is stated exactly once.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { ActiveProviderBadge } from "@/components/settings/ActiveProviderBadge";
import { TranscribeProviderBadge } from "@/components/settings/TranscribeProviderBadge";
import { PROTOCOL_LABEL_KEY } from "@/components/settings/connectionPresets";
import { ProviderForm } from "@/components/settings/ProviderForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { Provider } from "@/lib/api/providers";
import { useUpdateProvider } from "@/lib/hooks/useProviders";
import { useRenameResource } from "@/lib/hooks/useResourceMutations";

export function ProviderDetailHeader({
  provider,
  onDeleteClick,
  deletePending,
}: {
  provider: Provider;
  onDeleteClick: () => void;
  deletePending: boolean;
}) {
  const { t } = useTranslation();
  const update = useUpdateProvider();
  const rename = useRenameResource();
  const [editOpen, setEditOpen] = useState(false);

  const closeEdit = () => {
    setEditOpen(false);
    update.reset();
    rename.reset();
  };

  /** Save the edit dialog.
   *
   *  A changed NAME is an ordinary field edit now — the kind-agnostic
   *  `PATCH /resources/{uid}` every kind renames through — rather than this
   *  kind's own `POST /providers/{name}/rename`, which existed only because the
   *  name was the connection's identity. It still goes FIRST, for the reason it
   *  always did: a label already taken must fail before any of this dialog's
   *  other edits land.
   *
   *  Nothing navigates afterwards. The URL is built from the uid, so a rename
   *  does not change it — which is this change made visible: the page the user
   *  is reading stays the page they are reading, and the old code's
   *  `navigate(.../${next})` existed purely because the route WAS the name and
   *  staying put would have left them on a URL that 404s. */
  const save = async (
    patch: Parameters<typeof update.mutateAsync>[0]["patch"],
    next: string | null,
  ) => {
    try {
      if (next) await rename.mutateAsync({ kind: "provider", uid: provider.uid, name: next });
      await update.mutateAsync({ uid: provider.uid, patch });
    } catch {
      // Swallowed deliberately: the failure is already the mutation's state,
      // which the dialog renders inline (and the hook toasts). Letting it
      // escape the form's submit handler would only be an unhandled rejection.
      return;
    }
    closeEdit();
  };

  return (
    <>
      <PageHeader
        back={{ to: "/model-providers", label: t("settings.connections.detail.back") }}
        title={provider.name}
        badges={
          <>
            <Badge variant="secondary">{t(PROTOCOL_LABEL_KEY[provider.protocol])}</Badge>
            {provider.is_active ? <ActiveProviderBadge /> : null}
            {provider.transcribe_default ? <TranscribeProviderBadge /> : null}
          </>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ScopeControl kind="provider" uid={provider.uid} enabled={provider.enabled} />
            <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="mr-1.5 size-3.5" /> {t("common.edit")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onDeleteClick}
              disabled={deletePending}
              className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
            </Button>
          </div>
        }
      />
      <Dialog open={editOpen} onOpenChange={(open) => !open && closeEdit()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.connections.editTitle")}</DialogTitle>
          </DialogHeader>
          <ProviderForm
            initial={provider}
            submitError={rename.error ?? update.error}
            pending={update.isPending || rename.isPending}
            onCancel={closeEdit}
            onSubmit={() => {}}
            onUpdate={save}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
