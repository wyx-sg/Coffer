// src/components/clis/CliNodeDetail.tsx — the Commands tab's right column: one command of the tool, as its help describes it.
//
// Its full command line with a copy button, what it is for, its usage line, its
// subcommands (each opening that command in the tree), its positional
// arguments and its options. The text the tool printed is always one toggle
// away ("Raw help"); a command whose help the parser could not structure shows
// it straight away, and one that printed nothing says why.
import { TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Section, SectionStack } from "@/components/Section";
import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import { commandLine, nodeKey, type CommandTreeNode } from "@/lib/clis/tree";
import { CliOptionsTable } from "./CliOptionsTable";

interface Props {
  command: string;
  entry: CommandTreeNode;
  /** Keys of the commands the tree holds: a subcommand outside it (past the depth bound) is not a link. */
  known: ReadonlySet<string>;
  onOpen: (key: string) => void;
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Section title={title} gap="snug" labelled>
      {children}
    </Section>
  );
}

export function CliNodeDetail({ command, entry, known, onOpen }: Props) {
  const { t } = useTranslation();
  const { node } = entry;
  const [rawShown, setRawShown] = useState(false);
  const showRaw = rawShown || (!node.structured && node.raw !== "");
  return (
    <div className="space-y-5 p-5" data-testid="cli-node">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <CopyableCommand command={commandLine(command, node.path)} />
          {node.description ? <p className="text-sm text-text-muted">{node.description}</p> : null}
        </div>
        {node.raw !== "" && node.structured ? (
          <Button
            variant="outline"
            size="sm"
            aria-pressed={rawShown}
            onClick={() => setRawShown((v) => !v)}
          >
            {rawShown ? t("clis.commands.hideRaw") : t("clis.commands.showRaw")}
          </Button>
        ) : null}
      </div>

      {node.error ? (
        <Alert variant="warning">
          <TriangleAlert aria-hidden />
          <AlertDescription>{t("clis.commands.noHelp", { reason: node.error })}</AlertDescription>
        </Alert>
      ) : null}

      {showRaw ? (
        <Block title={t("clis.commands.rawTitle")}>
          <pre className="max-h-[28rem] overflow-auto whitespace-pre rounded-md border border-border-subtle bg-surface-sunken p-3 font-mono text-xs text-text">
            {node.raw}
          </pre>
          {node.truncated ? (
            <p className="text-2xs text-text-muted">{t("clis.commands.truncated")}</p>
          ) : null}
        </Block>
      ) : (
        <SectionStack>
          {node.usage ? (
            <Block title={t("clis.commands.usage")}>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-md border border-border-subtle bg-surface-sunken p-3 font-mono text-xs text-text">
                {node.usage}
              </pre>
            </Block>
          ) : null}
          {node.subcommands.length > 0 ? (
            <Block title={t("clis.commands.subcommands")}>
              <ul className="paper-card divide-y divide-border-subtle">
                {node.subcommands.map((sub) => {
                  const key = nodeKey([...node.path, sub.name]);
                  return (
                    <li key={sub.name} className="flex min-w-0 items-center gap-3 px-3 py-2">
                      {known.has(key) ? (
                        <button
                          type="button"
                          onClick={() => onOpen(key)}
                          className="w-40 shrink-0 truncate text-left font-mono text-sm text-accent-text hover:underline"
                        >
                          {sub.name}
                        </button>
                      ) : (
                        <span className="w-40 shrink-0 truncate font-mono text-sm">{sub.name}</span>
                      )}
                      {sub.summary ? (
                        <TruncatedText
                          text={sub.summary}
                          className="min-w-0 flex-1 text-xs text-text-muted"
                        />
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </Block>
          ) : null}
          {node.arguments.length > 0 ? (
            <Block title={t("clis.commands.arguments")}>
              <ul className="paper-card divide-y divide-border-subtle">
                {node.arguments.map((arg) => (
                  <li key={arg.name} className="flex min-w-0 items-center gap-3 px-3 py-2">
                    <span className="w-40 shrink-0 truncate font-mono text-sm">{arg.name}</span>
                    {arg.required ? (
                      <Badge variant="secondary">{t("clis.commands.required")}</Badge>
                    ) : null}
                    {arg.description ? (
                      <TruncatedText
                        text={arg.description}
                        className="min-w-0 flex-1 text-xs text-text-muted"
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            </Block>
          ) : null}
          {node.options.length > 0 ? (
            <Block title={t("clis.commands.options")}>
              <CliOptionsTable options={node.options} />
            </Block>
          ) : null}
        </SectionStack>
      )}
    </div>
  );
}
