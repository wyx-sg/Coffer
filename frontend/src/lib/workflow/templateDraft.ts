// frontend/src/lib/workflow/templateDraft.ts
// Pure edits on a template config — the editor's whole vocabulary (FR-054).
//
// The forward path is the ARRAY ORDER: there are no forward edges, so
// "reorder the stages" is the only way to change what runs after what, and it
// is a list operation rather than a graph one. `edges` carries feedback only —
// a later stage sending the run back to an earlier one — which is why
// `earlierStages` exists and no `laterStages` does.
//
// KEYS ARE DERIVED HERE AND NEVER TYPED (FR-060). A key is an identity the
// engine reads no meaning from (FR-003); asking a developer to invent one is
// asking them to do the computer's filing. So a stage's and a task's key are
// slugs of their name, made unique, recomputed whenever the name changes —
// and a stage's rename is rewritten through the feedback edges that named it
// in the same edit, so a rename can never orphan an edge. This is safe
// because a template is only ever data: a run froze its own copy of it
// (FR-011), so nothing in flight is reading these keys.
//
// Every function returns a new config; nothing here mutates its argument.
import type { TemplateConfig, TemplateEdge, TemplateNode, TemplateStage } from "@/lib/api/workflow";

/** Who does the work. Two values, because the engine only ever asked one
 *  question of this field: dispatch a turn, or stop and wait for a person. */
export const NODE_TYPES = ["ai", "manual"] as const;
export const APPROVALS = ["never", "always"] as const;
export const FAILURE_ACTIONS = ["stop", "continue", "retry"] as const;

/** What the stage dialog edits: everything about a stage except its tasks. */
export interface StageValues {
  name: string;
  optional: boolean;
  /** The feedback edges leaving this stage, as the dialog holds them. */
  sendBack: { reason: string; to_stage: string }[];
}

/** What the task dialog edits — everything a node has except its identity. */
export type NodeValues = Omit<TemplateNode, "key">;

/** A lowercase slug the engine reads no meaning from — it is an identity, not
 *  a word (FR-003). Empty input still has to produce something addressable. */
export function slugify(value: string, fallback: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug.length > 0 ? slug : fallback;
}

/** Make `candidate` unique against `taken` by suffixing, so a second "Review"
 *  is `review_2` rather than a refusal the developer has to decode. */
function unique(candidate: string, taken: Set<string>): string {
  if (!taken.has(candidate)) return candidate;
  let n = 2;
  while (taken.has(`${candidate}_${n}`)) n += 1;
  return `${candidate}_${n}`;
}

function stageKeys(config: TemplateConfig, except?: string): Set<string> {
  return new Set(config.stages.map((s) => s.key).filter((key) => key !== except));
}

/** Every node key in the template — the uniqueness scope is the WHOLE
 *  template, not the stage, because an event names a node by key alone. */
function nodeKeys(config: TemplateConfig, except?: string): Set<string> {
  return new Set(
    config.stages.flatMap((s) => s.nodes.map((n) => n.key)).filter((key) => key !== except),
  );
}

/** The key a stage with this name gets, leaving `except`'s own key free so a
 *  stage that is merely re-saved does not collide with itself. */
function stageKeyFor(config: TemplateConfig, name: string, except?: string): string {
  return unique(slugify(name, "stage"), stageKeys(config, except));
}

function nodeKeyFor(config: TemplateConfig, name: string, except?: string): string {
  return unique(slugify(name, "task"), nodeKeys(config, except));
}

/** An existing node, as the task dialog edits it: everything but the key.
 *
 *  Written out rather than spread-minus-key, and typed, so that a field added
 *  to `TemplateNode` is a compile error here rather than a field the dialog
 *  silently drops on save. It also settles the optional ones to the same
 *  defaults `blankNode` uses, so the dialog never holds `undefined`. */
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
  };
}

/** What a brand-new template starts as: one stage, one task. The contract's
 *  minima are `stages: 1` and `nodes: 1` per stage, so an empty shell would be
 *  refused the moment it was written. */
