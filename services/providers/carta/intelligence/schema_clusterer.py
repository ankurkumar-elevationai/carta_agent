"""
Semantic Clustering Engine (Phase 5).

Groups extracted JSON payloads by structural and semantic similarity to
identify schema families and detect drift. This runs over the extracted/
directory after Phase 4 completes.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Set
from hashlib import sha256
import msgspec

from ..models.extraction import EndpointCategory

log = logging.getLogger(__name__)


class SchemaCluster(msgspec.Struct, kw_only=True):
    """A group of API responses that share the same structural schema."""
    cluster_id: str
    representative_schema: dict
    member_count: int
    member_urls: tuple[str, ...]
    category: str
    drift_detected: bool = False


class SchemaClusterer:
    """
    Reads all extracted JSON from Phase 4 and groups them into schema clusters.
    Computes structural fingerprints based on key paths and value types.
    """

    def __init__(self, extracted_dir: Path, output_dir: Path):
        self.extracted_dir = Path(extracted_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._clusters: Dict[str, SchemaCluster] = {}

    def cluster(self) -> List[SchemaCluster]:
        """Process all extracted JSON files and group them into clusters."""
        if not self.extracted_dir.exists():
            log.warning(f"[SchemaClusterer] Extracted dir does not exist: {self.extracted_dir}")
            return []

        log.info(f"[SchemaClusterer] Building schema clusters from {self.extracted_dir}...")
        
        # Maps fingerprint -> list of file paths
        fingerprint_groups: Dict[str, list] = {}
        # Maps fingerprint -> representative canonical schema
        fingerprint_schemas: Dict[str, dict] = {}
        # Maps fingerprint -> list of source URLs
        fingerprint_urls: Dict[str, list] = {}
        # Maps fingerprint -> category
        fingerprint_category: Dict[str, str] = {}

        # 1. Parse all extracted JSONs
        for root, _, files in os.walk(self.extracted_dir):
            for file in files:
                if not file.endswith(".json") or file == "_extraction_manifest.json":
                    continue
                    
                path = Path(root) / file
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                    meta = data.get("_meta", {})
                    payload = data.get("data")
                    
                    if not payload:
                        continue
                        
                    category = meta.get("category", "unknown")
                    source_url = meta.get("source_url", "unknown")
                    
                    # 2. Extract structural type schema
                    canonical_schema = self._extract_type_schema(payload)
                    schema_str = json.dumps(canonical_schema, sort_keys=True)
                    fingerprint = sha256(schema_str.encode()).hexdigest()[:16]
                    
                    fingerprint_groups.setdefault(fingerprint, []).append(path)
                    fingerprint_schemas[fingerprint] = canonical_schema
                    fingerprint_urls.setdefault(fingerprint, []).append(source_url)
                    fingerprint_category[fingerprint] = category
                    
                except Exception as e:
                    log.warning(f"[SchemaClusterer] Failed to process {path.name}: {e}")
                    
        # 3. Build Cluster objects
        clusters = []
        for fingerprint, paths in fingerprint_groups.items():
            urls = fingerprint_urls[fingerprint]
            
            cluster = SchemaCluster(
                cluster_id=f"schema_{fingerprint}",
                representative_schema=fingerprint_schemas[fingerprint],
                member_count=len(paths),
                member_urls=tuple(set(urls)),
                category=fingerprint_category[fingerprint],
            )
            clusters.append(cluster)
            self._clusters[cluster.cluster_id] = cluster
            
        # 4. Save results
        self._save_clusters(clusters)
        
        log.info(f"[SchemaClusterer] Clustered {sum(len(v) for v in fingerprint_groups.values())} files into {len(clusters)} distinct schema families.")
        return clusters

    def _save_clusters(self, clusters: List[SchemaCluster]):
        """Persist the schema clusters to a JSON file."""
        out_path = self.output_dir / "schema_clusters.json"
        
        output_data = {
            "summary": {
                "total_clusters": len(clusters),
                "total_members": sum(c.member_count for c in clusters)
            },
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "category": c.category,
                    "member_count": c.member_count,
                    "member_urls": c.member_urls,
                    "schema": c.representative_schema,
                }
                for c in clusters
            ]
        }
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

    def _extract_type_schema(self, obj) -> any:
        """Recursively extracts the structural type schema from a JSON payload."""
        if isinstance(obj, dict):
            # Sort keys canonically, ignoring highly volatile or id fields for pure structure
            return {
                k: self._extract_type_schema(v) 
                for k, v in sorted(obj.items()) 
                if k not in ['id', 'uuid', 'timestamp', 'created_at', 'updated_at']
            }
        elif isinstance(obj, list):
            if len(obj) > 0:
                # Assume homogenous list, just take the shape of the first item
                return [self._extract_type_schema(obj[0])]
            return []
        elif obj is None:
            return "null"
        elif isinstance(obj, bool):
            return "bool"
        elif isinstance(obj, int):
            return "int"
        elif isinstance(obj, float):
            return "float"
        else:
            return "string"
