import logging
import json
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

class SchemaRegistry:
    """
    Manages schema evolution, drift tracking, and compatibility history.
    """
    def __init__(self, registry_dir: Path):
        self.registry_dir = registry_dir
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = self.registry_dir / "schema_registry.json"
        self._schemas = self._load()

    def _load(self) -> dict:
        if self._registry_file.exists():
            try:
                return json.loads(self._registry_file.read_text())
            except Exception as e:
                log.error(f"Failed to load schema registry: {e}")
        return {}

    def _save(self):
        self._registry_file.write_text(json.dumps(self._schemas, indent=2))

    def register_schema(self, structural_fingerprint: str, top_level_keys: tuple[str, ...], semantic_cluster_id: str) -> int:
        """
        Registers a schema, tracking its version and linkage to semantic clusters.
        Returns the version integer.
        """
        if structural_fingerprint not in self._schemas:
            self._schemas[structural_fingerprint] = {
                "version": len(self._schemas) + 1,
                "first_seen": None,
                "top_level_keys": list(top_level_keys),
                "semantic_clusters": []
            }
        
        if semantic_cluster_id not in self._schemas[structural_fingerprint]["semantic_clusters"]:
            self._schemas[structural_fingerprint]["semantic_clusters"].append(semantic_cluster_id)
            self._save()
            
        return self._schemas[structural_fingerprint]["version"]
