import logging
from typing import Any

log = logging.getLogger(__name__)

class GraphPreprocessor:
    """
    Priority 0: Sanitizes and unwraps raw payloads before they enter the normalizer or graph builder.
    Eliminates 'list' object has no attribute 'get' and deeply nested array edge cases.
    """
    
    @staticmethod
    def normalize_payload(payload: Any) -> Any:
        """
        Recursively unwraps common Carta pagination and GraphQL wrappers.
        Handles: dict, list, results[], items[], data[], records[], edges[], nodes[]
        """
        if isinstance(payload, list):
            return [GraphPreprocessor.normalize_payload(item) for item in payload]
            
        if isinstance(payload, dict):
            # Special case for GraphQL node unwrapping (e.g. {"node": {...}})
            if "node" in payload and len(payload) == 1:
                return GraphPreprocessor.normalize_payload(payload["node"])

            # Check for common collection wrappers
            wrapper_keys = ["results", "items", "records", "edges", "nodes", "data"]
            for key in wrapper_keys:
                if key in payload and isinstance(payload[key], (list, dict)):
                    # If found, extract the wrapped content and normalize it recursively
                    return GraphPreprocessor.normalize_payload(payload[key])
                    
            # If no wrapper was found, return the dict as-is
            return payload
            
        return payload
