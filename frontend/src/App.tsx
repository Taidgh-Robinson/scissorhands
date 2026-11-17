import { useState } from "react";
import { runPath } from "./api/client";
import { useProjectRuns, useProjects } from "./api/runs";
import RunWatch from "./RunWatch";

function ProjectRuns({ projectId }: { projectId: string }) {
  const { data: runs, error, isLoading } = useProjectRuns(projectId);
  const [selectedUrl, setSelectedUrl] = useState("");
  const options = runs?.map(run => ({
    url: runPath(projectId, run.work_item_id, run.run_id),
    label: `${run.work_item_id} / ${run.run_id} (${run.outcome ?? run.state})`,
  })) ?? [];
  const selected = options.find(option => option.url === selectedUrl);

  return (
    <section>
      <h2>Runs</h2>
      {isLoading && <p>Loading runs…</p>}
      {error && <p role="alert">Could not load runs. {error.message}</p>}
      {runs?.length === 0 && <p>This project has no runs yet.</p>}
      {options.length > 0 && (
        <label>
          Run{" "}
          <select
            value={selected?.url ?? ""}
            onChange={event => setSelectedUrl(event.target.value)}
          >
            <option value="">Select a run</option>
            {options.map(option => (
              <option key={option.url} value={option.url}>{option.label}</option>
            ))}
          </select>
        </label>
      )}
      {selected && <RunWatch key={selected.url} url={selected.url} />}
    </section>
  );
}

export default function App() {
  const { data: projects, error, isLoading } = useProjects();
  const [projectId, setProjectId] = useState("");
  const project = projects?.find(project => project.id === projectId);

  return (
    <main>
      <h1>Scissorhands runs</h1>
      {isLoading && <p>Loading projects…</p>}
      {error && <p role="alert">Could not load projects. {error.message}</p>}
      {projects?.length === 0 && (
        <p>No registered projects. Register a project with the reporting API to see its runs.</p>
      )}
      {projects && projects.length > 0 && (
        <label>
          Project{" "}
          <select
            value={project?.id ?? ""}
            onChange={event => setProjectId(event.target.value)}
          >
            <option value="">Select a project</option>
            {projects.map(project => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {project && (project.available
        ? <ProjectRuns key={project.id} projectId={project.id} />
        : <p>Project folder unavailable.</p>)}
    </main>
  );
}
