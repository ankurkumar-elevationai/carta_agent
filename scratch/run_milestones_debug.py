import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.providers.carta.browser.playwright_manager import PlaywrightManager
from services.providers.carta.provider import CartaProvider
from services.providers.carta.api.replay_client import CartaReplayClient, ReplayScenario, ReplayMode, ReplayTarget

async def debug():
    await PlaywrightManager.start()
    pw = PlaywrightManager.get()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = await context.new_page()
    
    provider = CartaProvider()
    print("Running _ensure_authenticated...")
    await provider._ensure_authenticated(page)
    print("Page URL:", page.url)
    
    auth_ctx, _ = await provider._extract_auth_context(page)
    
    client = CartaReplayClient(
        page=page,
        auth_context=auth_ctx,
        mode=ReplayMode.DISCOVERY
    )
    
    target = ReplayTarget(
        method="GET",
        url="/api/tasks/",
        headers={},
        body_hash=None,
        inferred_capabilities={"requires_browser"}
    )
    
    print("\n--- Milestone 1: HTTPX ---")
    res = await client.get(target, scenario=ReplayScenario.HTTPX_ONLY)
    print("HTTPX Status:", res.status_code)
    print("HTTPX Strategy:", res.strategy_used)
    
    print("\n--- Milestone 2: APIRequestContext ---")
    print("Page URL before APIRequestContext:", page.url)
    res = await client.get(target, scenario=ReplayScenario.API_CONTEXT_ONLY)
    print("APIRequestContext Status:", res.status_code)
    print("APIRequestContext Strategy:", res.strategy_used)
    print("Page URL after APIRequestContext:", page.url)
    
    print("\n--- Milestone 3: Browser Fetch ---")
    print("Page URL before Browser Fetch:", page.url)
    try:
        res = await client.get(target, scenario=ReplayScenario.BROWSER_FETCH_ONLY)
        print("Browser Fetch Status:", res.status_code)
        print("Browser Fetch Strategy:", res.strategy_used)
    except Exception as e:
        print("Browser Fetch Error:", e)
        if hasattr(e, 'page_url'):
            print("Failed page_url:", e.page_url)
            
    await page.close()
    await PlaywrightManager.stop()

if __name__ == "__main__":
    asyncio.run(debug())
