import sys
import os
import asyncio
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.providers.carta.api import CartaReplayClient, CartaAuthContext, ReplayMode
from services.providers.carta import PlaywrightManager

async def test_replay():
    load_dotenv()
    
    manager = PlaywrightManager()
    await manager.start()
    p = manager.get()
    
    browser = await p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    
    try:
        pages = context.pages
        if not pages:
            page = await context.new_page()
        else:
            page = pages[0]
            
        print(f"Current page URL: {page.url}")
        
        # Ensure we are not on about:blank or login
        if "about:blank" in page.url or "login" in page.url:
            print("Navigating to app base URL for context stability...")
            await page.goto("https://app.playground.carta.team/investors/firm/1/portfolio/gp-activity/")
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                print(f"wait_for_load_state timed out (ignoring): {e}")
            
        # Manually extract cookies and CSRF
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        
        csrf_token = cookie_dict.get('csrftoken', '')
        
        from datetime import datetime
        auth = CartaAuthContext(
            session_id="test_session",
            extracted_at=datetime.utcnow(),
            last_refreshed_at=datetime.utcnow(),
            version=1,
            cookies=cookie_dict,
            csrf_token=csrf_token,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        client = CartaReplayClient(page, auth, ReplayMode.EXTRACTION)
        
        print("\n--- Testing GET /api/tasks/ ---")
        try:
            res = await client.get("/api/tasks/")
            print(f"Status: {res.status_code}")
            print(f"Latency: {res.latency_ms}ms")
            print(f"Strategy: {res.strategy_used}")
            print(f"Timeline: {res.timeline}")
            print(f"Payload Keys: {list(res.payload.keys()) if isinstance(res.payload, dict) else 'Not a dict'}")
        except Exception as e:
            print(f"ReplayException: {e}")
            if hasattr(e, 'final_url'):
                print(f"Final URL: {e.final_url}")
                print(f"Page URL: {e.page_url}")
                print(f"Strategy: {e.strategy}")
                print(f"Status Code: {e.status_code}")

    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(test_replay())
