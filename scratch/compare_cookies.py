import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.providers.carta.browser.playwright_manager import PlaywrightManager
from services.providers.carta.provider import CartaProvider
from services.providers.carta.api.replay_client import CartaReplayClient, ReplayScenario, ReplayMode, ReplayTarget

async def print_cookies(context, label):
    cookies = await context.cookies()
    print(f"\n--- Cookies {label} ---")
    for c in sorted(cookies, key=lambda x: x['name']):
        print(f"  {c['name']}: {c['value'][:30]}... (domain={c['domain']}, path={c['path']})")

async def debug_fetch():
    await PlaywrightManager.start()
    pw = PlaywrightManager.get()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    
    provider = CartaProvider()
    page = await context.new_page()
    await provider._ensure_authenticated(page)
    
    await print_cookies(context, "Initial")
    
    auth_ctx, _ = await provider._extract_auth_context(page)
    client = CartaReplayClient(page, auth_ctx, ReplayMode.DISCOVERY)
    
    target = ReplayTarget(
        method="GET",
        url="/api/tasks/",
        headers={},
        body_hash=None,
        inferred_capabilities={"requires_browser"}
    )
    
    # 1. Run HTTPX
    print("\nRunning HTTPX...")
    await client.get(target, scenario=ReplayScenario.HTTPX_ONLY)
    await print_cookies(context, "After HTTPX")
    
    # 2. Run APIRequestContext
    print("\nRunning APIRequestContext...")
    await client.get(target, scenario=ReplayScenario.API_CONTEXT_ONLY)
    await print_cookies(context, "After APIRequestContext")
    
    # 3. Run Browser Fetch
    print("\nRunning Browser Fetch...")
    try:
        res = await client.get(target, scenario=ReplayScenario.BROWSER_FETCH_ONLY)
        print("Browser Fetch Status:", res.status_code)
    except Exception as e:
        print("Browser Fetch Error:", e)
        
    await page.close()
    await PlaywrightManager.stop()

if __name__ == "__main__":
    asyncio.run(debug_fetch())
