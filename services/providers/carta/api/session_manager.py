"""
services/providers/carta/api/session_manager.py
------------------------------------------------
Session Manager — Maintains a live CartaAuthContext (cookies + CSRF)
without requiring a browser for each request. Reads from the persistent
browser's cookie file and optionally refreshes from CDP.
"""

import json
import logging
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from .auth import CartaAuthContext

log = logging.getLogger(__name__)


class SessionManager:
    """
    Singleton-style session manager that provides live CartaAuthContext
    for direct HTTP fetch requests.
    
    Cookie sources (in priority order):
    1. In-memory cached auth context (if not expired)
    2. session_cookies.json on disk (written by start_persistent_browser.py)
    3. CDP browser refresh (if persistent browser is running on port 9222)
    """

    # Session cookies are valid for ~4 hours on Carta
    MAX_AGE_SECONDS = 4 * 3600

    def __init__(self, cookies_path: str = None):
        project_root = Path(__file__).resolve().parents[4]
        self.cookies_path = Path(cookies_path) if cookies_path else project_root / "config" / "session_cookies.json"
        self._auth_ctx: Optional[CartaAuthContext] = None
        self._loaded_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def get_auth_context(self) -> CartaAuthContext:
        """
        Get a valid CartaAuthContext. Attempts refresh if expired.
        
        Returns:
            CartaAuthContext with cookies and CSRF token
            
        Raises:
            RuntimeError: If no valid session could be obtained
        """
        async with self._lock:
            # 1. Return cached if still fresh
            if self._auth_ctx and self._loaded_at:
                age = time.time() - self._loaded_at
                if age < self.MAX_AGE_SECONDS:
                    return self._auth_ctx

            # 2. Try loading from disk
            ctx = self._load_from_file()
            if ctx:
                self._auth_ctx = ctx
                self._loaded_at = time.time()
                log.info("[SessionManager] Loaded auth context from session_cookies.json")
                return ctx

            # 3. Try CDP browser refresh
            ctx = await self._refresh_from_cdp()
            if ctx:
                self._auth_ctx = ctx
                self._loaded_at = time.time()
                log.info("[SessionManager] Refreshed auth context from CDP browser")
                return ctx

            raise RuntimeError(
                "No valid Carta session available. "
                "Please run 'python scripts/start_persistent_browser.py' and log in, "
                "or ensure session_cookies.json exists."
            )

    def invalidate(self):
        """Force a re-read on next access (e.g., after a 401/403)."""
        self._auth_ctx = None
        self._loaded_at = None
        if self.cookies_path.exists():
            try:
                self.cookies_path.unlink()
                log.info(f"[SessionManager] Deleted invalid cookie file: {self.cookies_path}")
            except Exception as e:
                log.warning(f"[SessionManager] Failed to delete cookie file: {e}")
        log.info("[SessionManager] Session invalidated. Will re-read on next access.")

    def _load_from_file(self) -> Optional[CartaAuthContext]:
        """Read cookies from the persistent browser's session file."""
        if not self.cookies_path.exists():
            log.warning(f"[SessionManager] Cookie file not found: {self.cookies_path}")
            return None

        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # session_cookies.json can be either:
            # A) A list of Playwright-style cookie objects [{name, value, domain, ...}]
            # B) A dict of {cookie_name: cookie_value}
            cookies_dict: Dict[str, str] = {}
            csrf_token = ""

            if isinstance(raw, list):
                # Playwright-style cookie list
                for cookie in raw:
                    name = cookie.get("name", "")
                    value = cookie.get("value", "")
                    if name and value:
                        cookies_dict[name] = value
                        if name.lower() in ("csrftoken", "eshares-csrftoken-2"):
                            csrf_token = value
            elif isinstance(raw, dict):
                # Simple key-value dict
                if "cookies" in raw:
                    cookies_dict = raw["cookies"]
                else:
                    cookies_dict = raw
                csrf_token = cookies_dict.get("eshares-csrftoken-2") or cookies_dict.get("csrftoken") or ""
            else:
                log.warning(f"[SessionManager] Unexpected cookie file format: {type(raw)}")
                return None

            if not cookies_dict:
                log.warning("[SessionManager] Cookie file is empty.")
                return None

            # Try to extract CSRF from cookie if not found
            if not csrf_token:
                csrf_token = cookies_dict.get("eshares-csrftoken-2") or cookies_dict.get("csrftoken") or cookies_dict.get("_csrf", "")

            # Check for sessionid to validate the session is real
            session_id = cookies_dict.get("eshares-sessionid-2") or cookies_dict.get("sessionid") or cookies_dict.get("session_id", "unknown")

            return CartaAuthContext(
                session_id=session_id,
                extracted_at=datetime.utcnow(),
                last_refreshed_at=datetime.utcnow(),
                version=1,
                cookies=cookies_dict,
                csrf_token=csrf_token,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            )

        except Exception as e:
            log.error(f"[SessionManager] Failed to parse cookie file: {e}")
            return None

    async def _refresh_from_cdp(self, port: int = 9222) -> Optional[CartaAuthContext]:
        """
        Attempt to refresh cookies from a running Chrome instance via CDP.
        This connects to the persistent browser started by start_persistent_browser.py.
        """
        try:
            import httpx

            # Check if CDP is available
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"http://localhost:{port}/json/version")
                if resp.status_code != 200:
                    return None

            # Use playwright to connect and extract cookies
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(f"http://localhost:{port}")
                contexts = browser.contexts
                if not contexts:
                    log.warning("[SessionManager] CDP browser has no contexts.")
                    return None

                context = contexts[0]
                raw_cookies = await context.cookies()

                cookies_dict: Dict[str, str] = {}
                csrf_token = ""

                for cookie in raw_cookies:
                    name = cookie.get("name", "")
                    value = cookie.get("value", "")
                    domain = cookie.get("domain", "")
                    if name and value and ("carta.com" in domain or "carta.team" in domain):
                        cookies_dict[name] = value
                        if name.lower() in ("csrftoken", "eshares-csrftoken-2"):
                            csrf_token = value

                if not cookies_dict:
                    log.warning("[SessionManager] No Carta cookies found in CDP browser.")
                    return None

                # Get page URL and user agent
                pages = context.pages
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                if pages:
                    try:
                        user_agent = await pages[0].evaluate("navigator.userAgent")
                    except Exception:
                        pass

                if not csrf_token:
                    csrf_token = cookies_dict.get("eshares-csrftoken-2") or cookies_dict.get("csrftoken") or ""

                session_id = cookies_dict.get("eshares-sessionid-2") or cookies_dict.get("sessionid", "cdp_session")

                # Also save to disk for next time
                self._save_cookies_to_file(cookies_dict)

                return CartaAuthContext(
                    session_id=session_id,
                    extracted_at=datetime.utcnow(),
                    last_refreshed_at=datetime.utcnow(),
                    version=1,
                    cookies=cookies_dict,
                    csrf_token=csrf_token,
                    user_agent=user_agent,
                )

        except ImportError:
            log.debug("[SessionManager] Playwright not available for CDP refresh.")
            return None
        except Exception as e:
            log.debug(f"[SessionManager] CDP refresh failed: {e}")
            return None

    def _save_cookies_to_file(self, cookies_dict: Dict[str, str]):
        """Persist refreshed cookies back to disk."""
        try:
            self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cookies_path, "w", encoding="utf-8") as f:
                json.dump(cookies_dict, f, indent=2)
            log.info(f"[SessionManager] Saved {len(cookies_dict)} cookies to {self.cookies_path}")
        except Exception as e:
            log.warning(f"[SessionManager] Failed to save cookies: {e}")
