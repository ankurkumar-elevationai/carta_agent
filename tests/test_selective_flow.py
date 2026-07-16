import sys
import os
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
import json
import time

# Add project root to python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
import utils.db
from api.server import app

class TestSelectiveFlow(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_flow_tasks.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        utils.db.DB_PATH = self.db_path
        
        # Create a dummy export file to satisfy primary export validation
        self.dummy_export = Path("test_export_summary.json")
        self.dummy_export.write_text(json.dumps({
            "task_id": "test-task",
            "company_name": "MangoCart, Inc.",
            "targets": ["inv_asset_valuation"],
            "timestamp": "2026-07-03",
            "status": "completed",
            "description": "Dummy export payload for test validation"
        }))

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        if self.dummy_export.exists():
            self.dummy_export.unlink()

    @patch("api.server.run_provider_agent_with_retry")
    def test_end_to_end_flow_with_targets(self, mock_run_agent):
        # Configure mocked agent runner to succeed instantly and return the dummy export path
        mock_run_agent.return_value = {
            "status": "success",
            "exports": [
                {
                    "type": "summary_json",
                    "path": str(self.dummy_export.resolve())
                }
            ]
        }

        # Initialize FastAPI TestClient which triggers app lifespan (starting background worker)
        with TestClient(app) as client:
            # 1. Submit a download report request with targets
            payload = {
                "company_name": "MangoCart, Inc.",
                "targets": ["inv_asset_valuation"]
            }
            resp = client.post("/api/download-report", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("task_id", data)
            task_id = data["task_id"]
            self.assertEqual(data["status"], "pending")

            # 2. Verify duplicate detection for EXACT SAME targets
            resp_dup = client.post("/api/download-report", json=payload)
            self.assertEqual(resp_dup.status_code, 200)
            data_dup = resp_dup.json()
            self.assertEqual(data_dup["task_id"], task_id)
            self.assertTrue(data_dup.get("duplicate"))

            # 3. Verify DIFFERENT targets do NOT trigger duplicate detection
            payload_different = {
                "company_name": "MangoCart, Inc.",
                "targets": ["inv_cap_call"]
            }
            resp_diff = client.post("/api/download-report", json=payload_different)
            self.assertEqual(resp_diff.status_code, 200)
            data_diff = resp_diff.json()
            self.assertNotEqual(data_diff["task_id"], task_id)
            self.assertIsNone(data_diff.get("duplicate"))

            # 4. Poll status of first task until it is completed
            completed = False
            for _ in range(20):  # poll up to 20 times (2 seconds)
                status_resp = client.get(f"/api/status/{task_id}")
                self.assertEqual(status_resp.status_code, 200)
                status_data = status_resp.json()
                if status_data["status"] == "completed":
                    completed = True
                    break
                time.sleep(0.1)

            self.assertTrue(completed, "Task did not complete within timeout")
            self.assertIn("export_url", status_data)

            # 5. Verify the background worker called mock runner with correctly unpacked targets
            mock_run_agent.assert_any_call("MangoCart, Inc.", task_id, targets=["inv_asset_valuation"])

if __name__ == "__main__":
    unittest.main()