export function emptyTemplate(): TemplateConfig {
  return addStage(
    { stages: [], edges: [], attempt_ceiling: 3 },
    {
      name: "",
      optional: false,
      sendBack: [],
    },
  );
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

/** The feedback edges of every stage BUT `fromStage`, so saving one stage's
 *  edges replaces exactly its own and leaves the rest alone. */
function edgesExceptFrom(config: TemplateConfig, fromStage: string): TemplateEdge[] {
  return (config.edges ?? []).filter((edge) => edge.from_stage !== fromStage);
}

/**
 * Add a stage, with one task in it.
 *
 * The task is not optional and not a placeholder the developer has to notice:
 * the contract's minimum is one node per stage, and the engine takes
 * `stage.nodes[0]` when a feedback edge lands on a stage — a stage with no
 * tasks is not a thing that can exist. It is named after the stage because a
 * one-task stage is the common shape and "Tech Design does the tech design"
 * reads better than "Tech Design contains New task 3".
 */
export function addStage(config: TemplateConfig, values: StageValues): TemplateConfig {
  const key = stageKeyFor(config, values.name);
  const stage: TemplateStage = {
    key,
    name: values.name,
    optional: values.optional,
    nodes: [{ ...blankNode(values.name), key: nodeKeyFor(config, values.name) }],
  };
  const added = withStages(config, [...config.stages, stage]);
  return { ...added, edges: [...edgesExceptFrom(added, key), ...asEdges(key, values.sendBack)] };
}

function asEdges(fromStage: string, sendBack: StageValues["sendBack"]): TemplateEdge[] {
  return sendBack
    .filter((row) => row.to_stage.length > 0)
    .map((row) => ({ from_stage: fromStage, to_stage: row.to_stage, reason: row.reason }));
}

/**
 * Save a stage's own fields, re-deriving its key from its name.
 *
 * A changed key is rewritten through every edge that named it — including the
 * ones this save is writing — so a rename and the edges that point at it move
 * together or not at all.
 */
export function saveStage(
  config: TemplateConfig,
  index: number,
  values: StageValues,
): TemplateConfig {
  const before = config.stages[index];
  if (before === undefined) return config;
  const key = stageKeyFor(config, values.name, before.key);
  const renamed = mapStage(config, index, (stage) => ({
    ...stage,
    key,
    name: values.name,
    optional: values.optional,
  }));
  const repointed = (renamed.edges ?? []).map((edge) => ({
    ...edge,
    from_stage: edge.from_stage === before.key ? key : edge.from_stage,
    to_stage: edge.to_stage === before.key ? key : edge.to_stage,
  }));
  return {
    ...renamed,
    edges: [
      ...repointed.filter((edge) => edge.from_stage !== key),
      ...asEdges(key, values.sendBack),
    ],
  };
}

/** Removing a stage removes the feedback edges that named it: an edge to a
 *  stage that is gone is refused, and leaving one behind would refuse a save
 *  the developer never made. */
export function removeStage(config: TemplateConfig, index: number): TemplateConfig {
  const gone = config.stages[index]?.key;
  return {
    ...config,
    stages: config.stages.filter((_, i) => i !== index),
    edges: (config.edges ?? []).filter((e) => e.from_stage !== gone && e.to_stage !== gone),
  };
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

/** The stages an edge FROM the stage at `index` may point back to: strictly
 *  earlier ones, and nothing else. A forward edge is the array order and is
 *  not written (FR-005) — the editor offers no way to draw one, and the
 *  daemon refuses one if it ever arrives. */
export function earlierStages(config: TemplateConfig, index: number): TemplateStage[] {
  return index <= 0 ? [] : config.stages.slice(0, index);
}

/** The feedback edges leaving a stage, as the stage dialog holds them. */
export function sendBackOf(config: TemplateConfig, stageKey: string): StageValues["sendBack"] {
  return (config.edges ?? [])
    .filter((edge) => edge.from_stage === stageKey)
    .map((edge) => ({ reason: edge.reason, to_stage: edge.to_stage }));
}
