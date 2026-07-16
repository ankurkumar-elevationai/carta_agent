import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        page = None
        for p_page in context.pages:
            if "carta.com" in p_page.url:
                page = p_page
                break
                
        if not page:
            print("No open Carta tab found!")
            await browser.close()
            return
            
        # Target partner resolution URL for SiO Space I LLC
        url = "https://fund-admin.app.carta.com/v2/partners/organization/c468c5e3-8847-4bf1-a7cf-2051abc4c306/fund/7248bb0f-4f45-4b51-b358-878824b27998/"
        print(f"Fetching {url} inside browser...")
        
        js_fetch = f"""
        async () => {{
            try {{
                const res = await fetch('{url}', {{ credentials: 'include' }});
                return await res.json();
            }} catch (e) {{
                return {{ error: e.toString() }};
            }}
        }}
        """
        
        res_data = await page.evaluate(js_fetch)
        print("\nResponse:")
        print(json.dumps(res_data, indent=2))
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
