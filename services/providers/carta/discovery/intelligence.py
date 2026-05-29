import hashlib
import json
from typing import Any, Dict

class SchemaInferenceEngine:
    """
    Infers structural schemas, enums, array shapes, pagination fields, and computes hashes.
    """

    @staticmethod
    def infer(payload: Any) -> Dict[str, Any]:
        """Returns a structural dictionary abstracting away the values."""
        
        def _walk(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _walk(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                if len(obj) > 0:
                    # Assume homogenous array based on first element
                    return [_walk(obj[0])]
                return []
            elif isinstance(obj, str):
                return "string"
            elif isinstance(obj, bool):
                return "boolean"
            elif isinstance(obj, int):
                return "integer"
            elif isinstance(obj, float):
                return "float"
            elif obj is None:
                return "null"
            return "unknown"

        structure = _walk(payload)
        
        # Detect pagination fields
        pagination_fields = []
        if isinstance(payload, dict):
            keys = set(payload.keys())
            if {"next", "previous", "cursor", "page", "total"} & keys:
                pagination_fields = list({"next", "previous", "cursor", "page", "total"} & keys)

        return {
            "structure": structure,
            "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else [],
            "pagination_fields": pagination_fields,
            "is_array": isinstance(payload, list)
        }

    @staticmethod
    def compute_hash(structure: Dict[str, Any]) -> str:
        """Computes a deterministic hash of the structural representation."""
        canonical_json = json.dumps(structure, sort_keys=True)
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

class EndpointRegistry:
    """
    Coordinates registering endpoints, inferring schemas, and checking DB existence.
    """
    def __init__(self, route_repo, schema_repo):
        self.route_repo = route_repo
        self.schema_repo = schema_repo
        self.schema_engine = SchemaInferenceEngine()

    async def register(self, endpoint: str, method: str, service: str, capability_type: str, depth: int, payload: Any, parent_url: str = None):
        """Registers a route and its inferred schema if it doesn't exist."""
        # Check if route already exists
        route = await self.route_repo.get_by_endpoint(endpoint)
        
        if not route:
            # Create route
            route = await self.route_repo.create(
                endpoint=endpoint,
                method=method,
                service=service,
                capability_type=capability_type,
                depth=depth,
                parent_url=parent_url
            )
            
            # Infer and save schema
            if payload:
                inferred = self.schema_engine.infer(payload)
                schema_hash = self.schema_engine.compute_hash(inferred["structure"])
                
                await self.schema_repo.create(
                    route_id=route.id,
                    schema_hash=schema_hash,
                    structure=inferred
                )
                
                # Update route with schema hash
                await self.route_repo.update_schema_hash(route.id, schema_hash)
                
        return route
