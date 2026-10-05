// src/components/secret/ScanSecretsDialog.tsx — Find plaintext keys: scan, tick, review a dry run, apply.
//
// Opening it scans the skills' files and the MCP servers' env and headers for
// plaintext values (spec secret "Move plaintext secrets in managed resources
// into the store"). Every finding starts ticked. Review asks the daemon for a
// dry run of the ticked ones — nothing is written — and shows the secrets it
// would add and the files and servers it would change; Apply then runs the
// import. The dialog closes on success, or, when some were skipped, says
// "Moved 2 of 3 keys", which and why, and offers Retry for one whose value is
// stored but whose file or server could not be rewritten. A scan that finds
// nothing says how many files and servers it read. Widths follow the step: scanning or nothing found 480, a result 640, the
// findings and the review 1060 so the dialog does not jump between them.
//
// Given `only` — vault-relative file paths, from the Sync page's "Move into
// secrets…" (spec vault-sync "Refuse to push a plaintext secret") — it lists
// the findings in those files alone, and when none of them is a file it can
// move a value out of, it says so instead of "No plaintext keys found".
import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import type { SecretImport } from "@/lib/api/secret";
import { translateApiError } from "@/lib/api/errors";
import { useIgnoreFindings, useImportSecrets, useSecretScan } from "@/lib/hooks/useSecrets";
import { ScanFindingsStep } from "./ScanFindingsStep";
import { ScanIgnoredList } from "./ScanIgnoredList";
import { ScanPreviewStep, ScanResultStep } from "./ScanPreviewStep";
import { planOf, type ImportPlan } from "./scanPlan";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Vault-relative paths (`skills/<name>/…`) to list findings in; omitted, every finding. */
  only?: readonly string[];
}

/** Whether a finding sits in one of `only`'s files. A skill finding's path is
 *  absolute, under the vault's `skills/`; `only` is relative to the vault. */
function inFiles(path: string | null, only: readonly string[]): boolean {
  return path !== null && only.some((p) => path === p || path.endsWith(`/${p}`));
}

type Step =
  | { name: "find" }
  | { name: "preview"; ids: string[]; plan: ImportPlan }
  | { name: "done"; result: SecretImport };

function Title({ children }: { children: string }) {
  const { t } = useTranslation();
  return (
    <DialogHeader>
      <DialogTitle>{children}</DialogTitle>
      <DialogDescription className="sr-only">{t("secrets.scan.hint")}</DialogDescription>
    </DialogHeader>
  );
}

