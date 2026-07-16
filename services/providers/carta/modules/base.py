from abc import ABC, abstractmethod
from typing import Set, Dict, Any

class ExtractionModule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the module (e.g., 'valuation')."""
        pass

    @property
    @abstractmethod
    def dependencies(self) -> Set[str]:
        """Set of module names that must execute before this module."""
        pass

    @property
    @abstractmethod
    def ttl_seconds(self) -> int:
        """Freshness TTL for the module's cache in seconds."""
        pass

    @abstractmethod
    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the specific API extraction routine.
        Uses dependency_data to access results of prerequisite modules.
        """
        pass
