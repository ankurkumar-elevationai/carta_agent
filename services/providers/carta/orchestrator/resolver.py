import logging
from typing import List, Dict, Set
from ..modules.base import ExtractionModule

log = logging.getLogger(__name__)

class DependencyResolver:
    @staticmethod
    def resolve_order(target_name: str, registry_modules: Dict[str, ExtractionModule]) -> List[ExtractionModule]:
        """
        Determines the topological sort of dependencies needed to build the target module.
        Raises ValueError if a cycle or missing dependency is found.
        """
        if target_name not in registry_modules:
            raise ValueError(f"Target module '{target_name}' is not registered.")
        
        # Build subgraph of reachable modules from target_name
        visited: Set[str] = set()
        path: Set[str] = set()
        order: List[ExtractionModule] = []

        def dfs(name: str):
            if name in path:
                raise ValueError(f"Circular dependency detected involving module '{name}'")
            if name in visited:
                return
            
            if name not in registry_modules:
                raise ValueError(f"Module '{name}' requested as dependency, but is not registered.")
            
            path.add(name)
            module = registry_modules[name]
            # Recursively resolve dependencies first
            for dep in sorted(module.dependencies):
                dfs(dep)
            
            path.remove(name)
            visited.add(name)
            order.append(module)

        dfs(target_name)
        log.debug(f"[Resolver] Resolved execution order for '{target_name}': {[m.name for m in order]}")
        return order
