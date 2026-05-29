import asyncio
import logging
import sys
import os
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.providers.carta.browser.cdp_pool import CDPPageRegistry
from services.providers.carta.discovery.passive_collector import PassiveNetworkCollector
from services.providers.carta.intelligence.duckdb_client import DuckDBAnalytics

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

async def test_pipeline():
    log.info("Starting CDP Pipeline Test...")
    
    # Initialize the new Collector & Pool
    collector = PassiveNetworkCollector()
    collector.start()
    pool = CDPPageRegistry(network_collector=collector)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Auto-register new pages just like in provider.py
        def on_page(new_page):
            asyncio.create_task(pool.register_page(new_page))
        context_page_listener = on_page
        context.on("page", context_page_listener)
        
        page = await context.new_page()
        # Manually register the first page
        await pool.register_page(page)
        
        log.info("Navigating to a test page to capture network events...")
        # Going to a site that triggers JSON API requests
        await page.goto("https://httpbin.org/json", wait_until="networkidle")
        await page.goto("https://httpbin.org/get", wait_until="networkidle")
        
        log.info("Shutting down collector and flushing events...")
        await collector.shutdown()
        
        await browser.close()
        
    log.info("Testing DuckDB Analytics over generated Parquet files...")
    
    # Initialize DuckDB client and query
    duckdb_client = DuckDBAnalytics()
    df = duckdb_client.query_entities()
    
    if df is not None and not df.is_empty():
        print("\n--- DuckDB Query Results (via Polars) ---")
        print(df)
        print("-----------------------------------------")
        log.info("Test passed! Parquet files were successfully written and read by DuckDB.")
    else:
        log.warning("No data found or query failed. Check the Parquet output directory.")

if __name__ == "__main__":
    asyncio.run(test_pipeline())
