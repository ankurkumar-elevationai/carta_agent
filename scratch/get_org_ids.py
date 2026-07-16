import asyncio
import os
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
            
        target_url = "https://app.carta.com/investors/individual/2115793/portfolio/1967488/capital-account-statements"
        print(f"Monitoring network requests for {target_url}...")
        
        requests = []
        
        # Listen for request events
        def handle_request(req):
            url = req.url
            if "carta.com" in url or "carta.team" in url:
                requests.append({
                    "url": url,
                    "method": req.method,
                    "headers": req.headers
                })
                
        page.on("request", handle_request)
        
        await page.goto(target_url, wait_until="load")
        await page.wait_for_timeout(8000)
        
        os.makedirs("scratch", exist_ok=True)
        out_path = "scratch/captured_requests.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"Monitored URL: {target_url}\n")
            f.write(f"Total Carta requests captured: {len(requests)}\n\n")
            for idx, req in enumerate(requests):
                f.write(f"[{idx+1}] {req['method']} {req['url']}\n")
                f.write("Headers:\n")
                for k, v in req["headers"].items():
                    if k.lower() in ("x-csrftoken", "referer", "host", "origin", "cookie", "accept", "x-requested-with"):
                        f.write(f"  {k}: {v}\n")
                f.write("-" * 80 + "\n")
                
        print(f"Saved captured requests to {out_path}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