export function ScanSecretsDialog({ open, onOpenChange, only }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const scan = useSecretScan(open);
  const importer = useImportSecrets();
  const ignorer = useIgnoreFindings();
  const [step, setStep] = useState<Step>({ name: "find" });
  const [ticked, setTicked] = useState<Set<string> | null>(null);

  const { reset } = importer;
  useEffect(() => {
    if (!open) return;
    setStep({ name: "find" });
    setTicked(null);
    reset();
  }, [open, reset]);

  const all = scan.data?.findings ?? [];
  const here = only ? all.filter((f) => inFiles(f.path, only)) : all;
  // Findings marked not a secret are hidden, never ticked, and never moved.
  const findings = here.filter((f) => !f.ignored);
  const ignored = here.filter((f) => f.ignored);
  // Every finding starts ticked, once the scan is in.
  const chosen = new Set(
    ticked ? findings.filter((f) => ticked.has(f.id)).map((f) => f.id) : findings.map((f) => f.id),
  );
  const close = () => onOpenChange(false);

  const toggle = (id: string) => {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setTicked(next);
  };

  const setIgnored = (id: string, ignore: boolean) => {
    // A finding reported again comes back ticked, as a fresh one does.
    if (!ignore && ticked) setTicked(new Set(ticked).add(id));
    ignorer.mutate({ ids: [id], ignore });
  };
  const ignoredList = (
    <ScanIgnoredList
      ignored={ignored}
      busy={ignorer.isPending}
      onReportAgain={(id) => setIgnored(id, false)}
    />
  );

  const review = async () => {
    const ids = findings.map((f) => f.id).filter((id) => chosen.has(id));
    try {
      const out = await importer.mutateAsync({ ids, dryRun: true });
      setStep({ name: "preview", ids, plan: planOf(out, findings) });
    } catch {
      // The hook toasts the failure; the findings stay as they were.
    }
  };

  const apply = async (ids: string[]) => {
    try {
      const out = await importer.mutateAsync({ ids, dryRun: false });
      if (out.skipped.length > 0) {
        setStep({ name: "done", result: out });
        return;
      }
      toast.success(t("secrets.scan.applied", { count: out.moved.length }));
      close();
    } catch {
      // The hook toasts the failure; the review stays open to retry.
    }
  };

  let body;
  let width = "max-w-[480px]";
  if (step.name === "done") {
    width = "max-w-[640px]";
    body = (
      <ScanResultStep
        result={step.result}
        retrying={importer.isPending}
        onRetry={(ids) => void apply(ids)}
        onClose={close}
      />
    );
  } else if (step.name === "preview") {
    width = "max-w-[1060px]";
    body = (
      <ScanPreviewStep
        plan={step.plan}
        applying={importer.isPending}
        onBack={() => setStep({ name: "find" })}
        onApply={() => void apply(step.ids)}
      />
    );
  } else if (scan.isPending) {
    body = (
      <>
        <Title>{t("secrets.scan.scanning")}</Title>
        <div className="space-y-2" aria-busy>
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-2/3" />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={close}>
            {t("common.cancel")}
          </Button>
        </DialogFooter>
      </>
    );
  } else if (scan.error) {
    body = (
      <>
        <Title>{t("secrets.scan.failed")}</Title>
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, scan.error)}
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => void scan.refetch()}>
            <RotateCcw aria-hidden /> {t("common.retry")}
          </Button>
        </DialogFooter>
      </>
    );
  } else if (findings.length === 0 && only) {
    body = (
      <>
        <Title>{t("secrets.scan.noneHereTitle")}</Title>
        <p className="text-sm text-text-muted">{t("secrets.scan.noneHereBody")}</p>
        {ignoredList}
        <DialogFooter>
          <Button onClick={close}>{t("common.done")}</Button>
        </DialogFooter>
      </>
    );
  } else if (findings.length === 0) {
    body = (
      <>
        <Title>{t("secrets.scan.noneTitle")}</Title>
        <p className="text-sm text-text-muted">{t("secrets.scan.noneBody")}</p>
        <dl className="grid grid-cols-[64px_minmax(0,1fr)] gap-x-3 text-xs">
          <dt className="text-text-muted">{t("secrets.scan.checked")}</dt>
          <dd className="text-text">
            {t("secrets.scan.filesRead", { count: scan.data?.files_checked ?? 0 })},{" "}
            {t("secrets.scan.serversRead", { count: scan.data?.servers_checked ?? 0 })}
          </dd>
        </dl>
        {ignoredList}
        <DialogFooter>
          <Button onClick={close}>{t("common.done")}</Button>
        </DialogFooter>
      </>
    );
  } else {
    width = "max-w-[1060px]";
    body = (
      <ScanFindingsStep
        scan={scan.data && { ...scan.data, findings }}
        ignored={ignored}
        busy={ignorer.isPending}
        onIgnore={(id) => setIgnored(id, true)}
        onReportAgain={(id) => setIgnored(id, false)}
        ticked={chosen}
        onToggle={toggle}
        onToggleAll={(all) => setTicked(new Set(all ? findings.map((f) => f.id) : []))}
        reviewing={importer.isPending}
        onCancel={close}
        onReview={() => void review()}
      />
    );
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !importer.isPending && onOpenChange(next)}>
      <DialogContent className={`${width} grid-cols-[minmax(0,1fr)]`}>{body}</DialogContent>
    </Dialog>
  );
}
