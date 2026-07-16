import unittest
from pathlib import Path
import os
import sqlite3
import json

from utils.db import init_db, claim_next_task
from services.providers.carta.models.extraction import EndpointCategory
from services.providers.carta.intelligence.intelligence_extractor import IntelligenceExtractor

class TestSelectiveScraping(unittest.TestCase):
    
    def setUp(self):
        self.db_path = "test_tasks.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                completed_at REAL,
                export_url TEXT,
                error TEXT,
                targets TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_database_targets_serialization(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        targets = ["inv_asset_valuation", "inv_cap_call"]
        cursor.execute(
            "INSERT INTO tasks (task_id, company_name, status, created_at, targets) VALUES (?, ?, ?, ?, ?)",
            ("task-123", "Test Company", "pending", 123456789.0, json.dumps(targets))
        )
        conn.commit()
        conn.close()

        import utils.db
        old_db_path = utils.db.DB_PATH
        utils.db.DB_PATH = self.db_path
        
        import asyncio
        loop = asyncio.new_event_loop()
        
        try:
            row = loop.run_until_complete(claim_next_task("pending", "downloading"))
            self.assertIsNotNone(row)
            task_id, company_name, targets_str = row
            self.assertEqual(task_id, "task-123")
            self.assertEqual(company_name, "Test Company")
            self.assertEqual(json.loads(targets_str), ["inv_asset_valuation", "inv_cap_call"])
        finally:
            utils.db.DB_PATH = old_db_path
            loop.close()

    def test_endpoint_matches_targets(self):
        extractor = IntelligenceExtractor(
            classifier=None,
            replay_client=None,
            output_dir=Path("."),
            target_platform_schemas=["inv_asset_valuation"]
        )

        self.assertTrue(extractor._endpoint_matches_targets("/api/v1/valuations", EndpointCategory.VALUATIONS))
        self.assertTrue(extractor._endpoint_matches_targets("/api/v1/valuations/123", EndpointCategory.VALUATIONS))

        self.assertFalse(extractor._endpoint_matches_targets("/api/v1/captable/summary", EndpointCategory.CAP_TABLE))
        self.assertFalse(extractor._endpoint_matches_targets("/api/v1/investments", EndpointCategory.PORTFOLIO))

        extractor_multi = IntelligenceExtractor(
            classifier=None,
            replay_client=None,
            output_dir=Path("."),
            target_platform_schemas=["inv_asset_valuation", "get_capital_calls"]
        )
        self.assertTrue(extractor_multi._endpoint_matches_targets("/api/v1/valuations", EndpointCategory.VALUATIONS))
        self.assertTrue(extractor_multi._endpoint_matches_targets("/api/v1/capital_calls", EndpointCategory.REPORTING))
        self.assertFalse(extractor_multi._endpoint_matches_targets("/api/v1/captable/summary", EndpointCategory.CAP_TABLE))

    def test_org_discovery_match_via_investments(self):
        from unittest.mock import AsyncMock, MagicMock
        from services.providers.carta.discovery.org_discovery import OrganizationDiscoveryEngine
        from services.providers.carta.models.extraction import OrganizationNode
        
        mock_replay = MagicMock()
        mock_replay.get = AsyncMock()
        
        orgs = [
            OrganizationNode(org_pk=455, name="Carta Demo Ventures", account_type="investment firm", landing_url=""),
            OrganizationNode(org_pk=1, name="Krakatoa Ventures", account_type="investment firm", landing_url=""),
        ]
        
        mock_result = MagicMock()
        mock_result.payload = [
            {"company": "Heart Round 2, Inc.", "legal_name": "Heart Round 2, Inc.", "dba": "HeartSpan"}
        ]
        
        async def mock_get(target, scenario=None):
            if "firm/1/" in target.url:
                return mock_result
            return MagicMock(payload=[])
            
        mock_replay.get.side_effect = mock_get
        
        engine = OrganizationDiscoveryEngine(replay_client=mock_replay)
        
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            matched = loop.run_until_complete(engine._match_via_investments("Heart Round 2, Inc.", orgs))
            self.assertIsNotNone(matched)
            self.assertEqual(matched.org_pk, 1)
            self.assertEqual(matched.name, "Krakatoa Ventures")
            
            matched_lc = loop.run_until_complete(engine._match_via_investments("heart round", orgs))
            self.assertIsNotNone(matched_lc)
            self.assertEqual(matched_lc.org_pk, 1)
        finally:
            loop.close()

if __name__ == '__main__':
    unittest.main()
