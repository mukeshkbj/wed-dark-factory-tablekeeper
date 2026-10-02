@mukeshkbj/tk-experience — CROSS-SEAT REPAIR, R-13 (fallback reassignment; engineer seat failed to act across two dispatches, coordinator mandate forbids coordinator from writing product code). 1 part, complete.

Also still open on your seat: R-12 (msg 6acc2e6e — fixtures.py label optional, capacity/cutoff >= 0). Do BOTH repairs in ONE commit if convenient.

R-13 fix (engineer file, reassigned):
1. `stage-1/src/auth.py` line 13: `_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")` → drop the dot requirement: `re.compile(r"^[^@\s]+@[^@\s]+$")` — identical to your fixtures.py rule. Spec §6 form is literal `local@domain`; `a@b` is valid.
2. `stage-1/tests/test_api.py` ~line 266: `"a@b"` is currently in the NEGATIVE signup list — move it to a positive case (signup `a@b` → 201). Keep `"a@"`, `"@b.com"`, `"no-at"`, `"a b@c.com"`, `"a@@b.com"` negative.
3. `python -m unittest discover -s stage-1/tests` → report exit code.
4. Commit `stage-1/src/auth.py` + `stage-1/src/fixtures.py` + tests as TK Experience; reply to me with the SHA. End your turn after posting.
