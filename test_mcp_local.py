import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path('.').resolve()))

from scripts.mcp_server import handle_call_tool, handle_read_resource

async def test_mcp_endpoints():
    print("=== Testing MCP Server Platform Endpoints ===\n")

    print("1. Testing Coverage Resource (platform://default-tenant/coverage)...")
    coverage_resp = await handle_read_resource("platform://default-tenant/coverage")
    coverage_data = json.loads(coverage_resp)
    print(f"Success!")
    print(f"Overall Field Coverage: {coverage_data.get('summary', {}).get('overall_field_coverage_pct')}%")
    print(f"Tables Populated: {coverage_data.get('summary', {}).get('tables_with_data')} / 19")
    
    print("\n-------------------------------------------------\n")

    # List of all platform schema tools
    platform_tools = [
        "get_investments", "get_investment_extra_info", "get_investment_team",
        "get_investment_valuations", "get_capital_calls", "get_investment_log",
        "get_investment_transactions", "get_investment_firm", "get_investment_focus",
        "get_investment_sectors", "get_investment_certificates", "get_distribution_history",
        "get_liquidity_distributions", "get_investment_expenses", "get_investment_interest",
        "get_investment_services", "get_usage_logs", "get_recent_developments",
        "get_growth_signals"
    ]

    for idx, tool_name in enumerate(platform_tools, start=2):
        print(f"{idx}. Testing Tool: {tool_name}...")
        try:
            tool_resp = await handle_call_tool(tool_name, {})
            content = json.loads(tool_resp[0].text)
            print(f"   Success! | Table: {content.get('table')} | Record Count: {content.get('record_count')}")
            
            # Print a single sample if there are records
            if content.get('record_count', 0) > 0 and content.get('data'):
                print("   Sample Data:")
                # Just print the first few keys of the first record to keep the output concise
                sample = content['data'][0]
                short_sample = {k: v for k, v in list(sample.items())[:4]} # First 4 fields
                print(f"     {json.dumps(short_sample)}")
            elif content.get('record_count') == 0:
                print("   (Empty/Stub)")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_mcp_endpoints())
