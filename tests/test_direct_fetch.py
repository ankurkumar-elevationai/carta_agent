import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from services.providers.carta.api.route_registry import RouteRegistry, EntityContext, ResolvedRoute
from services.providers.carta.api.session_manager import SessionManager
from services.providers.carta.api.direct_fetch import DirectFetchService, DirectFetchResult
from services.providers.carta.api.auth import CartaAuthContext

class TestRouteRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "routes.json"
        self.registry = RouteRegistry(registry_path=str(self.registry_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_seeding(self):
        self.assertTrue(self.registry.is_ready())
        endpoints = self.registry.list_endpoints()
        self.assertGreater(len(endpoints), 0)
        
        # Verify get_investments exists in defaults
        names = [e["name"] for e in endpoints]
        self.assertIn("get_investments", names)

    def test_alias_resolution(self):
        # inv_investment should resolve to get_investments
        resolved = self.registry.resolve_alias("inv_investment")
        self.assertEqual(resolved, "get_investments")
        
        # Unmapped endpoint should return itself
        self.assertEqual(self.registry.resolve_alias("unknown_endpoint"), "unknown_endpoint")

    def test_lookup_firm_level(self):
        ctx = EntityContext(firm_id=3288983, org_id=2925615)
        route = self.registry.lookup("get_investments", ctx)
        
        self.assertEqual(route.method, "GET")
        self.assertFalse(route.requires_entity_id)
        self.assertIn("3288983", route.url)
        self.assertIn("2925615", route.url)

    def test_lookup_entity_level(self):
        ctx = EntityContext(firm_id=3288983, entity_id=3272607)
        route = self.registry.lookup("get_capital_calls", ctx)
        
        self.assertEqual(route.method, "GET")
        self.assertTrue(route.requires_entity_id)
        self.assertIn("3288983", route.url)
        self.assertIn("3272607", route.url)

    def test_lookup_missing_entity_id_raises_value_error(self):
        ctx = EntityContext(firm_id=3288983)  # Missing entity_id
        with self.assertRaises(ValueError):
            self.registry.lookup("get_capital_calls", ctx)

    def test_save_and_load(self):
        # Modify a route and save
        self.registry.routes["get_investments"]["url_template"] = "/custom/path/{firm_id}/"
        self.registry.save()
        
        # Create a new registry pointing to the same file
        new_registry = RouteRegistry(registry_path=str(self.registry_path))
        self.assertEqual(new_registry.routes["get_investments"]["url_template"], "/custom/path/{firm_id}/")

    def test_update_from_extraction(self):
        extracted_urls = [
            {"url": "https://app.carta.com/api/investors/portfolio/firm/2925615/list_individual_portfolio_investments/3288983/list/", "category": "portfolio"},
            {"url": "https://app.carta.com/api/corporations/3288983/corporation_info/3272607/", "category": "cap_table"}
        ]
        self.registry.update_from_extraction(
            extracted_urls=extracted_urls,
            firm_id=3288983,
            entity_id=3272607,
            org_id=2925615
        )
        
        # Check that URL templates are updated correctly
        ctx = EntityContext(firm_id=3288983, org_id=2925615, entity_id=3272607)
        
        route_inv = self.registry.lookup("get_investments", ctx)
        self.assertEqual(route_inv.url, "https://app.carta.com/api/investors/portfolio/firm/2925615/list_individual_portfolio_investments/3288983/list/")
        
        route_info = self.registry.lookup("get_investment_extra_info", ctx)
        self.assertEqual(route_info.url, "https://app.carta.com/api/corporations/3288983/corporation_info/3272607/")


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cookies_path = Path(self.temp_dir.name) / "session_cookies.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_from_dict_file(self):
        cookies_data = {"sessionid": "test_sess_123", "csrftoken": "test_csrf_456"}
        with open(self.cookies_path, "w") as f:
            json.dump(cookies_data, f)
            
        manager = SessionManager(cookies_path=str(self.cookies_path))
        ctx = manager._load_from_file()
        
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.session_id, "test_sess_123")
        self.assertEqual(ctx.csrf_token, "test_csrf_456")
        self.assertEqual(ctx.cookies["sessionid"], "test_sess_123")

    def test_load_from_playwright_list_file(self):
        cookies_data = [
            {"name": "sessionid", "value": "pw_sess_789", "domain": ".carta.com"},
            {"name": "csrftoken", "value": "pw_csrf_abc", "domain": ".carta.com"}
        ]
        with open(self.cookies_path, "w") as f:
            json.dump(cookies_data, f)
            
        manager = SessionManager(cookies_path=str(self.cookies_path))
        ctx = manager._load_from_file()
        
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.session_id, "pw_sess_789")
        self.assertEqual(ctx.csrf_token, "pw_csrf_abc")


class TestDirectFetchService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = MagicMock(spec=RouteRegistry)
        self.registry.is_ready.return_value = True
        self.registry.resolve_alias.side_effect = lambda x: x
        
        self.session_manager = MagicMock(spec=SessionManager)
        self.auth_ctx = CartaAuthContext(
            session_id="sess_123",
            extracted_at=MagicMock(),
            last_refreshed_at=MagicMock(),
            version=1,
            cookies={"sessionid": "sess_123", "csrftoken": "csrf_456"},
            csrf_token="csrf_456",
            user_agent="test_agent"
        )
        self.session_manager.get_auth_context = AsyncMock(return_value=self.auth_ctx)
        
        self.service = DirectFetchService(
            registry=self.registry,
            session_manager=self.session_manager
        )

    async def test_fetch_success(self):
        route = ResolvedRoute(
            url="https://app.carta.com/api/test",
            method="GET",
            params={},
            category="test",
            requires_entity_id=False,
            template_name="test"
        )
        self.registry.lookup.return_value = route
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = '{"success": true}'
        mock_response.json.return_value = {"success": True}
        
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        
        with patch.object(self.service, "_get_client", AsyncMock(return_value=mock_client)):
            result = await self.service.fetch("get_investments", firm_id=123)
            
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.payload, {"success": True})
            self.assertIsNone(result.error)

    async def test_fetch_auth_expired_triggers_refresh(self):
        route = ResolvedRoute(
            url="https://app.carta.com/api/test",
            method="GET",
            params={},
            category="test",
            requires_entity_id=False,
            template_name="test"
        )
        self.registry.lookup.return_value = route
        
        # First call returns 401 Unauthorized, second retry returns 200 OK
        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.headers = {}
        resp_401.text = "Unauthorized"
        
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {}
        resp_200.text = '{"success": true}'
        resp_200.json.return_value = {"success": True}
        
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[resp_401, resp_200])
        
        with patch.object(self.service, "_get_client", AsyncMock(return_value=mock_client)):
            result = await self.service.fetch("get_investments", firm_id=123)
            
            # The session manager invalidate should be called on 401
            self.session_manager.invalidate.assert_called_once()
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.payload, {"success": True})
            self.assertTrue(result.retried)

if __name__ == "__main__":
    unittest.main()
