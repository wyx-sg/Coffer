// src/components/custom-tools/GroupBanners.tsx — which banner a group shows under its header, if any: Off beats
// failing calls, which beat a secret problem (the state the header pill names).
import type { CustomToolGroup } from "@/lib/api/customTools";
import { GroupFailingBanner, GroupOffBanner } from "./GroupProblemBanner";
import { GroupSecretAlert } from "./GroupSecretAlert";

interface Props {
  group: CustomToolGroup;
  onChooseAnother: () => void;
}

export function GroupBanners({ group, onChooseAnother }: Props) {
  if (group.health === "off") return <GroupOffBanner group={group} />;
  if (group.health === "failing") return <GroupFailingBanner group={group} />;
  return <GroupSecretAlert group={group} onChooseAnother={onChooseAnother} />;
}
