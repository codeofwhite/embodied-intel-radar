from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import radar_refresh


class RadarRefreshTests(unittest.TestCase):
    def test_live_pipeline_orders_collection_before_export_and_notification(self):
        names = [name for name, _, _ in radar_refresh.command_steps(False)]
        self.assertLess(names.index("jobs_collect"), names.index("jobs_export"))
        self.assertLess(names.index("jobs_export"), names.index("feishu"))
        self.assertIn("events", names)
        self.assertIn("social", names)
        self.assertIn("markets", names)

    def test_dry_run_has_no_export_step(self):
        names = [name for name, _, _ in radar_refresh.command_steps(True)]
        self.assertNotIn("jobs_export", names)
        self.assertEqual(names[0], "jobs_collect")
        self.assertIn("markets", names)

    def test_required_timeout_is_recorded_and_later_steps_continue(self):
        def fake_run(command, **kwargs):
            if command[-2:] == ["collect", "--dry-run"]:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial")
            return subprocess.CompletedProcess(command, 0, stdout="ok")

        with patch.object(radar_refresh.subprocess, "run", side_effect=fake_run):
            payload, return_code = radar_refresh.run_refresh(dry_run=True)
        self.assertEqual(return_code, 2)
        self.assertTrue(payload["steps"][0]["timedOut"])
        self.assertEqual(payload["steps"][0]["returnCode"], 124)
        self.assertIn("social", [step["name"] for step in payload["steps"]])
        self.assertEqual(len(payload["steps"]), len(radar_refresh.command_steps(True)))


if __name__ == "__main__":
    unittest.main()
