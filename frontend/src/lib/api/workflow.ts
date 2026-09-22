// frontend/src/lib/api/workflow.ts — request helpers for /api/v1/workflow/*
// (spec workflow, FR-044/FR-045).
//
// Wire types are the workflow contract's generated schemas
// (`specs/workflow/contracts/api.openapi.yaml` → `generated/workflow.ts`),
// aliased — never re-derived — under the names the hooks and pages import.
// Transport is the shared `call` (agents/frontend.md §4).
//
// A workflow TEMPLATE is a resource of kind `workflow` (FR-001) and is read
// through the generic /resources API, so there is no template function here.
import { call, callBlob, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/workflow";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Run = Schemas["RunOut"];
export type RunStatus = Run["status"];
export type RunDetail = Schemas["RunDetailOut"];
export type RunCreate = Schemas["RunCreateIn"];
export type RunInput = Schemas["RunInput"];
export type RunInputKind = RunInput["kind"];
/** What a client may SAY when mounting one: no `size`, `path` or `mount`,
 *  which are the server's answer rather than the caller's assertion. */
export type RunInputIn = Schemas["RunInputIn"];
export type InputList = Schemas["InputListOut"];
export type Node = Schemas["NodeOut"];
export type RunStage = Schemas["StageOut"];
export type NodeStatus = Node["status"];
export type NodeAttempt = Schemas["NodeAttemptOut"];
export type AdhocTask = Schemas["AdhocTaskIn"];
export type Say = Schemas["SayIn"];
export type RunNote = Schemas["RunNoteIn"];
export type Artifact = Schemas["ArtifactOut"];
/** One file under a run's directory, as the preview reads it (FR-064). */
export type RunFile = Schemas["RunFileOut"];
export type ArtifactList = Schemas["ArtifactListOut"];
export type Promotion = Schemas["PromotionOut"];
export type Approval = Schemas["ApprovalOut"];
export type ApprovalStatus = Approval["status"];
export type ApprovalDecision = Schemas["ApprovalDecisionIn"];

/** The resource kind a workflow template is registered under (FR-001). */
export const WORKFLOW_TEMPLATE_KIND = "workflow";

// The template's own shape. The contract declares these schemas and serves
// them from NO route on purpose (see `WorkflowTemplate`'s description): a
// template is written through the kind-agnostic resource endpoint (FR-056),
// and what the schemas exist for is the editor — a generated type for the
// shape it authors. So they are aliased here, beside the run types, and the
// editor never re-derives them.
export type TemplateConfig = Schemas["WorkflowTemplate"];
export type TemplateStage = Schemas["TemplateStage"];
export type TemplateNode = Schemas["TemplateNode"];
export type TemplateArtifact = Schemas["TemplateArtifact"];
export type TemplateOnFailure = Schemas["TemplateOnFailure"];

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const workflowApi = {
  // Runs
  listRuns: (status?: RunStatus) =>
    call<Schemas["RunListOut"]>(`/workflow/runs${status ? `?status=${enc(status)}` : ""}`),

  createRun: (body: RunCreate) => call<Run>("/workflow/runs", { method: "POST", body }),

  getRun: (runId: string) => call<RunDetail>(`/workflow/runs/${enc(runId)}`),

  deleteRun: (runId: string) => call<void>(`/workflow/runs/${enc(runId)}`, { method: "DELETE" }),

  /**
   * Choose who runs a task's next attempt, on what, at what effort (FR-071).
   * All three are written verbatim: null clears the override and falls back to
   * the workflow's own answer. Only before the task starts — once its turn is
   * in flight the conversation owns these and the daemon answers 409.
   */
  assignNode: (runId: string, nodeKey: string, body: Schemas["AssignmentIn"]) =>
    call<Schemas["NodeAttemptOut"]>(
      `/workflow/runs/${enc(runId)}/nodes/${enc(nodeKey)}/assignment`,
      { method: "POST", body },
    ),

  /**
   * Rewrite what a run is called and what it is for (FR-070). No `version`:
   * the optimistic lock guards the run's position, and a label moves it
   * nowhere — the status, the stage and the log come back untouched.
   */
  relabelRun: (runId: string, body: Schemas["RunLabelIn"]) =>
    call<Schemas["RunOut"]>(`/workflow/runs/${enc(runId)}`, { method: "PATCH", body }),

  listEvents: (runId: string) =>
    call<Schemas["EventListOut"]>(`/workflow/runs/${enc(runId)}/events`),

  // Nodes. There is no `actOnNode` here: the six node actions are the
  // engine's and the CLI's, and the web UI drives a task by talking to it
  // (FR-063) rather than by pressing Retry. The route stays; this client does
  // not call it, so it does not carry a method for it.
  /**
   * Say something to one task, whatever state it is in (FR-068). The daemon
   * decides what it means — a brief, more to do, or the next attempt — and
   * answers with the attempt the sentence landed on. There is no `version`: a
   * sentence addressed to a named task means the same wherever the run is.
   */
  sayToNode: (runId: string, nodeKey: string, text: string) =>
    call<NodeAttempt>(`/workflow/runs/${enc(runId)}/nodes/${enc(nodeKey)}/say`, {
      method: "POST",
      body: { text } satisfies Say,
    }),

  addAdhocTask: (runId: string, body: AdhocTask) =>
    call<NodeAttempt>(`/workflow/runs/${enc(runId)}/tasks`, { method: "POST", body }),

  // Inputs — what the run READS (FR-032). Editable for the whole of a run's
  // life, not only at creation (FR-050), so all four verbs live here.
  listInputs: (runId: string) => call<InputList>(`/workflow/runs/${enc(runId)}/inputs`),

  /** Mount a knowledge collection or a link. An upload has its own route. */
  addInput: (runId: string, body: RunInputIn) =>
    call<InputList>(`/workflow/runs/${enc(runId)}/inputs`, { method: "POST", body }),

  /**
   * Upload a file the nodes can read. The bytes are stored under the run's own
   * directory (FR-051), so this carries a body rather than a reference — a
   * FormData goes out with no Content-Type and the browser writes the
   * multipart boundary itself (see `call`).
   */
  uploadInput: (runId: string, file: File, label?: string | null) => {
    const form = new FormData();
    form.append("file", file);
    if (label) form.append("label", label);
    return call<InputList>(`/workflow/runs/${enc(runId)}/inputs/uploads`, {
      method: "POST",
      body: form,
    });
  },

  /**
   * Write a note of the developer's own into the run's inputs (FR-069). It
   * becomes a markdown file the run's tasks are told is the developer's words.
   */
  addNote: (runId: string, body: RunNote) =>
    call<InputList>(`/workflow/runs/${enc(runId)}/inputs/notes`, { method: "POST", body }),

  /** Replace a note's contents, keeping the name the tasks know it by. */
  rewriteNote: (runId: string, ref: string, text: string) =>
    call<InputList>(`/workflow/runs/${enc(runId)}/inputs/notes/${enc(ref)}`, {
      method: "PUT",
      body: { text },
    }),

  /** Unmount one input by its `ref`. An uploaded file's bytes go with it. */
  removeInput: (runId: string, inputRef: string) =>
    call<InputList>(`/workflow/runs/${enc(runId)}/inputs/${enc(inputRef)}`, { method: "DELETE" }),

  // Artifacts
  listArtifacts: (runId: string) => call<ArtifactList>(`/workflow/runs/${enc(runId)}/artifacts`),

  /** One file the run reads or wrote. `path` is relative to the run's own
   *  directory; the daemon guards it and caps how much comes back. */
  readFile: (runId: string, path: string) =>
    call<RunFile>(`/workflow/runs/${enc(runId)}/files?path=${enc(path)}`),

  /** One file's bytes — what an `<img>` in a note needs, since the daemon
   *  authorises by header and an image element cannot send one. */
  readFileBytes: (runId: string, path: string) =>
    callBlob(`/workflow/runs/${enc(runId)}/files/raw?path=${enc(path)}`),

  promoteArtifacts: (runId: string, collection: string) =>
    call<Promotion>(`/workflow/runs/${enc(runId)}/promotion`, {
      method: "POST",
      body: { collection },
    }),

  // Approvals
  listApprovals: (params: { runId?: string; status?: ApprovalStatus } = {}) => {
    const query = new URLSearchParams();
    if (params.runId) query.set("run_id", params.runId);
    if (params.status) query.set("status", params.status);
    const qs = query.toString();
    return call<Schemas["ApprovalListOut"]>(`/workflow/approvals${qs ? `?${qs}` : ""}`);
  },

  /** Idempotent: a repeated decision returns the same terminal state (FR-038). */
  decideApproval: (approvalId: string, body: ApprovalDecision) =>
    call<Approval>(`/workflow/approvals/${enc(approvalId)}/decision`, { method: "POST", body }),
};
