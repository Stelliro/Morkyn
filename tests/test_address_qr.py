"""The phone address comes as a QR code, so nobody has to type "http://" (#149).

Stell, 2026-10-23: the phone said "This site can't provide a secure connection";
"http" had been read as "https". The launcher prints the code in the terminal
and the page shows it under the address.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import segno  # noqa: E402

from app import launcher  # noqa: E402

LAN = {"reach": "lan", "lan_url": "http://192.168.0.152:8000", "vpn_url": "", "local_url": "http://127.0.0.1:8000"}


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


class TheCode(unittest.TestCase):
    def test_lan_reach_draws_the_lan_address(self):
        svg = launcher.address_qr_svg(LAN)
        self.assertTrue(svg and svg.lstrip().startswith(b"<svg"))
        expected = io.BytesIO()
        segno.make(LAN["lan_url"], error="m").save(expected, kind="svg", scale=5, border=3, dark="#0b0711", light="#ece6fb", xmldecl=False)
        self.assertEqual(svg, expected.getvalue())

    def test_vpn_reach_draws_the_vpn_address(self):
        plan = dict(LAN, reach="vpn", vpn_url="http://100.64.0.7:8000")
        self.assertEqual(launcher.shared_address(plan), "http://100.64.0.7:8000")

    def test_this_pc_only_has_no_code(self):
        self.assertIsNone(launcher.address_qr_svg(dict(LAN, reach="local")))
        self.assertIsNone(launcher.address_qr_svg({}))

    def test_the_terminal_gets_the_code_and_a_log_file_does_not(self):
        tty, pipe = _Tty(), io.StringIO()
        saved = sys.stdout
        try:
            sys.stdout = tty
            launcher.print_address_qr(LAN["lan_url"])
            sys.stdout = pipe
            launcher.print_address_qr(LAN["lan_url"])
        finally:
            sys.stdout = saved
        self.assertIn("Scan to open it on a phone", tty.getvalue())
        self.assertIn("█", tty.getvalue())
        self.assertEqual(pipe.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
