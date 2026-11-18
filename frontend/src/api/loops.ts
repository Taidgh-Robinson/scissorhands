import useSWR from "swr";
import { fetchJson } from "./client";
import type { Artifact } from "./runs";

export interface LoopReceipt {
  recorded_at: string;
  iteration: number;
  agent: string;
  agent_exit_code: number;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  agent_elapsed_seconds: number | null;
  verification_elapsed_seconds: number | null;
  git_before_tree: string | null;
  git_after_tree: string | null;
  outcome: string;
  rejection_reason: string | null;
  progress_updated: boolean;
  progress: string | null;
  status_updated: boolean;
  status_readable: boolean;
  criteria: { id: string; text: string; met: boolean | null; evidence: string }[];
  verification: {
    required: boolean;
    passed: boolean | null;
    commands: { command: string; return_code: number; passed: boolean }[];
  };
  completion_marker_claimed: boolean;
  completion_accepted: boolean;
  plan_required: boolean;
  plan_updated: boolean;
  plan_error: string | null;
  plan_revised: boolean;
  plan: {
    schema_version: number;
    iteration: number;
    steps: {
      id: string;
      objective: string;
      acceptance_criteria: string[];
      status: "pending" | "in_progress" | "completed" | "blocked";
    }[];
    selected_step_id: string;
    revision_reason: string;
    handoff: string;
  } | null;
}

export interface LoopDetail {
  work_item_id: string;
  run_id: string;
  number: number;
  // Receipts from older writers can omit fields.
  receipt: Artifact<Partial<LoopReceipt>>;
}

export const loopArtifacts = [
  ["report", "Report"],
  ["prompt", "Prompt"],
  ["agent_output", "Agent output"],
  ["final_message", "Final message"],
  ["status", "Status"],
  ["plan", "Plan"],
  ["progress", "Progress"],
  ["patch", "Patch"],
] as const;

export type LoopArtifactKind = typeof loopArtifacts[number][0] | "verification_output";
export const pageBytes = 64 * 1024;

function useLoopResource<T>(url: string, live: boolean) {
  // Changing from live to settled fetches a final snapshot before polling stops.
  return useSWR([url, live], ([path]) => fetchJson<T>(path), {
    refreshInterval: live ? 2000 : 0,
  });
}

export function useLoopDetail(loopUrl: string, live: boolean) {
  return useLoopResource<LoopDetail>(loopUrl, live);
}

export function useLoopArtifact(
  loopUrl: string, kind: LoopArtifactKind, live: boolean, offset: number, verification?: number,
) {
  const query = new URLSearchParams({ limit: String(pageBytes), offset: String(offset) });
  if (verification !== undefined) query.set("verification", String(verification));
  return useLoopResource<Artifact>(`${loopUrl}/artifacts/${kind}?${query}`, live);
}
