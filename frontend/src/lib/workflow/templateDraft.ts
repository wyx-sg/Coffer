// frontend/src/lib/workflow/templateDraft.ts
// Pure edits on a template config — the editor's whole vocabulary (FR-054).
//
// A template is a LIST, not a graph: the order the stages sit in is the order
// they run in, and it is the only thing that says what runs after what. There
// are no edges of any kind — a finding in a later task is acted on by the
// developer, by retrying the task that was wrong or adding one that fixes it
// (FR-025), which is a decision only the person holding the finding can make.
// So "reorder the stages" is a list operation and there is no graph to keep
// consistent alongside it.
//
// KEYS ARE DERIVED HERE AND NEVER TYPED (FR-060). A key is an identity the
// engine reads no meaning from (FR-003); asking a developer to invent one is
// asking them to do the computer's filing. So a stage's and a task's key are
// slugs of their name, made unique, recomputed whenever the name changes. This
// is safe because a template is only ever data: a run froze its own copy of it
// (FR-011), so nothing in flight is reading these keys.
//
// Every function returns a new config; nothing here mutates its argument.
import type { TemplateConfig, TemplateNode, TemplateStage } from "@/lib/api/workflow";
import { nodeKeyFor, stageKeyFor } from "@/lib/workflow/templateKeys";

export { slugify } from "@/lib/workflow/templateKeys";

/** Who does the work. Two values, because the engine only ever asked one
 *  question of this field: dispatch a turn, or stop and wait for a person. */
export const NODE_TYPES = ["ai", "manual"] as const;
export const APPROVALS = ["never", "always"] as const;
export const FAILURE_ACTIONS = ["stop", "continue", "retry"] as const;

/** What the stage dialog edits: everything about a stage except its tasks. */
export interface StageValues {
  name: string;
  optional: boolean;
}

/** How many attempts a task gets when nobody has said. The daemon applies the
 *  same number for an absent field; it is restated here so a new task shows a
 *  figure rather than an empty box the developer has to guess the meaning of. */
export const DEFAULT_ATTEMPT_CEILING = 3;

/** What the task dialog edits — everything a node has except its identity. */
export type NodeValues = Omit<TemplateNode, "key">;

export function nodeValues(node: TemplateNode): NodeValues {
  return {
    name: node.name,
    type: node.type,
    skill: node.skill ?? null,
    instructions: node.instructions ?? null,
    artifacts: node.artifacts ?? [],
    approval: node.approval ?? "never",
    on_failure: node.on_failure ?? { action: "stop" },
    agent: node.agent ?? null,
    attempt_ceiling: node.attempt_ceiling ?? DEFAULT_ATTEMPT_CEILING,
  };
}

/** A node with nothing chosen yet — what the task dialog opens on. */
export function blankNode(name = ""): NodeValues {
  return {
    name,
    type: "ai",
    skill: null,
    instructions: null,
    artifacts: [],
    approval: "never",
    on_failure: { action: "stop" },
    agent: null,
    attempt_ceiling: DEFAULT_ATTEMPT_CEILING,
  };
}

/** What a brand-new template starts as: one stage, one task. The contract's
 *  minima are `stages: 1` and `nodes: 1` per stage, so an empty shell would be
 *  refused the moment it was written. */
export function emptyTemplate(): TemplateConfig {
  return addStage({ stages: [] }, { name: "", optional: false });
}

function move<T>(items: T[], index: number, delta: number): T[] {
  const to = index + delta;
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(index, 1);
  next.splice(to, 0, item);
  return next;
}

function withStages(config: TemplateConfig, stages: TemplateStage[]): TemplateConfig {
  return { ...config, stages };
}

function mapStage(
  config: TemplateConfig,
  index: number,
  fn: (stage: TemplateStage) => TemplateStage,
): TemplateConfig {
  return withStages(
    config,
    config.stages.map((stage, i) => (i === index ? fn(stage) : stage)),
  );
}

/**
 * Add a stage, with one task in it.
 *
 * The task is not optional and not a placeholder the developer has to notice:
 * the contract's minimum is one node per stage, so a stage with no tasks is
 * not a thing that can exist. It is named after the stage because a one-task
 * stage is the common shape and "Tech Design does the tech design" reads
 * better than "Tech Design contains New task 3".
 */
export function addStage(config: TemplateConfig, values: StageValues): TemplateConfig {
  const key = stageKeyFor(config, values.name);
  const stage: TemplateStage = {
    key,
    name: values.name,
    optional: values.optional,
    nodes: [{ ...blankNode(values.name), key: nodeKeyFor(config, values.name) }],
  };
  return withStages(config, [...config.stages, stage]);
}

/** Save a stage's own fields, re-deriving its key from its name. Nothing in
 *  the template points at a stage key, so there is nothing to rewrite. */
export function saveStage(
  config: TemplateConfig,
  index: number,
  values: StageValues,
): TemplateConfig {
  const before = config.stages[index];
  if (before === undefined) return config;
  const key = stageKeyFor(config, values.name, before.key);
  return mapStage(config, index, (stage) => ({
    ...stage,
    key,
    name: values.name,
    optional: values.optional,
  }));
}

export function removeStage(config: TemplateConfig, index: number): TemplateConfig {
  return withStages(
    config,
    config.stages.filter((_, i) => i !== index),
  );
}

export function moveStage(config: TemplateConfig, index: number, delta: number): TemplateConfig {
  return withStages(config, move(config.stages, index, delta));
}

export function addNode(
  config: TemplateConfig,
  stageIndex: number,
  values: NodeValues,
): TemplateConfig {
  const node: TemplateNode = { ...values, key: nodeKeyFor(config, values.name) };
  return mapStage(config, stageIndex, (stage) => ({ ...stage, nodes: [...stage.nodes, node] }));
}

/** Save a task, re-deriving its key from its name. Nothing in the template
 *  points at a node key, so unlike a stage there is nothing to rewrite. */
export function saveNode(
  config: TemplateConfig,
  stageIndex: number,
  nodeIndex: number,
  values: NodeValues,
): TemplateConfig {
  const before = config.stages[stageIndex]?.nodes[nodeIndex];
  if (before === undefined) return config;
  const key = nodeKeyFor(config, values.name, before.key);
  return mapStage(config, stageIndex, (stage) => ({
    ...stage,
    nodes: stage.nodes.map((node, i) => (i === nodeIndex ? { ...values, key } : node)),
  }));
}

export function removeNode(
  config: TemplateConfig,
  stageIndex: number,
  nodeIndex: number,
): TemplateConfig {
  return mapStage(config, stageIndex, (stage) => ({
    ...stage,
    nodes: stage.nodes.filter((_, i) => i !== nodeIndex),
  }));
}

export function moveNode(
  config: TemplateConfig,
  stageIndex: number,
  nodeIndex: number,
  delta: number,
): TemplateConfig {
  return mapStage(config, stageIndex, (stage) => ({
    ...stage,
    nodes: move(stage.nodes, nodeIndex, delta),
  }));
}
