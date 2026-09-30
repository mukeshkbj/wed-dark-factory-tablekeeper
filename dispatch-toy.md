<!--
TOY REHEARSAL dispatch — practice run, NOT the submission.
Purpose: prove seat routing, handoffs, git identity, harness runs and cost,
on the unscored practice track, before the real dispatch.
Create a practice result repo first:
  mkdir D:\band-work\toy-result && git -C D:\band-work\toy-result init -b main
Paste in the rehearsal room mentioning @mukeshkbj/tk-coordinator.
-->

@mukeshkbj/tk-coordinator

Rehearsal dispatch for the practice track `toy`. Build the shared-counter
service sequentially through stages 1–4, strictly to the official toy
specifications. Full authority to coordinate the configured seats, make
implementation decisions, run checks and repair failures. No human input
between this dispatch and your final report; record blockers instead of
waiting.

Result repository (shared by all seats): D:\band-work\toy-result
Official kickoff checkout: D:\tk-official (commit
803560d2a678ace1414465c098eb0ab5380ffade)
Specifications: D:\tk-official\toy\spec\stage-1.md through stage-4.md
Harness: from D:\tk-official run
  D:\tk-official\.venv\Scripts\python.exe -m harness run --track toy \
    --repo "D:\band-work\toy-result" --stage <N> --out <NEW abs out dir>
Existing out dirs are refused; add --mode isolated for the final pass.
Note: some toy runs print one expected `fail` line (next-stage overshoot
probe) — that line is intended.

Seats (already in this room): @mukeshkbj/tk-coordinator (plan, gate, docs),
@mukeshkbj/tk-engineer (implementation), @mukeshkbj/tk-experience (UI stage),
@mukeshkbj/tk-verifier (independent checks, harness, gate verdicts).
Standing instructions: each seat's mandate lives at
D:\WED Dark factory\mandates\tk-<seat>.md — before anything else, read your
own mandate file; it governs how you work for the entire run.
Handoffs must mention the target seat by literal @handle and paste the
complete task plus the complete applicable spec text. Agents see only
messages that mention them. Commit with per-seat git identity, own files
only, no amend/squash/rebase. Each stage folder gets Dockerfile, RUN.md,
source, tests; accepted folder is copied forward to the next stage, never
backward.

This run is practice: exercise the full loop — plan, implement, independent
verify, gate verdict, freeze, copy forward — and measure token cost and
duration per stage so we can budget the real run. Report per-stage harness
output and the final `claimed stage` lines in your closing message.
