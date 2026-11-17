import useSWR from "swr";
import { isTerminal } from "./activity";
import { fetchJson, projectPath } from "./client";

interface Project {
  id: string;
  name: string;
  available: boolean;
}

export interface RunSummary {
  work_item_id: string;
  run_id: string;
  state: "queued" | "running" | "finished" | "cancelled" | "interrupted" | "unknown";
  outcome: string | null;
}

export function useProjects() {
  return useSWR("/api/projects", fetchJson<Project[]>, { refreshInterval: 10000 });
}

export function useProjectRuns(projectId: string) {
  return useSWR(`${projectPath(projectId)}/runs`, fetchJson<RunSummary[]>, {
    refreshInterval: 5000,
  });
}

export interface RunDetail {
  summary: RunSummary;
  loops: number[];
  activity?: {
    state: "available" | "missing" | "invalid" | "unavailable" | "unsafe" | "too_large";
    data: unknown;
  };
}

export function useRunDetail(url: string) {
  return useSWR(url, fetchJson<RunDetail>, {
    refreshInterval: data => isTerminal(data?.summary.state) ? 0 : 2000,
  });
}
