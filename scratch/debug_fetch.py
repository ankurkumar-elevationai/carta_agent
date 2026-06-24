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
    
    # Set up listeners
    def handle_request(req):
        if "api/tasks" in req.url:
            print(f"\n[REQUEST] URL: {req.url}")
            print(f"[REQUEST] Method: {req.method}")
            print("[REQUEST] Headers:")
            for k, v in req.headers.items():
                print(f"  {k}: {v}")
                
    def handle_response(res):
        if "api/tasks" in res.url:
            print(f"\n[RESPONSE] URL: {res.url}")
            print(f"[RESPONSE] Status: {res.status}")
            print("[RESPONSE] Headers:")
            for k, v in res.headers.items():
                print(f"  {k}: {v}")

    page.on("request", handle_request)
    page.on("response", handle_response)

    print("Navigating using _ensure_authenticated...")
    await provider._ensure_authenticated(page)
    print(f"Landed on page URL: {page.url}")
    
    js_simple = """
        async () => {
            try {
                const res = await fetch("/api/tasks/", {
                    headers: {
                        'Accept': 'application/json, text/plain, */*'
                    }
                });
                const text = await res.text();
                return { status: res.status, text: text.substring(0, 200) };
            } catch(e) {
                return { error: e.toString() };
            }
        }
    """
    
    print("Executing fetch...")
    res = await page.evaluate(js_simple)
    print("Fetch result:", res)
    
    await page.close()
    await PlaywrightManager.stop()

if __name__ == "__main__":
    asyncio.run(debug_fetch())
