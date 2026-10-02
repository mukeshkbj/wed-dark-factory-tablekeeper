#!/usr/bin/env python3
"""tk-verifier stage-3 UI checks.

Stage-3 adds NO new screens or testids (spec: "No new screens are required
for explanations or history"; ruling R3-15). The stage-2 UI suite is the
complete browser contract — this runner delegates to it verbatim against the
stage-3 service, satisfying matrix row D-5.

Run with the harness venv (playwright installed):
  D:/tk-official/.venv/Scripts/python.exe ui_checks.py \
      --base-url http://localhost:8096 --shots <dir>

Passes all arguments through to verification/stage-2/ui_checks.py.
"""
import importlib.util, pathlib, sys

_HERE = pathlib.Path(__file__).resolve().parent

def _load_ui2():
    p = _HERE.parent / "stage-2" / "ui_checks.py"
    spec = importlib.util.spec_from_file_location("tk_s2_ui", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

if __name__ == "__main__":
    _load_ui2().main()   # consumes sys.argv (--base-url, --shots)
