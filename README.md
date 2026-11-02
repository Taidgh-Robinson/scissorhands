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
```

Each iteration starts a new agent session. Runtime state is written beneath `.scissorhands/`:

- `.scissorhands/progress.md` is the agents' durable handoff note.
- `.scissorhands/status.json` is the agent's met/unmet assessment of each checklist item, with evidence.
  The harness prints it as a checklist after every iteration. A completion marker is accepted only
  when the file was updated during that iteration and every definition-of-done and acceptance-
  criteria entry is present with `met` set to `true` and non-empty evidence.
- `.scissorhands/runs/<run-id>/iteration-N.log` contains the combined command output.
- Codex also writes its final response to `iteration-N.final.txt`.
- `.scissorhands/runs/<run-id>/iteration-N.json` is the harness-owned receipt for that iteration. It
  preserves the progress text and criteria snapshot, whether each was updated, verification
  results, the completion decision, and the iteration outcome.

The loop stops when the agent puts `<promise>COMPLETE</promise>` on a line by itself and submits a
fresh, fully-met criteria status, when an agent command fails, or when the iteration limit is
reached. Reaching the limit returns exit code 2; an agent failure returns 1.

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

Describe the work in `WORK_ITEM.toml` using the required `title`, `description`,
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

Unknown placeholders are rejected at startup. Write a literal `$` as `$$`.

Start with two or three iterations and inspect `.scissorhands/progress.md`, the run logs, and the Git diff.
Small limits make it much easier to learn how prompt wording affects convergence.

## Project layout

```text
src/scissorhands/
  cli.py              Command-line entry point
  agents.py           Agent-specific commands and output handling
  core/               Loop orchestration, execution, decisions, receipts, and reporting
  prompting/          Prompt composition, contract rendering, and default template
tests/                Unit tests
docs/planning/        Roadmaps and design drafts
WORK_ITEM.toml        Editable work item used by the default CLI command
```

Planning documents are design drafts and may describe earlier names or proposed features.

