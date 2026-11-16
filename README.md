# Scissorhands

A deliberately small Python harness for running bounded, fresh-context coding-agent loops with
[Claude Code](https://code.claude.com/), [Codex](https://developers.openai.com/codex/), or
[OpenCode](https://opencode.ai/).

Here, an **agent loop** means: give a coding agent the same goal repeatedly, let each fresh run
inspect the work left by previous runs, and stop when the agent emits an explicit completion
promise. The repository—not chat history—is the shared memory.

## Quick start

```bash
uv sync
uv run python -m unittest discover -s tests -v

# Edit WORK_ITEM.toml first, then choose an agent:
uv run scissorhands --agent claude --work-item WORK_ITEM.toml --max-iterations 5
uv run scissorhands --agent codex --work-item WORK_ITEM.toml --max-iterations 5
uv run scissorhands --agent opencode --work-item WORK_ITEM.toml --max-iterations 5

# Target a different project without changing your working directory:
uv run scissorhands --root /path/to/project --agent codex --work-item WORK_ITEM.toml
```

`--root` defaults to the current directory. Relative work-item and contract paths resolve
against that project, and execution and run artifacts use the same root.

Each iteration starts a new agent session. Each invocation gets the next numbered run under
`.scissorhands/<work-item-id>/run-0001/`, with one `loop-0001/` folder per iteration:

- `work-item.json` and `work-item.toml` preserve the work item; `run.json` records the agent,
  model, approval setting, iteration limit, start time, and starting Git commit.
- `loop-0001/progress.md` is the agent's durable handoff note. The next loop gets a copy.
- `loop-0001/plan.json` is the agent's implementation plan and selected objective. Each step
  has a stable ID, intended outcome, acceptance-criterion links, and claimed status. The next
  loop gets a copy; the agent selects one objective and updates the plan for that iteration.
- `loop-0001/status.json` is the agent's met/unmet assessment of each checklist item, with evidence.
  The harness prints it as a checklist after every iteration. A completion marker is accepted only
  when the file was updated during that iteration and every definition-of-done and acceptance-
  criteria entry is present with `met` set to `true` and non-empty evidence.
- `loop-0001/prompt.md` saves the exact prompt; `iteration-1.log` saves combined agent output.
- `loop-0001/changes.patch` saves the Git diff produced during that loop, including staged edits
  and non-ignored new files. It is empty when no code changed. The harness leaves your Git index
  untouched.
- `run-0001/changes.patch` saves the cumulative Git diff from before the first loop through
  the end of the run.
- Codex also writes its final response to `iteration-1.final.txt`.
- `loop-0001/iteration-1.json` is the harness-owned receipt for that iteration. It
  preserves the progress text, criteria and implementation-plan snapshots, whether each was
  updated, verification results, the completion decision, timing, before/after Git tree IDs,
  and the iteration outcome.
  Verification command output is saved separately as `verification-N.log`.
- `loop-0001/iteration-1.md` and the run's `report.md` summarize the outcome. The run's
  `report.json` is created at startup and updated after each completed loop, so an interrupted
  run retains a machine-readable record of its last completed loop.

New runs start with clean agent state. An interrupted run retains its folder and number.

The loop stops when the agent puts `<promise>COMPLETE</promise>` on a line by itself and submits
fresh, fully-met criteria status and a valid implementation plan with every step completed,
when an agent command fails, or when the iteration limit is reached. Reaching the limit returns
exit code 2; an agent failure returns 1.

If the work item lists `verification` commands, the harness runs them itself after every iteration
instead of trusting the agent's report. The completion marker is only accepted when every command
exits 0. When a command fails, the tail of its output is added to the next iteration's prompt so
the fresh session starts from the real failure.

## Safety model

The defaults are intentionally conservative:

- Codex runs with `--sandbox workspace-write`.
- Claude Code and OpenCode use their configured permission policies. Claude Code runs in `--print`
  mode, where any tool call your settings do not already allow is denied rather than prompted, so
  allow the edit and test commands you expect in `.claude/settings.json` before a run.
- No backend receives an automatic-approval flag unless you pass `--auto-approve`.
- Every run must have a positive `--max-iterations` value.
- `verification` commands run through your shell in the repository root, outside the agent's
  sandbox, because they come from your work item. They are read once at startup, so an agent
  editing `WORK_ITEM.toml` mid-run cannot change what the harness executes. They do run code the
  agent wrote (your tests), just as running the tests yourself would.

`--auto-approve` maps to `codex exec --approve-for-me`, `claude --permission-mode auto`, and
`opencode run --auto`. The harness never passes Claude Code's `bypassPermissions` mode. OpenCode labels
its flag dangerous, so use it only inside a repository you trust and review your agent/tool
configuration first.

Use `--dry-run` to inspect the selected command and composed prompt without invoking an agent:

```bash
uv run scissorhands --agent opencode --work-item WORK_ITEM.toml --dry-run
```

Models are backend-specific and optional:

```bash
uv run scissorhands --agent claude --model sonnet --work-item WORK_ITEM.toml
uv run scissorhands --agent codex --model YOUR_CODEX_MODEL --work-item WORK_ITEM.toml
uv run scissorhands --agent opencode --model provider/model --work-item WORK_ITEM.toml
```

## Writing a useful work item

Describe the work in `WORK_ITEM.toml` using the required stable `id`, `title`, `description`,
`definition_of_done`, and `acceptance_criteria` fields. These optional arrays shape the work
further:

- `relevant_paths`: files and directories to start from, so each fresh session spends less time
  exploring.
- `constraints`: implementation boundaries.
- `non_goals`: nearby work the agent should leave alone.
- `verification`: commands the harness runs after every iteration.

The harness validates the work item, renders it into a consistent prompt, and adds the iteration
and completion contract automatically.

Definition of done describes the quality bar shared by the whole item, such as passing tests and
updated documentation. Acceptance criteria describe observable behavior specific to the requested
change. Keep each criterion independently verifiable, and do not include the completion marker.
The prompt labels them `DoD-1`, `DoD-2`, … and `AC-1`, `AC-2`, … in file order, and the agent
reports status against those IDs.

## One objective per loop

On the first iteration, the agent inspects the project and breaks the work item into small,
verifiable implementation steps. Before changing implementation code, it writes the current
loop's `plan.json` and selects exactly one step. Related implementation, tests, and documentation
belong to that objective. An unfinished step may be selected again in the next fresh session.
Verification failures take priority: select or add a repair step before unrelated work.

For example, a two-criterion export work item might start with:

```json
{
  "schema_version": 1,
  "iteration": 1,
  "steps": [
    {
      "id": "STREAM",
      "objective": "Stream exported JSON records without buffering the input.",
      "acceptance_criteria": ["AC-1"],
      "status": "in_progress"
    },
    {
      "id": "CLI",
      "objective": "Expose streaming export through the CLI.",
      "acceptance_criteria": ["AC-2"],
      "status": "pending"
    }
  ],
  "selected_step_id": "STREAM",
  "revision_reason": "Initial implementation plan.",
  "handoff": "Starting the streaming implementation."
}
```

Before exiting, the agent updates the selected step's status and writes a concrete `handoff`
describing the result, any blocker, and the next step. Status is `pending`, `in_progress`,
`completed`, or `blocked`; only the selected step may be `in_progress`, and it cannot remain
`pending`. Every step links to one or more known AC IDs, and the plan must cover all acceptance
criteria. Keep IDs stable for the same steps and retain completed steps. Creating a plan or
changing its ordered step definitions requires a non-empty `revision_reason`; changing only
statuses, selection, or handoff does not.

The harness captures the plan before running verification and includes the selected objective,
revision reason, and handoff in the terminal and Markdown reports. Receipts preserve the complete
snapshot, and `report.json` includes each loop's objective. Missing, invalid, stale, and unfinished
plans cannot support completion. Validation feedback is included in the next prompt. Each new
run starts with a new plan; prior loop snapshots remain available for review.

Plans and step completion remain agent claims. The harness validates the final recorded plan
and its freshness; it does not establish that the objective was written before code edits or
that all changes stayed within it. Criteria checks and harness-run verification still apply.

## Customizing the iteration contract

The harness appends an iteration contract to every prompt. The default lives in
`src/scissorhands/prompting/contract.md`. To try different wording without editing code, copy that file,
change it, and pass it with `--contract`:

```bash
uv run scissorhands --agent codex --work-item WORK_ITEM.toml --contract my-contract.md --dry-run
```

The template uses Python `string.Template` placeholders:

- `$marker` (required): the completion marker the harness looks for.
- `$iteration` and `$max_iterations`: the current iteration and the limit.
- `$final_iteration_note`: the wrap-up instructions on the last iteration, empty otherwise.
- `$verification_feedback`: failing verification output from the previous iteration, empty
  otherwise.
- `$progress_path` and `$status_path`: paths to the current loop's agent-written state.
- `$plan_path`: path to the current loop's implementation plan.

Unknown placeholders are rejected at startup. Write a literal `$` as `$$`.
Custom contracts with hard-coded `.scissorhands/progress.md` or `.scissorhands/status.json` paths
should replace them with `$progress_path` and `$status_path`.
Implementation-plan instructions are always included, including with a custom iteration contract.
Custom contracts should keep their guidance consistent with selecting one objective and updating
the plan before claiming completion. Older receipts without planning fields remain readable.

Start with two or three iterations and inspect the run report, loop progress notes, and the Git diff.
Small limits make it much easier to learn how prompt wording affects convergence.

## Project layout

```text
src/scissorhands/
  application/        Shared entry points for CLI and future API callers
    models.py         Run requests and previews
    runs.py           Validation, preview, reservation, and async execution
  cli/                Argument parsing, command entry point, terminal output
  api/                Project registry, HTTP reporting routes, and local server
  core/               Work-item, criterion, iteration, and verification models
    loop/             Orchestration, iteration execution, subprocesses, observers
  storage/            Project layout and filesystem operations
    repository.py     Read-only run and artifact queries
    paths.py          Directory discovery, IDs, and path validation
    artifacts.py      Known artifact names and bounded file decoding
    runs.py           Run allocation, snapshots, and artifact persistence
    reports/          Manifest JSON, loop reports, and run reports
  prompting/          Work-item rendering, prompt composition, contract templates
  agents.py           Agent-specific commands and completion-output handling
tests/                Tests grouped by application, CLI, core, storage, and prompting
docs/planning/        Roadmaps and design drafts
WORK_ITEM.toml        Editable work item used by the default CLI command
```

Planning documents are design drafts and may describe earlier names or proposed features.

The interface boundary is `scissorhands.application`:

```python
from scissorhands.application import RunObserver, RunRepository, RunRequest, RunService
```

The reporting API in `src/scissorhands/api/` uses these shared operations with each
registered project's root. Run management policy belongs in `application/`, loop
decisions in `core/`, and file access in `storage/`. Neither the backend nor its
models import the CLI or an HTTP framework; architecture tests guard this boundary.

The CLI command and on-disk artifact formats are unchanged. Python imports from the old
`core.run_service`, `core.run_repository`, and `core.runner` modules should migrate to
`scissorhands.application` or the specific owner modules shown above. Work-item prompt
rendering is now `prompting.work_items.render_work_item()`, and TOML loading is
`storage.work_items.load_work_item()`.

## Using the run service from an async application

`RunService.prepare()` and `RunService.preview()` are synchronous validation and
preview helpers. `RunService.run()` is awaitable. To obtain a run ID before the
agent starts, call `config, paths = await service.reserve(request)`, then run
`await service.run_reserved(config, paths)` in an application-owned task. The
reserved manifest starts in `queued` state; execution changes it to `running`.
Cancelling that task stops the active agent or verification subprocess and marks
the manifest `cancelled`. The CLI uses `asyncio.run()` to keep its existing
synchronous entry point and exit codes.

Backend execution is silent by default. Pass `observer=...` to `RunService` to receive
iteration, agent-output, status, verification, and warning notifications. The CLI supplies
`cli.reporting.TerminalReporter` to preserve its terminal output. Other interfaces can
subclass `RunObserver` and override the hooks they need. Hooks are synchronous and must
return promptly; storage warnings can arrive from worker threads. An async observer
integration should enqueue events using its event loop's thread-safe facilities.
Custom invokers own their output forwarding; the default subprocess invoker forwards
output to the supplied observer automatically. Persisted artifacts remain the source
of truth for history and polling.

## Reading run data from another application

`RunRepository(root)` reads the `.scissorhands/` tree in any explicitly selected project
folder. It does not require a Git repository, work-item TOML, installed agent, or web
framework, and it never creates directories or rewrites artifacts. Keep execution in
`RunService` and use the repository for queries from a future `api/` package:

```python
from dataclasses import asdict
from pathlib import Path

from scissorhands.application import RunRepository

repository = RunRepository(Path("/path/to/project"))
work_items = repository.list_work_items()
runs = repository.list_runs()  # optionally filter with work_item_id="TASK-1"
if runs:
    run = runs[0]
    detail = repository.read_run(run.work_item_id, run.run_id)
    payload = asdict(detail)  # plain JSON-serializable values
    if detail.loops:
        loop = repository.read_loop(run.work_item_id, run.run_id, detail.loops[-1])
        output = repository.read_artifact(
            run.work_item_id,
            run.run_id,
            "agent_output",
            loop=loop.number,
            tail=True,
            limit=16_384,
        )
```

Both work-item and run IDs identify a run; numbering repeats across work items and
projects. Lists are ordered by work-item ID and ascending run number. A project with
no `.scissorhands/` folder returns empty lists. Missing project, requested work-item,
run, or loop directories raise `FileNotFoundError`; invalid IDs or options raise
`ValueError`. Directory symlinks are excluded from discovery and rejected on direct
access with `UnsafeArtifactPath` (a `ValueError`).

Each artifact has a `state`: `available`, `missing`, `invalid`, `unavailable`, `unsafe`,
or `too_large`. Missing or damaged manifests leave the run visible with an `unknown`
state. Run details also discover loop directories that do not yet have a receipt.
Manifest lifecycle values are persisted observations; `running` alone does not prove
that a process is still alive. Receipts and manifests retain their original fields,
including the distinction between agent claims and harness verification decisions.

Run artifact kinds are `manifest`, `settings`, `work_item`, `work_item_toml`, `report`,
and `patch`. Supplying `loop=N` selects loop kinds: `receipt`, `report`, `agent_output`,
`final_message`, `status`, `plan`, `progress`, `prompt`, `patch`, and `verification_output`.
The latter also requires `verification=N`. Callers cannot supply arbitrary filenames;
file symlinks must resolve inside the selected run.

JSON reads require an object and are capped at 4 MiB. Text reads default to 64 KiB,
with a maximum of 1 MiB per call. Use `offset` and `limit` for byte windows, or
`tail=True` and `limit` for recent output. Results include the byte offset, bytes read,
observed total size, and truncation flag. Invalid or split UTF-8 characters are replaced.
Files are read independently, so active-run responses are not an atomic snapshot.

Repository methods perform synchronous filesystem I/O. FastAPI runs the synchronous
reporting handlers in a worker thread and maps repository errors to HTTP responses.

## Reporting API

Install the optional web dependencies and start the local server:

```bash
uv sync --extra api
uv run --extra api scissorhands-api
```

The server listens on `127.0.0.1:8000` by default. Its interactive API reference is
at `http://127.0.0.1:8000/docs`. A user-level SQLite file stores project registrations;
set `SCISSORHANDS_REGISTRY_DB` or pass `--registry-db` to choose another location.
Only project IDs, names, paths, and registration times go in this database. Reports
remain in each project's `.scissorhands/` tree.

Register as many project folders as needed with `POST /api/projects`:

```bash
curl -X POST http://127.0.0.1:8000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"path":"/absolute/path/to/project"}'
curl http://127.0.0.1:8000/api/projects
curl http://127.0.0.1:8000/api/runs
```

The registration response contains an opaque project `id`. Use it in
`GET /api/projects/{project_id}/runs` or the run-detail route
`GET /api/projects/{project_id}/work-items/{work_item_id}/runs/{run_id}`.
Run details list loop numbers. Append `/loops/{number}` to read a loop receipt,
`/artifacts/{kind}` for a run artifact, or `/loops/{number}/artifacts/{kind}` for a
loop artifact. Text artifacts support byte `offset`, `limit`, and `tail` parameters.
Missing or damaged artifacts have an explicit `state` in the response. The
`GET /api/runs` route combines runs from every readable registered project.
`DELETE /api/projects/{project_id}` removes a registration without deleting run files.

`POST /api/projects/{project_id}/work-items` generates a structured work item and writes it
into that project as TOML. Send the same fields as `WORK_ITEM.toml` (`id`, `title`,
`description`, `definition_of_done`, `acceptance_criteria`, and the optional `constraints`,
`verification`, `relevant_paths`, `non_goals` arrays), validated with the same rules the CLI
applies when loading a work item:

```bash
curl -X POST http://127.0.0.1:8000/api/projects/$PROJECT_ID/work-items \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "EXPORT-1",
    "title": "Add export",
    "description": "Export records as JSON.",
    "definition_of_done": ["Tests pass."],
    "acceptance_criteria": ["The output is valid JSON."]
  }'
```

By default this writes `WORK_ITEM.toml` at the project root, matching the CLI's default
`--work-item` path. Pass a relative `path` to write elsewhere (parent directories are created
as needed); the path must stay inside the project and may not point through a symlink. The
file is not overwritten unless the request also sets `"overwrite": true`, in which case it
replaces the existing file. The response includes the destination `path`, the rendered
`toml` text, and the validated `work_item` fields. Validation failures (empty required
fields, a malformed `id`) return 400; an unsafe or escaping `path` also returns 400; an
existing file without `overwrite` returns 409.

The combined listing returns an object with `runs` and `errors` arrays (rather than
a bare run array). Each error includes `project_id`, `status_code`, and `detail`:

```json
{
  "runs": [],
  "errors": [
    {"project_id": "unavailable-project-id", "status_code": 409,
     "detail": "Project folder is unavailable"}
  ]
}
```

A failed project contributes no runs; other projects remain readable. The response
is HTTP 200 even when all projects fail, so clients should always inspect `errors`.
An empty registry returns `{"runs": [], "errors": []}`. Project-specific run listings
still return a bare array. Registrations retain their canonical root: if a parent
directory is later redirected by a symlink, the project becomes unavailable.
Availability is a filesystem observation, not a guarantee that a subsequent read
will succeed; read failures are reported separately.

Errors on individual requests use `{"detail": "..."}`: HTTP 400 for invalid
registration paths or artifact option combinations, 404 for unknown project IDs or
missing work-item/run/loop directories, and 409 for duplicate registrations or
unavailable/unreadable project storage. Request validation errors use HTTP 422 with
FastAPI's structured `detail` array, including unknown artifact kinds and invalid
byte-window bounds. Missing or damaged artifact files themselves remain HTTP 200
with an explicit artifact `state`. OpenAPI lists artifact kinds, states, and error
responses; artifact kinds are specific to run or loop routes.

The API reads run data, maintains its project registry, and can write a generated
`work_items` TOML file into a registered project (never anywhere else). It does not start
or cancel runs. Keep it bound to localhost unless you add authentication: reports
may contain saved prompts, logs, and patches from the registered folders, and the
work-item endpoint will write files into those folders on request.

### Development checks

Run the full suite with the API extra installed before merging reporting changes:

```bash
uv sync --locked --extra api
uv run --extra api python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

The `Checks` workflow runs API tests, CLI tests without API dependencies, example
tests, lint, and formatting on pull requests. Configure `API tests`,
`CLI without API dependencies`, and `Lint and formatting` as required status checks
in the repository's branch protection settings. The API job verifies its dependencies
before discovery so missing dependencies cannot silently skip HTTP coverage.
Local CLI-only installations can still run the base suite with HTTP tests skipped.

### Docker Compose

```bash
SCISSORHANDS_PROJECTS_ROOT=/absolute/path/to/projects docker compose up --build
```

Compose starts the API on `127.0.0.1:8000`, mounts the host project directory
read-only at `/projects`, and persists the SQLite database in the `registry_data`
volume. SQLite is embedded in the API process, so there is no separate database
service. Register a container-visible path such as `/projects/my-project` through
`POST /api/projects`. If the projects live in unrelated host directories, add more
read-only bind mounts to a local Compose override file and register each mounted
path. The default project mount is the current repository when
`SCISSORHANDS_PROJECTS_ROOT` is unset. The registry volume survives container
restarts and rebuilds; project run artifacts always stay on the host mounts.

