// frontend/src/lib/workflow/templateDraft.test.ts
// The editor's edits, as pure functions. What is pinned here is the part the
// developer never sees and would be hurt by if it were wrong:
//
//   • a KEY is derived from the name and never asked for (FR-060), so it has
//     to be unique and stable enough to be readable;
//   • a stage always has at least one task, because the contract's minimum is
//     one;
//   • the array order is the forward path, so moving a stage is the only way
//     to change what runs after what.
import { describe, expect, test } from "vitest";

import {
  addNode,
  addStage,
  blankNode,
  emptyTemplate,
  moveStage,
  removeNode,
  removeStage,
  saveNode,
  saveStage,
  slugify,
} from "./templateDraft";
import type { TemplateConfig } from "@/lib/api/workflow";

const STAGE = (name: string) => ({ name, optional: false });

/** Design → Coding → Testing, one task each. */
function threeStages(): TemplateConfig {
  let config: TemplateConfig = { stages: [] };
  config = addStage(config, STAGE("Tech Design"));
  config = addStage(config, STAGE("Coding"));
  config = addStage(config, STAGE("Testing"));
  return config;
}

describe("slugify", () => {
  test("makes an addressable identity out of whatever was typed", () => {
    expect(slugify("Tech Design", "stage")).toBe("tech_design");
    expect(slugify("  Ship it! 🚀 ", "stage")).toBe("ship_it");
    expect(slugify("", "stage")).toBe("stage");
    expect(slugify("🚀🚀", "task")).toBe("task");
  });
});

describe("keys are derived, never typed", () => {
  test("a stage and its first task take their keys from the name", () => {
    const config = addStage(emptyTemplate(), STAGE("Tech Design"));
    const stage = config.stages[1];

    expect(stage.key).toBe("tech_design");
    // Same slug, no suffix: stage keys and node keys are separate namespaces,
    // and `stages[i].key` never has to be distinct from a node's.
    expect(stage.nodes[0].key).toBe("tech_design");
  });

  test("two stages with the same name get their own keys", () => {
    let config: TemplateConfig = { stages: [] };
    config = addStage(config, STAGE("Review"));
    config = addStage(config, STAGE("Review"));

    expect(config.stages.map((s) => s.key)).toEqual(["review", "review_2"]);
  });

  test("renaming a stage re-derives its key", () => {
    const config = saveStage(threeStages(), 1, STAGE("Implementation"));

    expect(config.stages[1].key).toBe("implementation");
  });

  test("re-saving a stage under its own name does not suffix its key", () => {
    const config = saveStage(threeStages(), 1, { ...STAGE("Coding"), optional: true });

    expect(config.stages[1].key).toBe("coding");
    expect(config.stages[1].optional).toBe(true);
  });

  test("a task's key is unique across the whole template, not the stage", () => {
    // An event names a node by key alone, so two stages may not both hold a
    // `review`.
    let config = addNode(threeStages(), 0, blankNode("Review"));
    config = addNode(config, 1, blankNode("Review"));

    expect(config.stages[0].nodes[1].key).toBe("review");
    expect(config.stages[1].nodes[1].key).toBe("review_2");
  });

  test("renaming a task re-derives its key without colliding with itself", () => {
    const config = saveNode(threeStages(), 0, 0, blankNode("Draft the TD"));

    expect(config.stages[0].nodes[0].key).toBe("draft_the_td");
  });
});

describe("a stage always has a task", () => {
  test("a new stage comes with one, named after it", () => {
    const config = addStage(emptyTemplate(), STAGE("Coding"));

    expect(config.stages[1].nodes).toHaveLength(1);
    expect(config.stages[1].nodes[0].name).toBe("Coding");
  });

  test("a brand-new template is one stage with one task", () => {
    const config = emptyTemplate();

    expect(config.stages).toHaveLength(1);
    expect(config.stages[0].nodes).toHaveLength(1);
    // The ceiling is the TASK's now, not the template's.
    expect(config.stages[0].nodes[0].attempt_ceiling).toBe(3);
  });

  test("removing a task leaves the others alone", () => {
    const config = removeNode(addNode(threeStages(), 0, blankNode("Review")), 0, 0);

    expect(config.stages[0].nodes.map((n) => n.name)).toEqual(["Review"]);
  });
});

describe("removing a stage", () => {
  test("takes that stage and nothing else", () => {
    const config = removeStage(threeStages(), 1);

    expect(config.stages.map((s) => s.key)).toEqual(["tech_design", "testing"]);
  });
});

describe("order is the forward path", () => {
  test("moving a stage moves it, and moving past either end does nothing", () => {
    const config = threeStages();

    expect(moveStage(config, 2, -1).stages.map((s) => s.key)).toEqual([
      "tech_design",
      "testing",
      "coding",
    ]);
    expect(moveStage(config, 0, -1).stages).toEqual(config.stages);
    expect(moveStage(config, 2, 1).stages).toEqual(config.stages);
  });
});
