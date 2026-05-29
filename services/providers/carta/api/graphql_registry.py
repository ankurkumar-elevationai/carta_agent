import json
import logging
from typing import Dict, Any, List

log = logging.getLogger(__name__)

class GraphQLRegistry:
    """
    Tracks GraphQL operations, request counts, variable keys seen,
    and response structures to build an API intelligence catalog.
    """
    def __init__(self):
        self.catalog: Dict[str, Dict[str, Any]] = {}

    def extract_operation_details(self, payload_text: str) -> dict:
        """Parse raw payload text to extract operationName and variables."""
        if not payload_text:
            return {}
        try:
            data = json.loads(payload_text)
            if isinstance(data, list):
                # Batch request
                data = data[0] if data else {}
                
            return {
                "operationName": data.get("operationName", "UnknownOperation"),
                "variables": data.get("variables", {}),
                "query": data.get("query", "")
            }
        except Exception:
            return {}

    def track_request(self, operation_name: str, variables: dict):
        if not operation_name:
            return
            
        if operation_name not in self.catalog:
            self.catalog[operation_name] = {
                "operation_name": operation_name,
                "request_count": 0,
                "variables_seen": set(),
                "response_root_keys": set(),
                "pagination_detected": False
            }
            
        self.catalog[operation_name]["request_count"] += 1
        
        # Track seen variable keys
        if variables:
            self.catalog[operation_name]["variables_seen"].update(variables.keys())

    def track_response(self, operation_name: str, response_data: dict):
        if not operation_name or not response_data:
            return
            
        if operation_name in self.catalog:
            data_dict = response_data.get("data", {})
            if isinstance(data_dict, dict):
                self.catalog[operation_name]["response_root_keys"].update(data_dict.keys())
                
                # Simple pagination detection heuristic
                for key, val in data_dict.items():
                    if isinstance(val, dict):
                        if "pageInfo" in val or "edges" in val or "cursor" in val:
                            self.catalog[operation_name]["pagination_detected"] = True

    def get_catalog_summary(self) -> Dict[str, Any]:
        """Convert sets to lists for JSON serialization."""
        summary = {}
        for op, data in self.catalog.items():
            summary[op] = {
                "operation_name": data["operation_name"],
                "request_count": data["request_count"],
                "variables_seen": list(data["variables_seen"]),
                "response_root_keys": list(data["response_root_keys"]),
                "pagination_detected": data["pagination_detected"]
            }
        return summary
