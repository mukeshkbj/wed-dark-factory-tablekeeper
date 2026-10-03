# Submission package — WeAreDevelopers × BAND Dark Factory (Tablekeeper)

Entry for lablab.ai. This file indexes the produced artifacts and the
remaining blockers. **Not submitted** — final Submit is an explicit
operator decision.

- Repository: https://github.com/mukeshkbj/wed-dark-factory-tablekeeper
- Form copy / event requirements / blockers: `docs/SUBMISSION-DRAFT.md`
- Factory report (incl. operator-intervention disclosure): `FACTORY.md`
- Demo walkthrough: `docs/DEMO-RUNBOOK.md`

## Produced assets

| Asset | Path | Status |
|---|---|---|
| Cover image | `submission/cover.png` | 1600×900 PNG, product design tokens |
| Slide deck | `submission/deck.pdf` | 7 pages, 16:9, all claims evidence-tied |
| Factory diagram | `submission/factory-diagram.{png,svg,gif}` | hand-drawn seat-loop, checks pass |
| Public demo recipe | `submission/deploy/` | validated on loopback; needs authorized host |
| Sources | `submission/src/` | cover.html, deck.html, diagram spec |

## Verified product state

- Four frozen stages; official final isolated sweep reaches stage 4:
  120/120, 25/25, 7/7, 6/6 — reproduced from a fresh public clone.
- Independent stage-4 verifier: 862/862 API, 62/62 upgrade, 82/82 UI,
  5/5 hardened. Evidence under `evidence/` and `verification/`.

## Deploy a public demo (when a host is authorized)

```sh
cd submission/deploy
DEMO_PORT=<free port> docker compose up --build -d
```

The stack keeps the app internal, seeds the synthetic fixture once, and
publishes only an nginx proxy that returns 404 for every `/_test*` path.
Verify as an unauthenticated judge (checklist in `submission/deploy/README.md`)
before claiming a URL.

## Blockers (operator-only)

1. `room.json` — export the real BAND room (`9bf93138-…`) via room menu →
   Download → Download full session; review for private values; place at
   repo root; rerun `harness check`. Do not fabricate.
2. Video — must show the actual BAND Desktop room plus walkthrough
   (room-less video disqualifies). Storyboard: `docs/SUBMISSION-DRAFT.md`.
3. Public URL — deploy the recipe above on an authorized host and test it.
4. Form — title/short/long descriptions and tags drafted in
   `docs/SUBMISSION-DRAFT.md`; select the form's exact tags at upload.
