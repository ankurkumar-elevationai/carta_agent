from services.providers.carta.intelligence.intelligence_extractor import IntelligenceExtractor
from services.providers.carta.models.extraction import DiscoveredEntity, InteractionProvenance
from unittest.mock import MagicMock

class MockInteractionTracker:
    def __init__(self):
        self.history = [
            InteractionProvenance(
                interaction_type="PAGE_LOAD",
                ui_path=("Tasks", "View Details"),
                triggered_endpoints=("https://api.carta.team/tasks/123",),
                entity_context="task_123"
            ),
            InteractionProvenance(
                interaction_type="TAB_CLICK",
                ui_path=("Portfolio", "Acme Corp", "Holdings"),
                triggered_endpoints=("https://api.carta.team/investors/holdings/1",),
                entity_context="company_777"
            )
        ]

class MockApiCollector:
    def __init__(self):
        self.interaction_tracker = MockInteractionTracker()

entities = [
    DiscoveredEntity(entity_id="task_123", entity_type="task", name="Task 1", parent_org_pk=1),
    DiscoveredEntity(entity_id="company_777", entity_type="company", name="Acme Corp", parent_org_pk=1)
]

extractor = IntelligenceExtractor(
    classifier=MagicMock(),
    replay_client=MagicMock(),
    output_dir="test",
    entity_manifest=entities,
    api_collector=MockApiCollector()
)

# Test 1: Should resolve using provenance context
entity1 = extractor._find_entity_for_url("https://api.carta.team/investors/holdings/1?limit=10")
print(f"Test 1 (Provenance): {entity1.name if entity1 else 'None'} (Expected: Acme Corp)")

# Test 2: Should resolve using URL string matching fallback
entity2 = extractor._find_entity_for_url("https://api.carta.team/task_123/")
print(f"Test 2 (Fallback): {entity2.name if entity2 else 'None'} (Expected: Task 1)")
