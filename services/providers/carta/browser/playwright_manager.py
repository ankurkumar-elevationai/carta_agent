import logging
import asyncio

log = logging.getLogger(__name__)

class PlaywrightManager:
    """
    Singleton Playwright runtime. Initialized ONCE at server startup,
    reused across all tasks and providers.
    """
    _playwright = None
    _lock = asyncio.Lock()

    @classmethod
    async def start(cls):
        async with cls._lock:
            if cls._playwright is not None:
                return
            from playwright.async_api import async_playwright
            log.info("Starting singleton Playwright runtime...")
            cls._playwright = await async_playwright().start()
            log.info("Playwright runtime started.")

    @classmethod
    def get(cls):
        if cls._playwright is None:
            raise RuntimeError("PlaywrightManager not started.")
        return cls._playwright

    @classmethod
    async def stop(cls):
        async with cls._lock:
            if cls._playwright is not None:
                try:
                    await cls._playwright.stop()
                except Exception as e:
                    log.warning(f"Error stopping Playwright runtime: {e}")
                finally:
                    cls._playwright = None
            log.info("Playwright runtime stopped.")
