import asyncio
import json
import logging
from services.providers.carta.api.direct_fetch import DirectFetchService

# Set up logging to stdout
logging.basicConfig(level=logging.WARNING)

async def main():
    with open("resolved_organizations.json", "r", encoding="utf-8") as f:
        orgs = json.load(f)
        
    service = DirectFetchService()
    try:
        print(f"Testing {len(orgs)} resolved organizations...")
        for org in orgs:
            name = org["name"]
            firm_id = int(org["firm_id"])
            entity_id = int(org["entity_id"])
            org_id = int(org["org_id"])
            org_uuid = org["org_uuid"]
            fund_uuid = org["fund_uuid"]
            partner_id = str(org["partner_id"])
            
            print(f"\n--- Testing: {name} ---")
            print(f"Firm ID: {firm_id}, Partner ID: {partner_id}")
            
            res = await service.fetch(
                endpoint_name="get_capital_account_summary",
                firm_id=firm_id,
                entity_id=entity_id,
                org_id=org_id,
                org_uuid=org_uuid,
                fund_uuid=fund_uuid,
                partner_id=partner_id,
                start_date="10/01/2025",
                end_date="12/31/2025",
            )
            
            print(f"Result Status: {res.status_code}")
            if res.status_code == 200:
                payload = res.payload
                print(f"Success! Partner: {payload.get('partner_name')}")
                print(f"Fund: {payload.get('fund_name')}")
                print(f"Ending Balance LP: {payload.get('ending_balance', {}).get('lp')}")
            else:
                print(f"FAILED: Status {res.status_code}, Error: {res.error}")
                print(f"Tested URL: {res.url}")
            
    finally:
        await service.close()

if __name__ == "__main__":
    asyncio.run(main())
