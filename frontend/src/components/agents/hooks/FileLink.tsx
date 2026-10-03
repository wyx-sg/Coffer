// src/components/agents/hooks/FileLink.tsx — a hook's file: a link to it in the Config files tab when that tab holds it.
//
// The path is the hook file's real one; the link goes to the Config files tab
// with that file open (`?file=<key>`). A plugin's hooks.json is not a Config
// files entry, so it reads as plain text.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { abbreviateHomePath } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";

interface Props {
  agentType: string;
  path: string;
  /** The Config files key that holds `path`, when one does. */
  fileKey: string | null;
}

export function FileLink({ agentType, path, fileKey }: Props) {
  const { t } = useTranslation();
  const label = abbreviateHomePath(path);
  if (!fileKey) return <span className="break-all font-mono text-xs text-text-muted">{label}</span>;
  return (
    <Link
      to={agentTabPath(agentType, "config", `?${new URLSearchParams({ file: fileKey })}`)}
      title={t("agents.hooks.openInConfig")}
      className="break-all font-mono text-xs text-text-muted underline decoration-border underline-offset-2 hover:text-text hover:decoration-text-muted"
    >
      {label}
    </Link>
  );
}
