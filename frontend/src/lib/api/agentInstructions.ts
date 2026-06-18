// frontend/src/lib/api/agentInstructions.ts — instructions-delivery wire calls
// (spec 004 item 1). Split from agents.ts for the file-size limit; reuses the
// shared `call`/`enc` helpers there.
import { call, enc } from "./agents";

export interface MasterInstructions {
  content: string;
  fingerprint: string;
}

export interface InstructionsStatus {
  delivered: boolean;
  in_sync: boolean;
}

export const agentInstructionsApi = {
  getMaster: () => call<MasterInstructions>("GET", "/instructions"),
  setMaster: (body: { content: string; expected_fingerprint?: string }) =>
    call<MasterInstructions>("PUT", "/instructions", body),
  status: (name: string) => call<InstructionsStatus>("GET", `/agents/${enc(name)}/instructions`),
  deliver: (name: string) => call<InstructionsStatus>("POST", `/agents/${enc(name)}/instructions`),
  remove: (name: string) => call<InstructionsStatus>("DELETE", `/agents/${enc(name)}/instructions`),
  adopt: (name: string) =>
    call<MasterInstructions>("POST", `/agents/${enc(name)}/instructions/adopt`),
};
