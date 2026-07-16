import asyncio
import json
import logging
from services.providers.carta.api.direct_fetch import DirectFetchService

# Set up logging to stdout
logging.basicConfig(level=logging.INFO)

async def main():
    service = DirectFetchService()
    try:
        # EC Space Tech I, LLC (org_id: 1881616, firm_id: 2115793, entity_id: 1967488)
        # Correct partner_id: 211270
        res = await service.fetch(
            endpoint_name="get_capital_account_summary",
            firm_id=2115793,
            entity_id=1967488,
            org_id=1881616,
            org_uuid="57d7aa77-506c-4941-af9a-7e3414043e37",
            fund_uuid="db2be2c9-f1a9-4d82-aa74-945f32712a7b",
            partner_id="211270",
            start_date="10/01/2025",
            end_date="12/31/2025",
        )
        
        print("\nDirect Fetch Result:")
        print(f"Status Code: {res.status_code}")
        print(f"Latency: {res.latency_ms}ms")
        print(f"Error: {res.error}")
        print(f"URL: {res.url}")
        
        if res.payload:
            print("\nPayload Preview:")
            print(json.dumps(res.payload, indent=2)[:2000])
        else:
            print("\nNo payload returned.")
            
    finally:
        await service.close()

if __name__ == "__main__":
    asyncio.run(main())
