"""Playtest #65: the model size guess reads the file name, not the folders above it.

A GGUF under a session folder with '430b' in its name was sized as a 430B
model, and the settings label printed the whole path.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.model_limits import model_facts, model_file_name  # noqa: E402


class ModelNameIsTheFile(unittest.TestCase):
    def test_file_name_from_paths_and_repo_ids(self):
        self.assertEqual(model_file_name(r"C:\Temp\claude\d66f-430b\no_such_model.gguf"), "no_such_model")
        self.assertEqual(model_file_name("C:/Models/Qwen3-8B-Q4_K_M.GGUF"), "Qwen3-8B-Q4_K_M")
        self.assertEqual(model_file_name("Qwen/Qwen3-8B"), "Qwen3-8B")
        self.assertEqual(model_file_name("qwen3:8b"), "qwen3:8b")

    def test_a_folder_name_does_not_size_a_missing_model(self):
        facts = model_facts({"provider": "mle", "mle_model": r"C:\Temp\claude\d66f-430b\no_such_model.gguf"})
        self.assertIsNone(facts["params_b"])
        self.assertEqual(facts["label"], "no_such_model")

    def test_the_file_name_still_sizes_it(self):
        facts = model_facts({"provider": "mle", "mle_model": r"C:\Temp\run-430b\Qwen3-8B-Q4_K_M.gguf"})
        self.assertEqual(facts["params_b"], 8.0)


if __name__ == "__main__":
    unittest.main()
