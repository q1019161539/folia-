import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from folia_upstream import UpstreamStatusStore, newest_stable_release


class FoliaUpstreamTests(unittest.TestCase):
    def test_stable_release_ignores_prerelease(self):
        selected = newest_stable_release([
            {"tag_name": "v0.8.0-beta", "prerelease": True},
            {"tag_name": "v0.7.7", "prerelease": False},
            {"tag_name": "nightly", "prerelease": False},
        ])
        self.assertEqual(selected["tag_name"], "v0.7.7")

    def test_update_notification_is_deduplicated(self):
        result = {"ok": True, "latest_release": "v0.8.0", "update_available": True, "image_ready": True}
        with tempfile.TemporaryDirectory() as value:
            store = UpstreamStatusStore(Path(value) / "status.json")
            notices = []
            with patch("folia_upstream.check_upstream", return_value=result):
                store.refresh({}, notices.append)
                store.refresh({}, notices.append)
            self.assertEqual(len(notices), 1)
            self.assertEqual(store.load()["notified_release"], "v0.8.0")


if __name__ == "__main__":
    unittest.main()
