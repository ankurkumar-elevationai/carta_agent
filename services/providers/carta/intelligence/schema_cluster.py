import logging
from typing import Optional
from hashlib import sha256
from ..models.extraction import TrafficClass, CapabilityTag, TraversalContext

log = logging.getLogger(__name__)

class SchemaClusterEngine:
    """
    Decoupled clustering engine for Structural and Semantic schema inference.
    """
    def __init__(self):
        self._structural_clusters = {}
        self._semantic_clusters = {}

    def cluster_response(self, 
                         schema_fingerprint: str, 
                         capability_tags: tuple[CapabilityTag, ...], 
                         traversal_context: Optional[TraversalContext], 
                         graphql_operation: Optional[str], 
                         traffic_class: TrafficClass) -> str:
        """
        Calculates a semantic cluster ID based on business capability.
        Structural clustering is handled via the strict schema_fingerprint.
        """
        # Semantic ID combines capabilities and workflow topology
        cap_str = ",".join(sorted([c.value for c in capability_tags]))
        
        topology = ""
        if traversal_context:
            topology = f"{traversal_context.navigation_mode}:{traversal_context.interaction_type}"
            
        semantic_components = f"{cap_str}|{graphql_operation or 'REST'}|{topology}|{traffic_class.value}"
        semantic_cluster_id = f"sem_{sha256(semantic_components.encode()).hexdigest()[:12]}"
        
        return semantic_cluster_id
