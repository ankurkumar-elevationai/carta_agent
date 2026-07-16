import asyncio
import json
import os
from playwright.async_api import async_playwright

async def inject():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cookies_file = os.path.join(project_root, "config", "session_cookies.json")
    if not os.path.exists(cookies_file):
        print(f"[ERR] {cookies_file} does not exist. Run import_raw_cookie.py first.")
        return
        
    with open(cookies_file, "r") as f:
        raw_cookies = json.load(f)
        
    formatted_cookies = []
    if isinstance(raw_cookies, dict):
        cookie_data = raw_cookies.get("cookies", raw_cookies)
        if isinstance(cookie_data, dict):
            for name, value in cookie_data.items():
                formatted_cookies.append({
                    "name": name,
                    "value": str(value),
                    "domain": ".carta.com",
                    "path": "/"
                })
        else:
            raw_cookies = cookie_data

    if not formatted_cookies and isinstance(raw_cookies, list):
        for cookie in raw_cookies:
            if isinstance(cookie, dict):
                c = dict(cookie)
                if "domain" not in c:
                    c["domain"] = ".carta.com"
                if "path" not in c:
                    c["path"] = "/"
                formatted_cookies.append(c)

    print(f"Loaded {len(formatted_cookies)} formatted cookies for injection.")
    if not formatted_cookies:
        print("[ERR] No valid cookies found to inject.")
        return

    print("Connecting to Chrome on port 9222...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        print("Injecting cookies...")
        await context.add_cookies(formatted_cookies)
        
        # Navigate the page to the app base URL
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating page to app.carta.com...")
        await page.goto("https://app.carta.com", wait_until="domcontentloaded")
        print("[OK] Session successfully injected and browser navigated!")
        
        # The connection will disconnect naturally when exiting the async context manager


if __name__ == "__main__":
    asyncio.run(inject())
