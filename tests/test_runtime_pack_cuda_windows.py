"""The Windows CUDA pack carries the CUDA runtime and cuBLAS and loads them first.

A player's 0.11.1 exe (2026-10-28) could not load llama.dll on a PC with the
NVIDIA driver and no CUDA Toolkit: ggml-cuda.dll links cudart64_12.dll and
cublas64_12.dll, the pack did not carry them, and llama_cpp's loader looks a
dependency up by PATH only.
"""

import ctypes
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import runtime_packs

# packaging/ is not a package (and the name is pip's "packaging"): load by path.
_SPEC = importlib.util.spec_from_file_location(
    "morkyn_build_packs", Path(__file__).resolve().parents[1] / "packaging" / "build_packs.py"
)
build_packs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_packs)


class WindowsCudaPreloadTest(unittest.TestCase):
    def _site(self, root: Path) -> Path:
        site = root / "site"
        for rel in runtime_packs._CUDA_DLLS:
            lib = site / "nvidia" / rel
            lib.parent.mkdir(parents=True, exist_ok=True)
            lib.write_bytes(b"")
        return site

    def test_dlls_load_by_full_path_in_order_and_their_folders_join_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = self._site(Path(tmp))
            loaded = []
            with mock.patch.object(runtime_packs.sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"PATH": "C:\\Windows"}), \
                    mock.patch.object(ctypes, "WinDLL", side_effect=loaded.append, create=True):
                runtime_packs._preload_cuda(site)
                path = os.environ["PATH"].split(os.pathsep)
            self.assertEqual(
                [Path(p).name for p in loaded], ["cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll"]
            )
            self.assertIn(str(site / "nvidia" / "cuda_runtime" / "bin"), path)
            self.assertIn(str(site / "nvidia" / "cublas" / "bin"), path)

    def test_a_pack_without_the_runtime_loads_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = []
            with mock.patch.object(runtime_packs.sys, "platform", "win32"), \
                    mock.patch.object(ctypes, "WinDLL", side_effect=loaded.append, create=True):
                runtime_packs._preload_cuda(Path(tmp))
            self.assertEqual(loaded, [])

    def test_the_windows_cuda_pack_installs_the_runtime_and_cublas(self):
        calls = []

        def fake_run(cmd, **_):
            calls.append(cmd)
            raise SystemExit("stop after pip")

        with mock.patch.object(build_packs, "os_tag", return_value="windows"), \
                mock.patch.object(build_packs.subprocess, "run", side_effect=fake_run), \
                tempfile.TemporaryDirectory() as out, \
                mock.patch.object(build_packs.tempfile, "mkdtemp", return_value=out):
            with self.assertRaises(SystemExit):
                build_packs.build("cuda", Path(out))
        self.assertTrue(any("nvidia-cuda-runtime-cu12" in a for a in calls[0]))
        self.assertTrue(any("nvidia-cublas-cu12" in a for a in calls[0]))


if __name__ == "__main__":
    unittest.main()
