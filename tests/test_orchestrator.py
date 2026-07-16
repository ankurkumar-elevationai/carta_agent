import asyncio
import os
import shutil
import tempfile
import time
from typing import Dict, Any, Set
import pytest

from services.providers.carta.modules.base import ExtractionModule
from services.providers.carta.orchestrator.cache import CacheManager
from services.providers.carta.orchestrator.registry import ModuleRegistry
from services.providers.carta.orchestrator.resolver import DependencyResolver
from services.providers.carta.orchestrator.orchestrator import ExtractionOrchestrator

# Mock modules for testing
class MockInvestmentModule(ExtractionModule):
    @property
    def name(self) -> str:
        return "investment"

    @property
    def dependencies(self) -> Set[str]:
        return set()

    @property
    def ttl_seconds(self) -> int:
        return 2  # Short TTL for testing expiration

    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"data": "mock_investment_data"}

class MockValuationModule(ExtractionModule):
    @property
    def name(self) -> str:
        return "valuation"

    @property
    def dependencies(self) -> Set[str]:
        return {"investment"}

    @property
    def ttl_seconds(self) -> int:
        return 10

    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        inv_data = dependency_data.get("investment", {}).get("data")
        return {"data": f"mock_valuation_data_based_on_{inv_data}"}


@pytest.mark.asyncio
async def test_registry_and_resolver():
    registry = ModuleRegistry()
    inv_mod = MockInvestmentModule()
    val_mod = MockValuationModule()
    
    registry.register(inv_mod)
    registry.register(val_mod)
    
    assert registry.get("investment") == inv_mod
    assert registry.get("valuation") == val_mod
    
    # Test topological sorting
    order = DependencyResolver.resolve_order("valuation", registry.modules_dict)
    assert len(order) == 2
    assert order[0].name == "investment"
    assert order[1].name == "valuation"


@pytest.mark.asyncio
async def test_cache_manager():
    temp_dir = tempfile.mkdtemp()
    try:
        cache = CacheManager(temp_dir)
        data = {"hello": "world"}
        
        # Fresh write
        cache.set("test_module", data)
        
        # Test cache hit
        cached = cache.get("test_module", ttl_seconds=5)
        assert cached == data
        
        # Test cache expiry
        time.sleep(2.1)
        cached_expired = cache.get("test_module", ttl_seconds=2)
        assert cached_expired is None
    finally:
        shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_orchestrator_execution():
    temp_dir = tempfile.mkdtemp()
    try:
        registry = ModuleRegistry()
        inv_mod = MockInvestmentModule()
        val_mod = MockValuationModule()
        registry.register(inv_mod)
        registry.register(val_mod)
        
        cache = CacheManager(temp_dir)
        orchestrator = ExtractionOrchestrator(registry, cache)
        
        # Context is dict with dependencies
        context = {"direct_fetch": None, "firm_id": 123}
        
        # Run orchestrator
        val_data = await orchestrator.run_module("valuation", context)
        assert val_data == {"data": "mock_valuation_data_based_on_mock_investment_data"}
        
        # Verify it was cached
        assert cache.get("valuation_123", ttl_seconds=10) == val_data
        assert cache.get("investment_123", ttl_seconds=10) == {"data": "mock_investment_data"}
    finally:
        shutil.rmtree(temp_dir)
