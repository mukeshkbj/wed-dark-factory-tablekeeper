@mukeshkbj/tk-coordinator

This is the single production dispatch for all four stages of our hackathon
entry. Build TABLEKEEPER sequentially through stages 1, 2, 3 and 4, strictly to
the official specifications. You have authority to make implementation
decisions, coordinate the configured seats, execute shell/browser/container
checks, repair failures autonomously, commit original seat history and complete
the entire sequence. No human clarification, approvals, steering, hints or
reruns. Do not stop after a plan or a single stage; continue until all stages
pass independent review or you document a concrete unrecoverable blocker.
Time and tokens are available; prefer complete correctness and polished
experience over premature delivery.

Factory: a reusable software factory that turns requirements into independently
checked releases.
Product: Tablekeeper — keep the promise, even when the floor changes. A booking
is a promise to a guest; a closed table should not ruin their evening. Build
the required clean-room reservation service and a warm, exceptionally usable
restaurant experience. The stage-4 closure-replanning capability is the
differentiator: show a manager the smallest safe seating change and apply it
atomically while preserving guests' times and accepted terms.
Team owner: Mukesh Agrawal, product direction and factory configuration. Credit
the agent seats for implementation/verification honestly. Do not invent
personal manual coding, customers, revenue, benchmarks or certifications.

Workspace/result repository (shared by all seats): D:\WED Dark factory
Official immutable kickoff checkout: D:\tk-official
Official commit: 803560d2a678ace1414465c098eb0ab5380ffade
Official participant guide: D:\tk-official\docs\participant-guide.md
Full specifications: D:\tk-official\tablekeeper\spec\stage-1.md through stage-4.md
Harness: run from D:\tk-official as
  D:\tk-official\.venv\Scripts\python.exe -m harness run --track tablekeeper \
    --repo "D:\WED Dark factory" --stage <N> --out <NEW absolute out dir>
Add `--mode isolated` for acceptance runs, `--all` for the final sweep.
Each run needs a NEW output directory (existing dirs are refused). Store public-safe evidence under result/evidence;
keep raw exports containing tokens private outside the repository.
Dependencies may be downloaded during build; runtime MUST have no outbound
network. Do not change official harness/tests or use another contestant's code.

Configured seats, and no others:
- @mukeshkbj/tk-coordinator (fb24d94e-a471-4783-94ff-1c72d37c5b67): planning,
  delegation, acceptance, factory documentation.
- @mukeshkbj/tk-engineer (a54295ec-7111-4a4e-876f-d7f925d1a0a1): domain
  implementation, atomic state, deployment.
- @mukeshkbj/tk-experience (86c01fc2-d8d3-4fc3-a79c-2bc002b38fa1): substantive
  implementation contribution in stage 1, then product UI, manager workflow
  and demo assets.
- @mukeshkbj/tk-verifier (32de7415-ebc1-41fa-8121-e7280328a21a): independent
  spec-derived tests, adversarial checks, isolated official harness, gate
  decisions.
Standing instructions: each seat's mandate lives at
D:\WED Dark factory\mandates\tk-<seat>.md — before anything else, read your
own mandate file; it governs how you work for the entire run. In your first
committed artifact, record the model id your session actually reports (e.g.
`devin` session metadata) — the mandate header's requested model is `swe`;
report the resolved value honestly so FACTORY.md cites reality.
All four are already participants in this fresh room. Use `band brief --json`
for your own identity. Exchange real handoffs via literal @handles. Each
delegated handoff MUST paste the task's relevant complete instructions and the
COMPLETE specification applicable to that stage (all inherited specs), not just
a path or message id. Number long message parts and mark the final one. Do not
assume another seat sees unaddressed room messages. All work must originate
from the BAND collaboration. Keep distribution substantive: coordinator does
not implement the service; engineer and experience own separate actual
implementation files; verifier independently authors tests and checks exact
revisions. Give explicit next-owner handoffs so the run keeps moving.

