"""Compose work-item prompts and iteration guidance."""

from scissorhands.core.work_items import WorkItem
from scissorhands.prompting.contract import default_contract, render_contract
from scissorhands.prompting.work_items import render_work_item


def compose_prompt(
    work_item: WorkItem,
    iteration: int,
    marker: str,
    *,
    max_iterations: int,
    verification_feedback: str | None = None,
    contract: str | None = None,
    progress_path: str = ".scissorhands/progress.md",
    status_path: str = ".scissorhands/status.json",
) -> str:
    """Add the repeatable loop contract to the user's task."""
    final_note = ""
    if iteration == max_iterations:
        final_note = f"""
This is the final iteration. Do not start large new pieces of work. Finish or safely wrap up what
is in progress, leave the repository in a working state, and make
`{progress_path}` a clear handoff for whoever picks this up next.
"""
    feedback = ""
    if verification_feedback:
        feedback = f"""
## Verification feedback

The harness ran the verification commands after the previous iteration and they failed. Fix these
failures before starting anything else:

{verification_feedback}
"""
    rendered = render_contract(
        contract if contract is not None else default_contract(),
        iteration=iteration,
        max_iterations=max_iterations,
        marker=marker,
        final_iteration_note=final_note,
        verification_feedback=feedback,
        progress_path=progress_path,
        status_path=status_path,
    )
    return f"{render_work_item(work_item)}\n{rendered}"
