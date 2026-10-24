"""Run tools/api_bridge_playtest.py with the installed engine packs on the path (llama_cpp from the CUDA pack).

The Linux .venv has no llama_cpp; the packaged game's pack is built for the same Python.
Usage: python run_harness.py <repo root> <harness args...>
"""
import os
import runpy
import sys

repo = sys.argv[1]
sys.argv = [os.path.join(repo, "tools", "api_bridge_playtest.py"), *sys.argv[2:]]
sys.path.insert(0, repo)
sys.path.insert(0, os.path.join(repo, "tools"))
os.environ.setdefault("MORKYN_RUNTIME_DIR", os.path.expanduser("~/.local/share/morkyn/runtime"))
from app import runtime_packs  # noqa: E402

print("packs on the path:", runtime_packs.activate(), flush=True)
runpy.run_path(sys.argv[0], run_name="__main__")
