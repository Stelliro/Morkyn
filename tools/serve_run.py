"""Serve a finished harness run's save on a port for viewing: python serve_finished.py <repo> <run dir> <port>."""
import os, sys, runpy
repo, run, port = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, repo); sys.path.insert(0, os.path.join(repo, "tools"))
from playtest_setup_presets import isolated_data_env
os.environ.update(isolated_data_env(os.path.join(run, "data")))
os.environ["AI_RPG_MODEL_PROVIDER"] = "offline"
os.chdir(repo)
sys.argv = ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port]
runpy.run_module("uvicorn", run_name="__main__")