Before implementation: read the complete participant guide and all four specs
to plan extensible architecture, but implement only the current stage in its
folder. Use clause-by-clause requirement matrices with explicit tricky inputs
and transitions. Start stage-1 from no source. After accepting it, copy that
completed folder into stage-2 and extend; then stage-3; then stage-4. Never
copy later code backward. Every stage folder is complete and independently
buildable with Dockerfile, RUN.md, source, tests and offline assets — no
symlinks, submodules or nested .git. Preserve original authored commits; no
squash, amend or rebase. Stage only your owned files. Commit using per-command
identity, e.g. `git -c user.name='TK Engineer' -c user.email='tk-engineer@local'
commit ...`. Coordinate snapshot windows so the verifier checks stable
revisions.

Engineering priorities: linearizable writes under up to 50 concurrent requests;
exact idempotency scoping and original receipts; atomic batches and failure
rollback; IANA timezone/DST correctness and absolute durations; strict
specified type/error precedence; safe password hashing and owner isolation;
fully validated atomic imports preserving credentials, receipts, histories and
opaque identities; immutable historical terms; recurring identity/exceptions;
bounded deterministic globally optimal closure planning. Do not add
restrictions that contradict the contract. Design to fit a single image,
2 vCPU, 2 GiB and the specified timeouts. Arbitrary fixtures and dates must
work. Use persistence for practical operation if feasible without sacrificing
atomic import and reset.

Product priorities from stage 2: a distinctive, warm hospitality aesthetic —
deliberate typography, strong spacing, locally rendered illustration or floor
plan. No stock dashboard template, fake metrics or invented restaurant claims.
Real signup/login, clear booking search, generous responsive layout at 375px
and desktop, all required data-testid hooks, accessible labels/focus/contrast.
Distinguish unavailable, pending, confirmed refusal and uncertain outcome.
Request generations prevent stale searches; uncertain retries preserve exact
body/key until resolved. Human table names and restaurant timezone must be
clear. Manager screens for policy/series/closure-preview-and-apply in the
appropriate stages: before/after seating with preserved guest promises,
stale-plan recovery, impossible-plan explanations. Optional product extensions
are welcome only while contract correctness holds. Attractive built-in demo
seed data without external services; an easy documented synthetic demo account;
a reproducible demo scenario. Test endpoints required enabled by default in
judge images; supply an explicit hardened deployment mode disabling all /_test
controls for any publicly exposed demo, and document the difference. Do not
expose the judge image publicly.

Acceptance for EACH stage: independent verifier reads complete spec and
implementation, runs own spec-derived checks beyond published samples, executes
official harness with stage N plus inherited suites and expected next-stage
overshoot, and runs final `--mode isolated` no-outbound execution. Aim for ALL
shipped checks passing. Preserve failures and their repairs. Do not weaken
test expectations or special-case fixture data. Record commands, full
revisions, counts, duration and exact limitations. Only after verifier
acceptance freeze the folder and advance. If a later-stage check reveals a
genuine earlier-stage contract bug, coordinate a spec-grounded correction and
reverify affected folders; do not retrofit future-stage features.

At completion: run official `python -m harness run --track tablekeeper --repo
"D:\WED Dark factory" --all --mode isolated` (from D:\tk-official, venv python)
with new evidence output; independently verify a clean clone; run offline
`python -m harness check "D:\WED Dark factory" --track tablekeeper` (room.json
is exported by the operator after the run, so report that expected pending
gate honestly).
Keep only completed stage folders in the submission; preserve incomplete work
outside them if needed. Supply README.md, FACTORY.md (enough to reproduce seat
setup and run; measured time/tokens/cost with unknowns labelled; failure
recovery examples grounded in room), MIT LICENSE, reproducible local run/demo
commands, security and limitations documentation, accurate requirement
coverage and test summaries. Do not fabricate room.json; the operator exports
the real session. Experience seat produces docs/DEMO-RUNBOOK.md with exact
synthetic fixtures, routes/actions and expected visible outcomes for a
3-minute demo, plus honest feature limitations. Coordinator ends with explicit
final report to the room identifying exact accepted revisions, all checks,
stage chain and limitations. No message to the human asking what to do next.

Read the official full specs now and include their full contents in delegated
handoffs. This dispatch intentionally refers the lead to local authoritative
files as allowed by the participant guide; delegated handoffs must paste them.
No further human input will follow.
