# TK Verifier — stage-2 phase-1/2 report @ b424a8b

Seat: `mukeshkbj/tk-verifier` (Devin ACP, `--agent-type review`).
Model reported by this session: **SWE-2 High** (mandate requested `swe`).
Checked revision: `b424a8be649c8b5194ab2b10ca2b3889ced3530c` (HEAD,
engineer `14936ad` + experience `b424a8b` on the frozen stage-1 scaffold).

## Verdict: **ACCEPTED at 5be5343** (fix-verified; see Follow-up below)

*Original verdict at b424a8b was REJECTED on blocker S2-1; the repair commit
5be5343 clears it — all gates green.*

## Verdict (at b424a8b, superseded): REJECTED — one blocking UI defect (finding S2-1)

The API/domain surface is clean on every axis I can reach. The browser
grid has a DOM-ordering defect that makes EVERY successful search hang for
a client that waits on the spec-named OR-condition — the shipped official
suite times out on it 13 times.

## Results

| Suite | Command | Result |
|---|---|---|
| Own API checks (inherited + C2) | `python verification/stage-2/checks.py --base-url http://localhost:8082` | **350/350 PASS**, 0 FAIL, 0 5xx, 822.2s — `evidence/s2/checks-b424a8b.log` |
| Own UI checks (Playwright) | `D:\tk-official\.venv\Scripts\python.exe verification/stage-2/ui_checks.py --base-url http://localhost:8082` | 80/80 PASS, 70.2s — `evidence/s2/ui-b424a8b.log` |
| Own UI checks + new OR-selector guard | same, r2 | 81/82, 1 FAIL = S2-1 reproduction — `evidence/s2/ui-b424a8b-r2.log` |
| Upgrade continuity | `python verification/stage-2/upgrade_checks.py --s1-url :8093 --s2-url :8082` (stage-1 @aae0226 vs stage-2) | 19/19 PASS, 37s |
| Reference-model replay | `model.py --ops 500` seeds 7/13/42 | **3 seeds x 500 ops, 0 disagreements** — `evidence/s2/model-seed{7,13,42}.log`; an initial seed-13 divergence was a model fidelity gap (F-11), not a product defect |
| Hardened mode | `checks.py --hardened` vs `TK_HARDENED=1` instance | 5/5 PASS |
| Author unit tests | `python -m unittest discover -s tests` (stage-2) | 127/127 OK, 23.6s |
| Official harness host | `harness run --stage 2 --out evidence/harness/s2-run2` | stage 1 **pass 120/120**; stage 2 **fail 12/25**; stage-3 overshoot fail (expected) |
| Official harness isolated | same + `--mode isolated` → `s2-run4-isolated` | identical: stage-1 120/120 pass, stage-2 12/25 fail, `state: completed` |

## Finding S2-1 (BLOCKER) — hidden `no-slots` precedes `availability-grid` in DOM

- Requirement (stage-2 spec): "`no-slots` — shown instead of the grid when
  the day has no slots"; grid container `availability-grid`.
- `stage-2/ui/index.html` keeps BOTH elements permanently in the DOM,
  `no-slots` (`index.html:63`) before the `availability-grid` table
  (`index.html:70`), toggling only the `hidden` attribute. `index.js`
  `renderGrid` unhides the grid but leaves `no-slots` hidden.
- Any client waiting on `wait_for_selector("[data-testid=availability-grid],
  [data-testid=no-slots]")` (a comma/OR selector — the natural way to await
  "grid or no-slots") resolves to the FIRST match in DOM order = the hidden
  `no-slots`, and waits for ITS visibility forever. Playwright call log:
  "locator resolved to 2 elements. Proceeding with the first one:
  `<div hidden data-testid=no-slots>`" ×23 polls → 10s timeout.
- Reproduction: any successful search (`r_anker`, a day with slots) —
  official `test_ui.py::search()` helper does exactly this wait; 13 of 25
  stage-2 checks fail on it (test_sample 1, test_ui 12). My added probe
  `U-GRID-6b` fails the same way; `U-GRID-6a` (closed day) passes because
  the first match happens to be the visible element there.
- Expected: after every completed search, the first DOM-order match of the
  two testids is the visible one. DOM reorder alone cannot satisfy both
  directions — the inapplicable element must leave the DOM (or not match).
- Severity: blocker. The entire post-search flow (booking, confirmation,
  lookup hand-off) is unreachable to a client that waits this way.

## Disclosures (honesty, per mandate)

- The defect escaped my spec-derived UI suite because my probes query each
  testid individually; the OR-wait hazard only shows under a comma selector.
  Guard `U-GRID-6a/b` added after observing the official failure — it was
  the official suite, not mine, that caught it first. Flagged as F-9.
- `model.py` NOW0 is now grid-snapped; before the fix the replay would have
  been vacuous (every op off-grid). Stage-1's model.py shares the latent
  flaw — its clean result may have been start-minute luck. Flagged as F-10.
- Error precedence among simultaneously-applicable combination errors is
  unstated (F-1); the implementation picks
  shape→existence→declared-pair→party→grid→hours→capacity→occupancy,
  verified empirically and mirrored in the reference model.
- The seed-13 M-moves-62 divergence was chased to ground: the service
  correctly returns 422 party_exceeds_capacity for a party-8 booking moved
  onto a cap-4 singleton (direct probe reproduced); the reference model's
  move-target validation lacked the capacity check (F-11). Fixed in
  model.py; no product change made.
- Harness host run needed `PYTHONUTF8=1`: without it the harness crashes on
  a `charmap` encode of `\ufffd` while writing the pytest log (harness
  tooling defect on Windows consoles; run evidence in s2-run1).
- Isolated mode needed `docker pull python:3.12-slim` beforehand — the
  isolated build env has no DNS to resolve the base image.

## Follow-up: S2-1 fix verified @ 5be5343

Commit `5be5343dc361659455c7abcca4430e4be3cb1781` (tk-experience,
"stage-2 UI repair: detach inactive availability state") resolves S2-1 by
the recommended fix shape: renderGrid detaches the inapplicable element
(no-slots on open days, grid+stale cells on closed days) so the OR-selector
first DOM match is always the visible state.

Re-verification at 5be5343:

| Suite | Command | Result |
|---|---|---|
| UI checks incl. U-GRID-6a/b (rewritten to emulate the polling wait_for_selector, since an instantaneous DOM snapshot pre-response is a false negative) | `python verification/stage-2/ui_checks.py --base-url http://localhost:8095` | **82/82 PASS** — evidence/s2/ui-5be5343-r2.log |
| API checks (full re-run at fix SHA) | `python verification/stage-2/checks.py --base-url http://localhost:8095` | **350/350 PASS**, 0 FAIL, 0 5xx, 825.4s — evidence/s2/checks-5be5343.log |
| Author unit tests | `python -m unittest discover -s stage-2/tests` | 127/127 OK |
| Official harness host | `harness run --stage 2 --out s2-run5-postfix` | stage-1 **120/120**, stage-2 **25/25 pass** |
| Official harness isolated | same + `--mode isolated` -> s2-run6-isolated | stage-1 **120/120**, stage-2 **25/25 pass**, state completed |

## Held open

- stage-3 overshoot correctly fails (no stage-3 code) — expected.
- Hidden judging tests exceed the shipped sample; matrix F-1..F-8 gaps/obs
  stand. UI visual-quality clauses (W-V-*) are screenshot-captured
  (`evidence/raw/ui-s2*/`) but remain human-review observations.
- `evidence/` logs uncommitted per hygiene rules; harness report.json +
  counts.json committed per stage-1 convention.
