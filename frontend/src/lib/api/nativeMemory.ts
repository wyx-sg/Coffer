// frontend/src/lib/api/nativeMemory.ts — agent native-memory discovery and
// take-over (spec 007). Split from agents.ts for the file-size limit.

import { call, enc } from "./agents";

export interface NativeMemoryProject {
  slug: string;
  memory_dir: string;
  fact_count: number;
  managed: boolean;
}

export interface NativeMemoryOut {
  projects: NativeMemoryProject[];
  unmanaged_fact_count: number;
}

export async function getAgentNativeMemory(name: string): Promise<NativeMemoryOut> {
  return call<NativeMemoryOut>("GET", `/agents/${enc(name)}/native-memory`);
}

export interface NativeMemoryImportItem {
  slug: string;
  fact_count: number;
  status: string; // imported | skipped_undecodable | skipped_managed | error
  project_root: string | null;
  store_name: string | null;
  backup_dir: string | null;
  detail: string | null;
}

export interface NativeMemoryImportOut {
  items: NativeMemoryImportItem[];
  imported: number;
  skipped: number;
}

export async function importAgentNativeMemory(name: string): Promise<NativeMemoryImportOut> {
  return call<NativeMemoryImportOut>("POST", `/agents/${enc(name)}/native-memory/import`);
}
