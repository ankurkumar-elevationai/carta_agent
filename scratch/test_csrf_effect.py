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
    await provider._ensure_authenticated(page)
    print(f"Landed on page URL: {page.url}")
    
    js_relative = """
        async () => {
            try {
                const res = await fetch("/api/tasks/");
                return { status: res.status };
            } catch(e) {
                return { error: e.toString() };
            }
        }
    """

    js_absolute = """
        async () => {
            try {
                const res = await fetch("https://app.playground.carta.team/api/tasks/");
                return { status: res.status };
            } catch(e) {
                return { error: e.toString() };
            }
        }
    """

    res1 = await page.evaluate(js_relative)
    print("Relative fetch status:", res1)
    
    res2 = await page.evaluate(js_absolute)
    print("Absolute fetch status:", res2)
    
    await page.close()
    await PlaywrightManager.stop()

if __name__ == "__main__":
    asyncio.run(debug_fetch())
