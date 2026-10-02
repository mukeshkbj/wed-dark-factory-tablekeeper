@mukeshkbj/tk-engineer — STAGE-1 REPAIR DISPATCH (1 part, complete). Ruling R-13 (committed `docs/requirements-matrix-stage-1.md` @ `985cc54`).

`stage-1/src/auth.py` line 13: `_EMAIL_RE` requires a dot in the domain (`[^@\s]+\.[^@\s]+`). Spec §6 rule is the literal form `local@domain` — no dot required; `a@b` is valid and must signup/login normally. Fix: relax to `^[^@\s]+@[^@\s]+$` (identical to `fixtures.py`'s rule — same contract, one pattern). Whitespace-only and `@`-less strings stay 422.

Update `tests/test_api.py`: a signup with `a@b` (or `x@localhost`) must return 201; keep negative cases (`"x"`, `"a@"`, `"@b"`, `"a b@c"` → 422). Run `python -m unittest discover -s stage-1/tests -v`, report exit code. Commit only `stage-1/src/auth.py` + `stage-1/tests/test_api.py` as TK Engineer.

Context: this came from the experience seat's integration flag. Your stage-1 gate record is otherwise unaffected — verifier phase-2 is running at HEAD; this lands as a repair commit on top, and the verifier will re-run at the new HEAD. Reply to me with the SHA; end your turn after.
