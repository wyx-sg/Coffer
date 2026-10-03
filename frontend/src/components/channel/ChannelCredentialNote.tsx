// frontend/src/components/channel/ChannelCredentialNote.tsx
// What the credential check found, under the field it was run for: "checking…",
// the bot it identified (a success note), or the reason it failed (an error
// line like any other field error). Shared by Add channel and Replace token.
import { CheckCircle2, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { CredentialCheck } from "@/lib/api/channels";
import type { CredentialCheckState } from "@/lib/hooks/useCredentialCheck";
import { FieldError } from "./FieldError";

/** The failure, in words a person can act on. */
function credentialFailure(
  t: (key: string, o?: Record<string, unknown>) => string,
  result: CredentialCheck,
): string {
  return t(`channels.credentials.${result.reason ?? "unreachable"}`);
}

interface Props {
  id: string;
  check: CredentialCheckState;
  /** The success note's title and body (the caller knows the surface's words). */
  success: (result: CredentialCheck) => { title: string; body?: string | null };
}

export function ChannelCredentialNote({ id, check, success }: Props) {
  const { t } = useTranslation();
  if (check.state === "idle") return null;
  if (check.state === "checking") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-text-muted" role="status">
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        {t("channels.credentials.checking")}
      </p>
    );
  }
  const { result } = check;
  if (!result.ok) {
    // A missing field is the form's own "Enter …" message, never this one.
    return result.reason === "missing" ? null : (
      <FieldError id={id} message={credentialFailure(t, result)} />
    );
  }
  const { title, body } = success(result);
  return (
    <div
      id={id}
      className="flex gap-2 rounded-lg bg-success-soft px-3 py-2.5"
      data-testid="credential-found"
    >
      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
      <div className="space-y-0.5">
        <p className="text-sm font-label text-text">{title}</p>
        {body ? <p className="text-xs text-text-muted">{body}</p> : null}
      </div>
    </div>
  );
}
