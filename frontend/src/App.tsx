import { useState } from "react";
import { runPath } from "./api/client";
import { useProjectRuns, useProjects } from "./api/runs";
import RunWatch from "./RunWatch";
import { useTheme, Viewer } from "./themes";

function RunExplorer() {
  const { Choice, Frame, Icon, illustration } = useTheme();
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const [runUrl, setRunUrl] = useState("");
  const project = projects.data?.find(entry => entry.id === projectId);
  const runs = useProjectRuns(project?.available ? project.id : null);
  const runOptions = (runs.data ?? []).map(run => ({
    value: runPath(projectId, run.work_item_id, run.run_id),
    label: `${run.work_item_id} / ${run.run_id} (${run.outcome ?? run.state})`,
  }));
  const selected = runOptions.find(option => option.value === runUrl);
  const projectOptions = (projects.data ?? []).map(entry => ({ value: entry.id, label: entry.name }));

  return (
    <main className="explorer">
      <div className="intro">
        <div>
          <h1>Run explorer</h1>
          <p>Inspect agent runs, loop artifacts, and verification results.</p>
        </div>
        {illustration && <img className="intro-art" src={illustration} alt="" />}
      </div>
      <div className="workspace">
        <aside className="sheet selectors" aria-label="Run selection">
          <Frame />
          <div className="panel-heading"><Icon name="folder-open" /><h2>Workspace</h2></div>
          <div className="fields">
            <Choice
              label="Project"
              value={project?.id ?? ""}
              options={[{ value: "", label: "Select a project" }, ...projectOptions]}
              onChange={id => { setProjectId(id); setRunUrl(""); }}
              disabled={!projectOptions.length}
            />
            {projects.isLoading && <p role="status">Loading projects…</p>}
            {projects.error && <p role="alert">Could not load projects. {projects.error.message}</p>}
            {projects.data?.length === 0 && <p>No registered projects. Register a project with the reporting API to see its runs.</p>}
            {project && !project.available && <p>Project folder unavailable.</p>}
            <Choice
              label="Run"
              value={selected?.value ?? ""}
              options={[{ value: "", label: "Select a run" }, ...runOptions]}
              onChange={setRunUrl}
              disabled={!runOptions.length}
            />
            {runs.isLoading && <p role="status">Loading runs…</p>}
            {runs.error && <p role="alert">Could not load runs. {runs.error.message}</p>}
            {runs.data?.length === 0 && <p>This project has no runs yet.</p>}
          </div>
          {projects.data && <p className="selection-count">
            {projectOptions.length} registered {projectOptions.length === 1 ? "project" : "projects"}
          </p>}
        </aside>
        <div className="sheet inspector">
          <Frame />
          <div className="panel-heading"><Icon name="file-text" /><h2>Run detail</h2></div>
          {selected ? <RunWatch key={selected.value} url={selected.value} /> : (
            <div className="empty-detail">
              <span className="empty-icon"><Icon name="layers" size={48} /></span>
              <h3>No run selected</h3>
              <p>Choose a run in the workspace to view its details.</p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function App() {
  return <Viewer><RunExplorer /></Viewer>;
}
