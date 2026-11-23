export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return response.json();
}

export function projectPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}`;
}

export function runPath(projectId: string, workItemId: string, runId: string): string {
  return `${projectPath(projectId)}/work-items/${encodeURIComponent(workItemId)}/runs/${encodeURIComponent(runId)}`;
}
