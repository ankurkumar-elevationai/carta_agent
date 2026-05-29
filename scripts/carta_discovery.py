import asyncio
import logging
import os
import sys

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set environment variables before importing settings
os.environ["CARTA_MODE"] = "discovery"
os.environ["CARTA_ENABLE_HAR"] = "true"
os.environ["CARTA_ENABLE_NETWORK_DISCOVERY"] = "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

from services.providers.carta import CartaProvider, PlaywrightManager

async def run_discovery(company_name: str):
    """
    Triggers the CartaProvider in DISCOVERY mode.
    This will launch the persistent browser connection, log in,
    navigate to the company holdings, and collect network intelligence
    including GraphQL schemas, request classifications, and HAR files.
    """
    log.info(f"Starting Carta Discovery Run for '{company_name}'")
    
    # 1. Start singleton Playwright
    await PlaywrightManager.start()
    
    provider = CartaProvider()
    
    try:
        result = await provider.run(company_name=company_name, task_id="discovery_task_001")
        log.info(f"Discovery run complete. Result:\n{result}")
        log.info("Check 'output/carta/' for network logs and HAR.")
    except Exception as e:
        log.error(f"Discovery run failed: {e}", exc_info=True)
    finally:
        await PlaywrightManager.stop()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    # By default, use a test company string
    target_company = "Acme Corp"
    if len(sys.argv) > 1:
        target_company = sys.argv[1]
        
    asyncio.run(run_discovery(target_company))
