"""
Interaction Provenance Tracker (Phase 3).

Records WHY an API was triggered by tracking the UI interaction context
(e.g., TAB_CLICK, ROW_DRILLDOWN) and the resulting network endpoints.
This forms the behavioral intelligence layer for semantic replay and autonomous workflows.
"""

import logging
import time
from typing import Optional, List
from ..models.extraction import InteractionProvenance

log = logging.getLogger(__name__)


class InteractionProvenanceTracker:
    """
    Tracks the UI interaction context (provenance) of network events.
    Records WHY an API was triggered based on the user's/agent's UI actions.
    """

    def __init__(self):
        self._current_interaction_type: str = "PAGE_LOAD"
        self._current_ui_path: List[str] = []
        self._current_entity_context: Optional[str] = None
        self._history: List[InteractionProvenance] = []

        # Transient state for the current interaction
        self._current_endpoints: set = set()
        self._interaction_start_time: float = time.time()

    def begin_interaction(
        self,
        interaction_type: str,
        ui_path: List[str],
        entity_context: Optional[str] = None,
    ):
        """Mark the start of a new UI interaction."""
        # Commit previous interaction if it had endpoints
        self._commit_current()

        self._current_interaction_type = interaction_type
        self._current_ui_path = ui_path
        self._current_entity_context = entity_context
        self._current_endpoints = set()
        self._interaction_start_time = time.time()

        log.info(
            f"[InteractionTracker] Started {interaction_type} at {ui_path} "
            f"(Entity: {entity_context})"
        )

    def record_endpoint_triggered(self, url: str):
        """Record that a network endpoint was triggered during the current interaction."""
        # Clean URL (strip query params for cleaner tracking)
        clean_url = url.split("?")[0]
        self._current_endpoints.add(clean_url)

    def _commit_current(self):
        """Commit the current interaction to history."""
        if self._current_endpoints:
            prov = InteractionProvenance(
                interaction_type=self._current_interaction_type,
                ui_path=tuple(self._current_ui_path),
                triggered_endpoints=tuple(sorted(self._current_endpoints)),
                entity_context=self._current_entity_context,
                timestamp=self._interaction_start_time,
            )
            self._history.append(prov)
            log.debug(
                f"[InteractionTracker] Committed {self._current_interaction_type} "
                f"with {len(self._current_endpoints)} endpoints"
            )
            self._current_endpoints.clear()

    @property
    def history(self) -> List[InteractionProvenance]:
        self._commit_current()
        return self._history
