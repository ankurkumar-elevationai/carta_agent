"""
Entity Graph Builder (Phase 6).

Consumes the extracted JSON payloads and DiscoveredEntity manifest,
normalizes the raw data, and builds the canonical CartaEntityGraph.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..models.extraction import (
    CartaEntityGraph,
    GraphNode,
    GraphEdge,
    GraphProvenance,
    DiscoveredEntity
)
from ..normalizers.response_normalizer import ResponseNormalizer

log = logging.getLogger(__name__)


class EntityGraphBuilder:
    """
    Builds the structured, deterministic entity graph from raw extracted payloads.
    """

    def __init__(
        self,
        extracted_dir: Path,
        output_dir: Path,
        entity_manifest: list[DiscoveredEntity],
        firm_id: int = 0,
        firm_name: str = "unknown",
    ):
        self.extracted_dir = Path(extracted_dir)
        self.output_dir = Path(output_dir)
        self.entity_manifest = {e.entity_id: e for e in entity_manifest}
        self.graph = CartaEntityGraph(
            graph_id=str(uuid.uuid4()),
            firm_id=firm_id,
            firm_name=firm_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            nodes={},
            edges=[],
        )

    def build(self) -> CartaEntityGraph:
        """Process all extracted JSON files to build the canonical graph."""
        if not self.extracted_dir.exists():
            log.warning(f"[GraphBuilder] Extracted dir does not exist: {self.extracted_dir}")
            return self.graph

        log.info(f"[GraphBuilder] Building Entity Graph from {len(self.entity_manifest)} known entities...")

        # 1. Initialize nodes for all discovered entities
        for entity_id, entity in self.entity_manifest.items():
            node = GraphNode(
                entity_id=entity.entity_id,
                entity_type=entity.entity_type,
                name=entity.name,
                status="discovered",
                metadata={"detail_url": entity.detail_url},
                provenance=GraphProvenance(
                    source_urls=(),
                    extraction_timestamp="",
                    confidence=1.0,
                    schema_cluster_ids=()
                )
            )
            self.graph.nodes[entity_id] = node

        # 2. Process all extracted JSONs to enrich nodes and build edges
        processed_files = 0
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
                        
                    entity_id = meta.get("entity_id")
                    if not entity_id:
                        continue
                        
                    category = meta.get("category", "unknown")
                    source_url = meta.get("source_url", "")
                    
                    # Ensure node exists (might be discovered dynamically during extraction)
                    if entity_id not in self.graph.nodes:
                        self.graph.nodes[entity_id] = GraphNode(
                            entity_id=entity_id,
                            entity_type=meta.get("entity_type", "unknown"),
                            name=meta.get("entity_name", "unknown"),
                            status="extracted",
                            provenance=GraphProvenance(
                                source_urls=(),
                                extraction_timestamp="",
                                confidence=1.0,
                                schema_cluster_ids=()
                            )
                        )
                        
                    # 3. Normalize Payload
                    canonical = ResponseNormalizer.normalize_entity(
                        entity_id=entity_id,
                        entity_type=self.graph.nodes[entity_id].entity_type,
                        name=self.graph.nodes[entity_id].name,
                        payload=payload,
                        category=category
                    )
                    
                    # 4. Enrich Node
                    node = self.graph.nodes[entity_id]
                    if canonical["status"] != "unknown":
                        node.status = canonical["status"]
                        
                    # Merge metadata
                    for k, v in canonical["metadata"].items():
                        node.metadata[k] = v
                        
                    # Update provenance
                    new_urls = list(node.provenance.source_urls)
                    if source_url not in new_urls:
                        new_urls.append(source_url)
                    node.provenance.source_urls = tuple(new_urls)
                    
                    # 5. Extract Edges
                    edges = ResponseNormalizer.extract_relationships(entity_id, payload)
                    for edge_data in edges:
                        edge = GraphEdge(
                            source_id=entity_id,
                            target_id=edge_data["target_id"],
                            edge_type=edge_data["edge_type"],
                            properties={"inferred_from": category}
                        )
                        self.graph.edges.append(edge)
                        
                    processed_files += 1
                    
                except Exception as e:
                    log.warning(f"[GraphBuilder] Failed to process {path.name}: {e}")

        # 3. Save Graph
        self._save_graph()
        
        log.info(f"[GraphBuilder] Graph construction complete: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")
        return self.graph

    def _save_graph(self):
        """Persist the canonical graph to JSON."""
        out_path = self.output_dir / "entity_graph.json"
        
        output_data = {
            "summary": {
                "total_nodes": len(self.graph.nodes),
                "total_edges": len(self.graph.edges)
            },
            "nodes": [
                {
                    "id": n.entity_id,
                    "type": n.entity_type,
                    "name": n.name,
                    "status": n.status,
                    "metadata": n.metadata,
                    "provenance": {
                        "source_urls": list(n.provenance.source_urls),
                        "sources": len(n.provenance.source_urls),
                        "confidence": n.provenance.confidence
                    }
                }
                for n in self.graph.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type,
                    "properties": e.properties
                }
                for e in self.graph.edges
            ]
        }
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
