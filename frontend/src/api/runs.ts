import useSWR from "swr";
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
