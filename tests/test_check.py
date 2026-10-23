import unittest

from scripts.check import file_errors


class SourceChecks(unittest.TestCase):
    def test_tracked_ignored_runtime_file_is_rejected(self):
        self.assertTrue(file_errors("skills/example/.env.local", b"example"))
        self.assertTrue(file_errors("docs/auth.json", b"{}"))
        self.assertTrue(file_errors("runtime.json", b"{}"))

    def test_parse_failure_does_not_echo_data(self):
        result = file_errors("templates/test.json", b'{"private-value": invalid}')
        self.assertTrue(result)
        self.assertNotIn("private-value", " ".join(result))

    def test_secret_detection_without_real_secret(self):
        simulated = ("gh" + "p_" + "a" * 40).encode()
        self.assertTrue(file_errors("docs/example.md", simulated))
        self.assertNotIn(simulated.decode(), str(file_errors("docs/example.md", simulated)))

    def test_native_instruction_filename(self):
        self.assertTrue(file_errors("templates/project/CLAUDE.md", b"example"))
        self.assertEqual([], file_errors("templates/project/AGENTS.md", b"# Project"))

    def test_known_source_is_allowed(self):
        self.assertEqual([], file_errors("scripts/tool.py", b"print('hello')\n"))


if __name__ == "__main__":
    unittest.main()
