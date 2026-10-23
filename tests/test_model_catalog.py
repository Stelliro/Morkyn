"""One-click local models download whole, resume, and never leave a bad file as a model.

Stell (2026-10-23): "is it possible to add a one click install to a good 8b
model?" app/model_catalog.py downloads a catalog GGUF into MLE's folder. A
5 GB download gets cut; it must resume from its .part file, start over when the
server ignores the range, and drop a file whose SHA-256 does not match instead
of renaming it into place where MLE would load it.
"""
from __future__ import annotations

import hashlib
import http.server
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

os.environ.update(isolated_data_env(tempfile.mkdtemp(prefix="morkyn-model-catalog-")))

from app import model_catalog  # noqa: E402

PAYLOAD = bytes(range(256)) * 9000  # about 2.3 MB: several chunks


class _Handler(http.server.BaseHTTPRequestHandler):
    honour_range = True

    def do_GET(self):  # noqa: N802 - http.server's name
        start = 0
        header = self.headers.get("Range")
        if header and self.honour_range:
            start = int(header.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        body = PAYLOAD[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ModelCatalogDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/model.gguf"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="morkyn-mle-models-"))
        self._dir = mock.patch.object(model_catalog, "models_dir", lambda: self.folder)
        self._dir.start()
        self.item = {"id": "test", "file": "test.gguf", "size": len(PAYLOAD), "sha256": hashlib.sha256(PAYLOAD).hexdigest()}
        _Handler.honour_range = True

    def tearDown(self):
        self._dir.stop()

    def test_a_cut_download_resumes_and_lands_whole(self):
        (self.folder / "test.gguf.part").write_bytes(PAYLOAD[:700_000])
        target = model_catalog.download(self.item, self.url)
        self.assertEqual(target.read_bytes(), PAYLOAD)
        self.assertFalse((self.folder / "test.gguf.part").exists())

    def test_a_server_that_ignores_the_range_starts_over(self):
        _Handler.honour_range = False
        (self.folder / "test.gguf.part").write_bytes(PAYLOAD[:700_000])
        self.assertEqual(model_catalog.download(self.item, self.url).read_bytes(), PAYLOAD)

    def test_a_wrong_checksum_is_removed_not_renamed_into_a_model(self):
        bad = {**self.item, "sha256": "0" * 64}
        with self.assertRaises(ValueError):
            model_catalog.download(bad, self.url)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_every_catalog_entry_is_complete(self):
        for item in model_catalog.CATALOG:
            self.assertTrue(item["file"].endswith(".gguf"), item["id"])
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(item["size"], 1 << 30)
            self.assertIn("/", item["repo"])
        self.assertEqual(sum(1 for item in model_catalog.CATALOG if item.get("recommended")), 1)


if __name__ == "__main__":
    unittest.main()
