$verification_feedback
## Scissorhands iteration contract

This is iteration $iteration of $max_iterations. Work on the one objective selected in
`$plan_path`: inspect the repository, make the focused changes, and run relevant verification.
Do not merely describe what could be done or start another implementation step this iteration.

Use `$progress_path` as durable memory between fresh agent sessions. Read it if it
exists. At the end of this iteration, update it with completed work, verification results,
important decisions, and the clearest next step.

Also write `$status_path` with your honest assessment of every definition of done
item and acceptance criterion, keyed by the IDs shown above. Include every ID, for example:

```json
{
  "DoD-1": {"met": true, "evidence": "What you ran or checked and what you saw."},
  "AC-1": {"met": false, "evidence": "What is still missing."}
}
```

The harness only accepts the completion marker when this file was updated during the current
iteration and every listed item has `"met": true` with non-empty `"evidence"`.

$final_iteration_note
Only when every definition of done item and every acceptance criterion is genuinely satisfied,
and every step in the fresh implementation plan is completed, include this exact marker on a
line by itself in your final response:

$marker

Do not emit the marker when work remains or verification is failing. When the work item lists
verification commands, the harness runs them after every iteration and ignores the marker unless
they all pass.
