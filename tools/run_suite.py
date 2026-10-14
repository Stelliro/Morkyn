"""Run the full test suite with its temp dirs in one folder that is deleted afterwards.

Many test modules make an isolated data dir with tempfile.mkdtemp and never remove it. In
%TEMP% on C: those piled up to 14,000+ folders and about 20 GB and filled the disk
(2026-10-14). This runner points TEMP/TMP at a folder beside the repo's drive root (outside the
repo: some tests assert their temp dir is not inside it), runs the suite there and deletes the
folder when it ends.

    .venv\\Scripts\\python.exe tools\\run_suite.py [--out FILE] [--tmp DIR]

Prints the last lines of the run and every FAIL/ERROR line; --out keeps the full output.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="", help="file for the full suite output")
    parser.add_argument("--tmp", default=str(Path(ROOT.anchor) / "morkyn-suite-tmp"),
                        help="temp folder for the run (outside the repo; deleted after)")
    args = parser.parse_args()
    tmp = Path(args.tmp).resolve()
    if ROOT in tmp.parents or tmp == ROOT:
        print("--tmp must be outside the repo", file=sys.stderr)
        return 2
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEMP=str(tmp), TMP=str(tmp), TMPDIR=str(tmp))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "."],
            cwd=str(ROOT / "tests"), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    text = proc.stdout or ""
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    for line in sorted(l for l in text.splitlines() if l.startswith(("FAIL:", "ERROR:"))):
        print(line)
    print("\n".join(text.strip().splitlines()[-3:]))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
