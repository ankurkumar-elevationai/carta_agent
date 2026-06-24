import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.providers.carta.browser.playwright_manager import PlaywrightManager
from services.providers.carta.provider import CartaProvider

async def debug_fetch():
    await PlaywrightManager.start()
    pw = PlaywrightManager.get()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    
    provider = CartaProvider()
    page = await context.new_page()
    
    # Listeners to capture request referers
    def handle_request(req):
        if "api/tasks" in req.url:
            print(f"[FETCH REQUEST] Referer: {req.headers.get('referer')}")
            
    page.on("request", handle_request)
    
    # Step 1: Nav to /investors/firm/1/portfolio/
    await page.goto("https://app.playground.carta.team/investors/firm/1/portfolio/")
    await asyncio.sleep(2.0)
    print(f"Page URL: {page.url}")
    
    js_fetch = """
        async () => {
            const res = await fetch("/api/tasks/");
            return res.status;
        }
    """
    
    status1 = await page.evaluate(js_fetch)
    print(f"Fetch status when page is at {page.url}: {status1}")
    
    # Step 2: Nav to /investors/firm/1/portfolio/gp-activity
    await page.goto("https://app.playground.carta.team/investors/firm/1/portfolio/gp-activity")
    await asyncio.sleep(2.0)
    print(f"Page URL: {page.url}")
    
    status2 = await page.evaluate(js_fetch)
    print(f"Fetch status when page is at {page.url}: {status2}")
    
    # Step 3: Nav to /investors/firm/1/portfolio/gp-activity/tasks
    await page.goto("https://app.playground.carta.team/investors/firm/1/portfolio/gp-activity/tasks")
    await asyncio.sleep(2.0)
    print(f"Page URL: {page.url}")
    
    status3 = await page.evaluate(js_fetch)
    print(f"Fetch status when page is at {page.url}: {status3}")
    
    await page.close()
    await PlaywrightManager.stop()

if __name__ == "__main__":
    asyncio.run(debug_fetch())
