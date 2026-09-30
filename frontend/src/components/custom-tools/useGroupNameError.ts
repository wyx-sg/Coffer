// src/components/custom-tools/useGroupNameError.ts — why a new group's name cannot be used, if it cannot.
import { useTranslation } from "react-i18next";

import { isGroupName } from "@/lib/customTools/drafts";

export function useGroupNameError(name: string, taken: string[]): string | undefined {
  const { t } = useTranslation();
  if (name && !isGroupName(name)) return t("customTools.add.nameInvalid");
  if (taken.includes(name)) return t("customTools.add.nameTaken");
  return undefined;
}
