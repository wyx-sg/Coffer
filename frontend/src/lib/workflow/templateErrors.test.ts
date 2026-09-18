// frontend/src/lib/workflow/templateErrors.test.ts
// A refusal is only useful if the editor can find the field it names (FR-055),
// and the daemon spells that field three different ways depending on how deep
// the rejection was raised. All three have to reduce to the same path.
import { describe, expect, test } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { errorId, templateRefusal } from "@/lib/workflow/templateErrors";

describe("templateRefusal", () => {
  test("reads the path out of a message that leads with it", () => {
    const error = new ApiError(
      "WORKFLOW_TEMPLATE_INVALID",
      "stages[1].nodes[0].skill: no registered skill named 'ghost'",
    );
    expect(templateRefusal(error)).toEqual({
      path: "stages[1].nodes[0].skill",
      message: "no registered skill named 'ghost'",
    });
  });

  test("finds the path inside a Pydantic validation report", () => {
    const error = new ApiError(
      "CONFIG_INVALID",
      "1 validation error for WorkflowTemplateConfig\n  Value error, " +
        "stages[0].nodes[2].artifacts[1].name: must be a single path segment " +
        "[type=value_error, input_value={'stages': []}]",
    );
    expect(templateRefusal(error)).toEqual({
      path: "stages[0].nodes[2].artifacts[1].name",
      message: "must be a single path segment",
    });
  });

  test("prefers a structured path and reason over the message", () => {
    const error = new ApiError("WORKFLOW_TEMPLATE_INVALID", "stages: something", {
      path: "edges[0].to_stage",
      reason: "no stage named 'shipping'",
    });
    expect(templateRefusal(error)).toEqual({
      path: "edges[0].to_stage",
      message: "no stage named 'shipping'",
    });
  });

  test("names a task's own ceiling, which is where the number lives now", () => {
    const error = new ApiError(
      "CONFIG_INVALID",
      "stages[0].nodes[1].attempt_ceiling: must be >= 1",
    );
    expect(templateRefusal(error)?.path).toBe("stages[0].nodes[1].attempt_ceiling");
  });

  test("is null when nothing names a field", () => {
    expect(templateRefusal(new ApiError("INTERNAL_ERROR", "internal error"))).toBeNull();
    expect(templateRefusal(new Error("offline"))).toBeNull();
    expect(templateRefusal(null)).toBeNull();
  });
});


test("a field's error id is derived from its path", () => {
  expect(errorId("stages[1].nodes[0].skill")).toBe("template-error-stages[1].nodes[0].skill");
});
