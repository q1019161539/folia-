import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("scan_secrets", Path(__file__).with_name("scan_secrets.py"))
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class SecretScanTests(unittest.TestCase):
    def test_ai_keys_and_no_value_in_report(self):
        # Assemble synthetic tokens in memory; never commit a token-shaped literal.
        value = ("sk" + "-" + "aB2cD3eF4gH5" * 4).encode()
        result = scanner.scan_bytes(b"test\n" + value, "sample.py", "test")
        self.assertEqual(result[0]["line"], 2)
        self.assertEqual(result[0]["rule"], "ai-relay-key")
        self.assertNotIn(value.decode(), json.dumps(result))

    def test_private_key_and_cookie(self):
        value = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----\n"
        self.assertEqual(scanner.scan_bytes(value, "a", "test")[0]["rule"], "private-key")
        cookie = b"SESSDATA=" + b"a1b2c3" * 8
        self.assertEqual(scanner.scan_bytes(cookie, "a", "test")[0]["rule"], "bilibili-session")

    def test_private_paths_and_safe_examples(self):
        for name in (".env", "x/.env.production", "data/studio.db", "ops/a/backup/x.json",
                     "private.pem", "x/video.mp4", "source.bundle", "cookies.json"):
            self.assertTrue(scanner.forbidden_path(name), name)
        for name in (".env.example", "backend/publish_v2.py", "web/publish.js", "docs/STATUS.md"):
            self.assertFalse(scanner.forbidden_path(name), name)

    def test_identifiers_and_environment_placeholders_are_safe(self):
        data = b"WHERE key='publish_v2_rollout'; TITLE_API_KEY=${TITLE_API_KEY:-}"
        self.assertEqual(scanner.scan_bytes(data, "example", "test"), [])

    def test_history_finds_removed_key_and_ignored_env_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (root / ".gitignore").write_text(".env\n", encoding="utf-8")
            value = "sk" + "-" + "z9Y8x7W6v5U4" * 4
            (root / "sample.py").write_text(value, encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "synthetic fixture")
            (root / "sample.py").write_text("no credential", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "remove fixture")
            (root / ".env").write_text(value, encoding="utf-8")
            self.assertEqual(scanner.current_scan(root)[0], [])
            findings, _ = scanner.history_scan(root)
            self.assertTrue(any(item["rule"] == "ai-relay-key" for item in findings))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(scanner.main(["--root", directory, "--history"]), 1)
            self.assertNotIn(value, output.getvalue())


if __name__ == "__main__":
    unittest.main()
