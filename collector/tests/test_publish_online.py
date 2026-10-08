import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import publish_online


class PublishOnlineTests(unittest.TestCase):
    def test_config_generates_secret_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "online.json"
            publish_online.create_config("https://example.chatgpt.site/", "token", path)
            payload = json.loads(path.read_text())
            self.assertEqual(payload["site_url"], "https://example.chatgpt.site")
            self.assertGreater(len(payload["ingest_secret"]), 40)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_headers_keep_site_and_ingest_auth_separate(self):
        result = publish_online.headers({
            "ingest_secret": "shared",
            "sites_authorization": "site",
        })
        self.assertEqual(result["Authorization"], "Bearer shared")
        self.assertEqual(result["OAI-Sites-Authorization"], "Bearer site")


if __name__ == "__main__":
    unittest.main()
