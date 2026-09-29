import unittest

from app.debug_commands import HELP_TEXT, handle_command, is_command


class DebugCommandTests(unittest.TestCase):
    def test_help_lists_linking_and_commands(self):
        self.assertTrue(is_command("  /help"))
        self.assertFalse(is_command("what will you do?"))
        result = handle_command("/help")
        self.assertTrue(result["ok"])
        self.assertFalse(result["advanced_turn"])
        self.assertIn("@C character", result["answer"])
        self.assertIn("/item", result["answer"])
        self.assertIn("/teleport", result["answer"])
        self.assertIn("/godmode", result["answer"])
        self.assertEqual(result["answer"], HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
