import unittest
from services.platform_schema import InvAssetValuation
from services.platform_payload_mapper import PlatformPayloadMapper

class TestPlatformPayloadMapper(unittest.TestCase):
    
    def setUp(self):
        self.mapper = PlatformPayloadMapper()

    def test_latest_valuation_selected_by_full_date(self):
        valuations = [
            InvAssetValuation(investment_id="inv_1", amount=100.0, year="2023", date="2023-01-01"),
            InvAssetValuation(investment_id="inv_1", amount=300.0, year="2024", date="2024-05-15"),
            InvAssetValuation(investment_id="inv_1", amount=200.0, year="2024", date="2024-01-10"),
        ]
        
        payloads = self.mapper.map_portfolio_investment_update(valuations)
        
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].data.valuation, 300.0)
        self.assertEqual(payloads[0].data.valuation_year, "2024")

    def test_missing_valuation_date_fallback_to_year(self):
        valuations = [
            InvAssetValuation(investment_id="inv_1", amount=150.0, year="2022", date=None),
            InvAssetValuation(investment_id="inv_1", amount=250.0, year="2023", date=None),
        ]
        
        payloads = self.mapper.map_portfolio_investment_update(valuations)
        
        self.assertEqual(payloads[0].data.valuation, 250.0)
        self.assertEqual(payloads[0].data.valuation_year, "2023")

    def test_placeholder_ids_present(self):
        valuations = [
            InvAssetValuation(investment_id="inv_123", amount=10.0, year="2020", date="2020-01-01"),
        ]
        
        payloads = self.mapper.map_portfolio_investment_update(valuations)
        
        self.assertEqual(payloads[0].org_id, "__ORG_ID__")
        self.assertEqual(payloads[0].user_id, "__USER_ID__")
        self.assertEqual(payloads[0].investment_id, "inv_123")

    def test_null_valuation_handled(self):
        # Even if amount is zero or missing from upstream
        valuations = [
            InvAssetValuation(investment_id="inv_null", amount=0.0, year="2020", date="2020-01-01"),
        ]
        
        payloads = self.mapper.map_portfolio_investment_update(valuations)
        
        self.assertEqual(payloads[0].data.valuation, 0.0)

    def test_payload_validation(self):
        # Pydantic validation test implicitly happens when mapping
        valuations = [
            InvAssetValuation(investment_id="inv_valid", amount=999.99, year="2025", date="2025-10-10"),
        ]
        payloads = self.mapper.map_portfolio_investment_update(valuations)
        
        dump = payloads[0].model_dump()
        self.assertIn("org_id", dump)
        self.assertIn("user_id", dump)
        self.assertIn("investment_id", dump)
        self.assertIn("data", dump)
        self.assertIn("valuation", dump["data"])
        self.assertIn("valuation_year", dump["data"])
        self.assertEqual(dump["data"]["valuation"], 999.99)
        self.assertEqual(dump["data"]["valuation_year"], "2025")

if __name__ == '__main__':
    unittest.main()
