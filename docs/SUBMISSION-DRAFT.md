# lablab.ai submission draft — WeAreDevelopers × BAND Dark Factory

**Status:** draft only; do not submit until the blockers below are cleared and every claim has been checked against the final public artifacts.

## Event details checked

- Event: [WeAreDevelopers × BAND present: Dark Factory](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)
- Track: Tablekeeper.
- Published event close: October 5, 2026, 23:59 PDT.
- The event page requires a public GitHub repository, one completed folder per stage, the BAND room export, and a video that records the actual BAND Desktop room plus a project walkthrough. The event page explicitly says a video without the room recording disqualifies an entry.
- The event page lists project title, short and long descriptions, technology/category tags, cover image, video presentation, slide presentation, and public GitHub repository. The general [lablab submission guide](https://lablab.ai/delivering-your-hackathon-solution) says title ≤50 characters, short description ≤255 characters, long description ≥100 words, PNG/JPG cover (16:9 recommended), MP4 video under 5 minutes, and PDF slides. Verify current limits, size caps, accepted links, and tag options in the live form before upload.
- The event rubric weights Factory 50%, App 25%, Agent Teamwork 25%. The published event criteria emphasize generic mandates, reusable factory setup, spec-conforming progress through stages, room traceability, and autonomy.

## Form copy

### Project title

**Tablekeeper: A Verified Reservation Factory**

### Short description (draft)

Four BAND seats built a four-stage, spec-derived Tablekeeper reservation service with timezone-aware bookings, recurring visits, and atomic seating recovery; the final isolated stage chain passes from a fresh clone.

### Long description (draft; review before use)

Tablekeeper pairs a restaurant reservation service with the four-seat BAND factory that built it. The Coordinator, Engineer, Experience, and Verifier seats worked from a single dispatch to produce four independently buildable stages. The service covers table search and reservations, paired tables, timezone-aware booking, idempotent retries, effective-dated policies, recurring visits, and manager previews for seating changes after a table closure. Applying a plan atomically records the closure and moves affected reservations while preserving guest times and accepted terms. An independent verifier derived checks from the official specifications; the final isolated harness passed the full stage chain, including 120, 25, 7, and 6 published checks for stages one through four, and that result reproduced from a fresh public GitHub clone. The repository includes the code, generic mandates, handoffs, repair history, gate evidence, and a synthetic demo runbook. The run did require operator help restoring runtime access, restarting stalled seats, and recording gate evidence after room-cap failures, so it was not a zero-human-intervention run. Per-seat cost and stage wall-time are unknown, and hidden-test success is not claimed. The cover image and slide deck are prepared; a safe public demo recipe is included in the repository but not yet deployed.

### Technology/category tags (select only if present)

- Technologies actually used: BAND Desktop, Devin ACP, Python, Docker.
- Use the form's exact matching technology/category tags. Do not claim Featherless usage; this project did not use it. Do not select a category merely because it sounds close if the form options do not match.

## Video outline (operator must record)

Target an edited walkthrough under five minutes if the live upload form confirms the published general limit. The actual BAND Desktop room recording is mandatory; capture it as part of the video, not as a substitute image. Avoid showing or speaking any live credentials, access tokens, or private account details. Do not imply the factory ran without operator intervention.

1. **Room and task (0:00–0:35):** record the real BAND Desktop room; show the four seats and original all-stage dispatch, then the handoff/review pattern. Do not edit room history or fabricate messages.
2. **Product problem (0:35–0:55):** explain the guest promise: a table closure must not silently change a booking time or accepted terms.
3. **Local demo (0:55–2:20):** follow `docs/DEMO-RUNBOOK.md`: seed only synthetic data on loopback, preview the closure plan as the seeded manager, apply it, then verify availability and reservation lookup as the guest.
4. **Evidence (2:20–3:15):** show the committed stage freeze records and final isolated harness report. State the counts as checks executed, not unique requirements.
5. **Limits and process honesty (3:15–3:45):** disclose operator recovery actions, unknown costs/time, fixed synthetic demo dates, no public deployment, and that published checks do not guarantee hidden-test success.

Before recording, review the room view and desktop for secrets. The raw room export is unredacted and must be reviewed separately before it is committed.

## Produced assets

- **Cover image:** `submission/cover.png` — 1600×900 PNG, product visual language (warm cream, forest green, ink), Tablekeeper wordmark, tagline, seating-grid motif drawn from the real demo fixture. Source: `submission/src/cover.html`.
- **Slide deck:** `submission/deck.pdf` — 7 pages, 16:9. Title → the guest-promise problem → product flow → the four-seat factory (hand-drawn diagram) → verification evidence → proven-vs-not-claimed → repo pointers. All metrics labeled as checks executed. Source: `submission/src/deck.html`.
- **Factory diagram:** `submission/factory-diagram.png` / `.svg` / `.gif` — hand-drawn paper-style loop: spec → Coordinator → Engineer + Experience → Verifier → gate → Freeze, with dashed reject-repair and next-stage channels. Source spec: `submission/src/factory-diagram.spec.json`.
- **Public demo recipe:** `submission/deploy/` — compose stack **and** all-in-one `single/` image, both validated on loopback. **Deployed:** `https://tablekeeper-demo-52fh.onrender.com` via `render.yaml` (Render free tier); verified publicly — health/UI 200, all `/_test/*` 404, seeded login works.

## Slide deck outline (as produced in `submission/deck.pdf`)

1. **Title and promise:** Tablekeeper; “keep the guest's time and accepted terms when a table closes.”
2. **The problem:** a closure must not silently move a booking — time and accepted terms are the promise.
3. **The product flow:** search/booking → closure preview → atomic apply → existing availability and lookup views reflect the reassignment.
4. **The factory:** four seats and their generic ownership; one dispatch → committed handoffs → independent spec-derived verification, with the reject loop and the operator-intervention caveat.
5. **Verification:** stage chain 120/120, 25/25, 7/7, 6/6; independent stage-4 suite 862/862, upgrade 62/62, inherited UI 82/82, hardened 5/5; fresh-clone reproduction. Labeled as check counts.
6. **Proven vs not claimed:** frozen revisions and clean-clone result; synthetic data; no users/revenue/production deployment claims; unknown seat costs and stage durations; human recovery actions.
7. **Try it:** repository, runbook, license, factory artifacts.

## Cover direction (as produced in `submission/cover.png`)

The product's warm cream, forest-green, and ink visual language. A 16:9 composition pairs the Tablekeeper wordmark with a minimal seating-grid motif and the line “A reservation factory that keeps the guest promise.” No customer logos, fabricated metrics, or unsourced market claims. Confirm PNG/JPG acceptance and size limits in the live upload form.

## Submission blockers

- **BAND room:** `room.json` is missing. In Band Desktop, open scored room `9bf93138-25b0-431d-aa62-4a3dbca30155`; use the room menu → Download → Download full session. Save the original file at the repo root as `room.json`, inspect it for credentials/private values, then run the official `harness check`. Never synthesize a replacement.
- **Mandatory video:** no room-inclusive video recording is present. The operator must record the actual room and product walkthrough.
- **Slides and cover:** produced — `submission/deck.pdf` (7 pages) and `submission/cover.png` (1600×900). Review both against the live form's size/format rules before upload.
- **Working online prototype: DEPLOYED** — `https://tablekeeper-demo-52fh.onrender.com` (Render free tier, `render.yaml` blueprint, all-in-one image). Verified as an unauthenticated judge on 2026-10-03: `/health` 200, UI 200, `/_test/reset|export|import` all 404, seeded demo login works. Form fields: **Demo Application Platform → `Other`**, Application URL → the onrender URL. Caveats to keep honest: free tier spins down after ~15 min idle (~1 min cold start, reseeds fixture each time); judge-created bookings vanish on spin-down.
- **Autonomy rubric risk:** runtime recovery and some gate-recording actions required operator intervention. This is disclosed in `FACTORY.md`; do not describe the submitted run as fully hands-off.

Repository: https://github.com/mukeshkbj/wed-dark-factory-tablekeeper

Final Submit action remains an explicit operator decision; this file is preparation, not submission.
