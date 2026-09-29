// frontend/src/lib/skills/tabs.ts
// A skill's detail tabs, in order — Files, Delivery, Requires, History (spec
// skill-manager "Cover skill management on REST, the CLI and the web"). The
// first is the default and lives at the bare `/skills/<name>`; the others add
// their name to the path. Shared by the Skills page, which owns the address,
// and the lazily loaded pane that draws the tabs.
export const SKILL_TABS = ["files", "delivery", "requires", "history"] as const;
export type SkillTab = (typeof SKILL_TABS)[number];
export const DEFAULT_SKILL_TAB: SkillTab = "files";
