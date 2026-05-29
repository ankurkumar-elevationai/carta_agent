import logging
import os
from ..utils.settings import settings, CartaRuntimeMode
from ..api.interceptor import NetworkInterceptor

log = logging.getLogger(__name__)

class NetworkMonitor:
    """
    High-level orchestrator for network events.
    Attaches the API Interceptor and manages HAR capture dynamically
    based on the configured RuntimeMode.
    """
    def __init__(self, context):
        self.context = context
        self.interceptor = None
        self._har_started = False
        self._attached = False

    async def start(self):
        if settings.mode == CartaRuntimeMode.DISCOVERY and settings.enable_network_discovery:
            log.info("[NetworkMonitor] Discovery Mode active. Attaching interceptor to context.")
            
            output_dir = os.path.dirname(settings.har_path) if settings.har_path else "output/carta"
            self.interceptor = NetworkInterceptor(
                output_dir=output_dir,
                max_capture_bytes=settings.max_capture_bytes
            )
            
            self.context.on("request", self.interceptor.handle_request)
            self.context.on("response", self.interceptor.handle_response)
            self._attached = True
            
            if settings.enable_har:
                log.info(f"[NetworkMonitor] Enabling HAR capture (target: {settings.har_path})")
                try:
                    await self.context.tracing.start(screenshots=False, snapshots=False)
                    self._har_started = True
                except Exception as e:
                    log.warning(f"[NetworkMonitor] Failed to start HAR tracing: {e}")

    async def stop(self):
        if self.interceptor:
            # Save the metadata catalog and request map
            self.interceptor._save_request_map()
            
            try:
                catalog_path = os.path.join(self.interceptor.output_dir, "graphql_catalog.json")
                import json
                with open(catalog_path, "w", encoding="utf-8") as f:
                    json.dump(self.interceptor.graphql_registry.get_catalog_summary(), f, indent=2)
                log.info(f"[NetworkMonitor] Saved GraphQL intelligence catalog to {catalog_path}")
            except Exception as e:
                log.error(f"[NetworkMonitor] Failed to save GraphQL catalog: {e}")
                
        if self._har_started and settings.har_path:
            log.info(f"[NetworkMonitor] Saving HAR file to {settings.har_path}")
            try:
                os.makedirs(os.path.dirname(settings.har_path), exist_ok=True)
                await self.context.tracing.stop(path=settings.har_path)
            except Exception as e:
                log.error(f"[NetworkMonitor] Failed to save HAR: {e}")
                
        if self._attached:
            try:
                self.context.remove_listener("request", self.interceptor.handle_request)
                self.context.remove_listener("response", self.interceptor.handle_response)
            except Exception:
                pass
            self._attached = False
