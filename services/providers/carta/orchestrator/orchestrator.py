import logging
import time
from typing import Dict, Any, List, Optional
from .registry import ModuleRegistry
from .resolver import DependencyResolver
from .cache import CacheManager
from ..modules.base import ExtractionModule

log = logging.getLogger(__name__)

class ExtractionOrchestrator:
    def __init__(self, registry: ModuleRegistry, cache: CacheManager):
        self.registry = registry
        self.cache = cache

    async def run_module(self, name: str, context: Any, force_refresh: bool = False) -> Any:
        """
        Runs the module named `name` after satisfying all of its dependencies.
        Uses cached values for dependencies and target if they are fresh (and force_refresh is False).
        """
        # Resolve all dependencies topologically
        modules_to_run = DependencyResolver.resolve_order(name, self.registry.modules_dict)
        
        dependency_results: Dict[str, Any] = {}
        
        # Resolve entity-specific name suffix if available in context
        suffix = ""
        if isinstance(context, dict):
            firm_id = context.get("firm_id")
            entity_id = context.get("entity_id")
            if firm_id:
                suffix += f"_{firm_id}"
                if entity_id:
                    suffix += f"_{entity_id}"
        elif hasattr(context, "firm_id"):
            firm_id = getattr(context, "firm_id")
            entity_id = getattr(context, "entity_id", None)
            if firm_id:
                suffix += f"_{firm_id}"
                if entity_id:
                    suffix += f"_{entity_id}"

        for module in modules_to_run:
            # Check cache unless we are forcing refresh
            should_skip_cache = force_refresh
            
            cache_key = f"{module.name}{suffix}"
            cached_data = None
            if not should_skip_cache:
                cached_data = self.cache.get(cache_key, module.ttl_seconds)
            
            if cached_data is not None:
                dependency_results[module.name] = cached_data
                log.info(f"[Orchestrator] Using cached data for module '{module.name}' (key: '{cache_key}')")
            else:
                log.info(f"[Orchestrator] Cache miss/stale for '{module.name}' (key: '{cache_key}'). Executing extraction...")
                start_time = time.monotonic()
                try:
                    # Execute module extraction
                    extracted_data = await module.extract(context, dependency_results)
                    # Cache the result
                    self.cache.set(
                        name=cache_key,
                        data=extracted_data,
                        version="1.0",
                        metadata={"execution_time_ms": int((time.monotonic() - start_time) * 1000)}
                    )
                    dependency_results[module.name] = extracted_data
                except Exception as e:
                    log.error(f"[Orchestrator] Execution failed for module '{module.name}': {e}", exc_info=True)
                    # Attempt to fall back to stale cache if available
                    stale_data = self.cache.get(cache_key, ttl_seconds=999999999) # Infinite TTL fallback
                    if stale_data is not None:
                        log.warning(f"[Orchestrator] Falling back to stale cache for module '{module.name}'")
                        dependency_results[module.name] = stale_data
                    else:
                        raise e
                        
        return dependency_results[name]

    async def sync_all(self, context: Any) -> Dict[str, Any]:
        """
        Nightly synchronization job: refreshes all registered modules sequentially in topological order.
        """
        log.info("[Orchestrator] Starting nightly synchronization job for all modules...")
        sync_results: Dict[str, Any] = {}
        
        # Get all registered modules
        all_modules = self.registry.get_all()
        
        # We need to execute them in a valid topological order overall.
        # We can construct a combined topological sort of all modules.
        # Let's build a dummy target that depends on all modules to get a global topological sort.
        visited: Set[str] = set()
        global_order: List[ExtractionModule] = []
        
        def dfs(module: ExtractionModule):
            if module.name in visited:
                return
            for dep_name in sorted(module.dependencies):
                dfs(self.registry.get(dep_name))
            visited.add(module.name)
            global_order.append(module)
            
        for m in sorted(all_modules, key=lambda x: x.name):
            dfs(m)
            
        log.info(f"[Orchestrator] Global execution order for sync: {[m.name for m in global_order]}")
        
        dependency_results: Dict[str, Any] = {}
        for module in global_order:
            log.info(f"[Orchestrator][Sync] Refreshing module '{module.name}'...")
            start_time = time.monotonic()
            try:
                extracted_data = await module.extract(context, dependency_results)
                self.cache.set(
                    name=module.name,
                    data=extracted_data,
                    version="1.0",
                    metadata={"sync_run": True, "execution_time_ms": int((time.monotonic() - start_time) * 1000)}
                )
                dependency_results[module.name] = extracted_data
                sync_results[module.name] = "success"
            except Exception as e:
                log.error(f"[Orchestrator][Sync] Synchronization failed for module '{module.name}': {e}")
                sync_results[module.name] = f"failed: {str(e)}"
                
        return sync_results
