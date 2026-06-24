import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.providers.carta.browser.playwright_manager import PlaywrightManager
from services.providers.carta.provider import CartaProvider
from services.providers.carta.api.replay_client import CartaReplayClient, ReplayScenario, ReplayMode, ReplayTarget

async def get_csrf(context):
    cookies = await context.cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    return cookie_dict.get("eshares-csrftoken-2") or cookie_dict.get("csrftoken") or ""

async def debug_fetch():
    await PlaywrightManager.start()
    pw = PlaywrightManager.get()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    
    provider = CartaProvider()
    page = await context.new_page()
    await provider._ensure_authenticated(page)
    
    csrf0 = await get_csrf(context)
    print("Initial CSRF token from page cookies:", csrf0)
    
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
    print("Running HTTPX...")
    res = await client.get(target, scenario=ReplayScenario.HTTPX_ONLY)
    csrf1 = await get_csrf(context)
    print(f"HTTPX result status: {res.status_code}, CSRF token after HTTPX: {csrf1}")
    print(f"CSRF token changed: {csrf0 != csrf1}")
    
    # 2. Run APIRequestContext
    print("Running APIRequestContext...")
    res = await client.get(target, scenario=ReplayScenario.API_CONTEXT_ONLY)
    csrf2 = await get_csrf(context)
    print(f"APIRequestContext result: {res.status_code}, CSRF token after API: {csrf2}")
    print(f"CSRF token changed: {csrf1 != csrf2}")
    
    # 3. Run Browser Fetch
    print("Running Browser Fetch...")
    res = await client.get(target, scenario=ReplayScenario.BROWSER_FETCH_ONLY)
    csrf3 = await get_csrf(context)
    print(f"Browser Fetch result: {res.status_code}, CSRF token after Fetch: {csrf3}")
    
    await page.close()
    await PlaywrightManager.stop()

if __name__ == "__main__":
    asyncio.run(debug_fetch())
