import logging
from typing import Dict, List, Optional
from ..modules.base import ExtractionModule

log = logging.getLogger(__name__)

class ModuleRegistry:
    def __init__(self):
        self._modules: Dict[str, ExtractionModule] = {}

    def register(self, module: ExtractionModule) -> None:
        if module.name in self._modules:
            log.warning(f"[Registry] Overwriting already registered module: {module.name}")
        self._modules[module.name] = module
        log.info(f"[Registry] Registered module: {module.name}")

    def get(self, name: str) -> ExtractionModule:
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not found in registry.")
        return self._modules[name]

    def get_all(self) -> List[ExtractionModule]:
        return list(self._modules.values())

    @property
    def modules_dict(self) -> Dict[str, ExtractionModule]:
        return self._modules
