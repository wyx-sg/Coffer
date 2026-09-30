// src/components/secret/useKindLabel.ts — a citer's kind as the user knows it ("MCP server", "Model provider", …).
import { useTranslation } from "react-i18next";

/** Labels a citer kind; a kind with no label reads as itself. */
export function useKindLabel() {
  const { t } = useTranslation();
  return (kind: string) => t(`secrets.kind.${kind}`, { defaultValue: kind });
}
