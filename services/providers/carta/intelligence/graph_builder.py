import os
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..models.extraction import (
    CartaEntityGraph,
    GraphNode,
    GraphNodeProvenance,
    GraphEdge,
    RelationshipEvidence,
    RelationshipCandidate,
    GraphProvenance,
    DiscoveredEntity
)
from ..normalizers.response_normalizer import ResponseNormalizer
from ..normalizers.preprocessor import GraphPreprocessor
from .canonical_registry import CanonicalRegistry
from .identity_resolver import EntityIdentityResolver

log = logging.getLogger(__name__)


class EntityGraphBuilder:
    """
    Builds the structured, deterministic entity graph from raw extracted payloads,
    using the CanonicalRegistry to prevent duplicates and fragmented entities.
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
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.entity_manifest = {e.entity_id: e for e in entity_manifest}
        
        self.graph = CartaEntityGraph(
            graph_id=str(uuid.uuid4()),
            firm_id=firm_id,
            firm_name=firm_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            nodes={},
            edges=[],
        )
        self.registry = CanonicalRegistry(firm_id=firm_id)
        self.edge_registry = set()
        
        # Track SPV -> Fund links from raw extraction data
        self.spv_to_fund: dict[str, str] = {}

    def _add_edge(self, source_id: str, target_id: str, edge_type: str, evidence: RelationshipEvidence, metadata: dict = None):
        """Add an edge if it doesn't already exist."""
        edge_sig = f"{source_id}->{target_id}:{edge_type}"
        if edge_sig in self.edge_registry:
            return
        
        self.edge_registry.add(edge_sig)
        self.graph.edges.append(GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            evidence=evidence,
            metadata=metadata or {}
        ))

    def build(self) -> CartaEntityGraph:
        """Process all extracted JSON files to build the canonical graph."""
        if not self.extracted_dir.exists():
            log.warning(f"[GraphBuilder] Extracted dir does not exist: {self.extracted_dir}")
            return self.graph

        log.info(f"[GraphBuilder] Building Entity Graph from {len(self.entity_manifest)} known entities...")

        # 1. Base Org Node
        org_norm = ResponseNormalizer.normalize_entity(
            entity_id=f"org_{self.graph.firm_id}",
            entity_type="organization",
            name=self.graph.firm_name,
            payload={},
            category="base",
            source_url="base_manifest"
        )
        org_canon = self.registry.register(org_norm, source_artifact="base_manifest")
        
        self.graph.nodes[org_canon.canonical_id] = GraphNode(
            node_id=org_canon.canonical_id,
            node_type=org_canon.entity_type,
            name=org_canon.display_name,
            properties={"status": "discovered"},
            provenance=GraphNodeProvenance(
                source_artifacts=[org_canon.first_seen_artifact],
                source_endpoints=["base_manifest"],
                confidence=org_canon.confidence
            )
        )
        org_id = org_canon.canonical_id

        # 1.5 Seed registry from Entity Manifest (Guaranteed Nodes)
        for entity_ctx in self.entity_manifest.values():
            norm = ResponseNormalizer.normalize_entity(
                entity_id=entity_ctx.entity_id,
                entity_type=entity_ctx.entity_type,
                name=entity_ctx.name,
                payload={},
                category="base",
                source_url="entity_manifest"
            )
            canon = self.registry.register(norm, source_artifact="entity_manifest")
            if getattr(entity_ctx, "parent_fund_id", None):
                self.spv_to_fund[canon.canonical_id] = f"fund_{entity_ctx.parent_fund_id}"

        # 2. Process all extracted JSONs to enrich registry and build edges
        processed_files = 0
        raw_edges = []
        
        for root, _, files in os.walk(self.extracted_dir):
            for file in files:
                if not file.endswith(".json") or file == "_extraction_manifest.json":
                    continue
                    
                path = Path(root) / file
                artifact_name = str(path.name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                    if not isinstance(data, dict):
                        continue
                        
                    meta = data.get("_meta", {})
                    payload = data.get("data")
                    
                    if not payload:
                        continue
                        
                    entity_id = meta.get("entity_id")
                    if not entity_id:
                        continue
                        
                    category = meta.get("category", "unknown")
                    source_url = meta.get("source_url", "")
                    entity_type = meta.get("entity_type", "unknown")
                    entity_name = meta.get("entity_name", "unknown")
                    
                    # 3. Normalize Payload
                    payload = GraphPreprocessor.normalize_payload(payload)
                    
                    if isinstance(payload, list):
                        payload = {category: payload}
                    
                    normalized = ResponseNormalizer.normalize_entity(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        name=entity_name,
                        payload=payload,
                        category=category,
                        source_url=source_url
                    )
                    
                    # 4. Canonicalize
                    canon = self.registry.register(normalized, source_artifact=artifact_name)
                    
                    # Track SPV -> Fund links if present in payload
                    # (Assuming the payload might have a fund_id if it's an SPV)
                    if entity_type == "spv":
                        if isinstance(payload, dict):
                            fund_id = payload.get("fund_id") or payload.get("parent_fund_id")
                            if fund_id:
                                self.spv_to_fund[canon.canonical_id] = f"fund_{fund_id}"
                    
                    # 5. Extract Edges (Delay edge creation until nodes are fully canonicalized)
                    edges_data = ResponseNormalizer.extract_relationships(
                        source_entity_id=canon.canonical_id, # Use canonical ID
                        source_entity_type=entity_type,
                        payload=payload,
                        parent_org_pk=self.graph.firm_id
                    )
                    
                    for edge_data in edges_data:
                        raw_edges.append({
                            "source_id": edge_data.source if edge_data.source else canon.canonical_id,
                            "target_id": edge_data.target,
                            "target_type": edge_data.metadata.get("target_type", "unknown"),
                            "edge_type": edge_data.edge_type,
                            "payload_ref": edge_data.metadata.get("payload_ref"),
                            "source_artifact": artifact_name,
                            "source_endpoint": source_url,
                            "category": category,
                            "confidence": edge_data.confidence,
                            "evidence_sources": edge_data.evidence
                        })
                        
                    processed_files += 1
                    
                except Exception as e:
                    log.warning(f"[GraphBuilder] Failed to process {path.name}: {e}")

        # 6. Finalize Nodes
        for canon in self.registry.registry.values():
            self.graph.nodes[canon.canonical_id] = GraphNode(
                node_id=canon.canonical_id,
                node_type=canon.entity_type,
                name=canon.display_name,
                properties=canon.properties,
                provenance=GraphNodeProvenance(
                    source_artifacts=[canon.first_seen_artifact, canon.last_seen_artifact] if canon.first_seen_artifact != canon.last_seen_artifact else [canon.first_seen_artifact],
                    source_endpoints=[], # We would need to track all endpoints in the registry for perfection, but keeping it simple
                    confidence=canon.confidence
                )
            )
            
        # 7. Finalize Edges
        # Phase B: Create inferred hierarchy edges explicitly
        manifest_evidence = RelationshipEvidence(
            relationship_type="managed_by",
            source_artifact="entity_manifest",
            source_endpoint="discovery",
            evidence_sources=["manifest"],
            confidence=1.0
        )
        
        for canon in self.registry.registry.values():
            if canon.entity_type == "spv":
                fund_parent = self.spv_to_fund.get(canon.canonical_id)
                if fund_parent and fund_parent in self.graph.nodes:
                    # Fund -> SPV
                    self._add_edge(
                        source_id=fund_parent,
                        target_id=canon.canonical_id,
                        edge_type="managed_by",
                        evidence=RelationshipEvidence(
                            relationship_type="managed_by",
                            source_artifact="entity_manifest",
                            source_endpoint="discovery",
                            evidence_sources=["manifest"],
                            confidence=1.0
                        )
                    )
                else:
                    # Org -> SPV fallback
                    self._add_edge(
                        source_id=org_id,
                        target_id=canon.canonical_id,
                        edge_type="managed_by",
                        evidence=manifest_evidence
                    )
            elif canon.entity_type == "fund":
                # Org -> Fund
                self._add_edge(
                    source_id=org_id,
                    target_id=canon.canonical_id,
                    edge_type="manages",
                    evidence=RelationshipEvidence(
                        relationship_type="manages",
                        source_artifact="entity_manifest",
                        source_endpoint="discovery",
                        evidence_sources=["manifest"],
                        confidence=1.0
                    )
                )
            elif canon.entity_type in ("corporation", "investment"):
                # Org -> Corporation / Investment
                self._add_edge(
                    source_id=org_id,
                    target_id=canon.canonical_id,
                    edge_type="invested_in",
                    evidence=RelationshipEvidence(
                        relationship_type="invested_in",
                        source_artifact="entity_manifest",
                        source_endpoint="discovery",
                        evidence_sources=["manifest"],
                        confidence=1.0
                    )
                )

        # Process raw extracted edges
        for raw_edge in raw_edges:
            target_id = raw_edge["target_id"]
            
            # Check if we need to create a Valuation Node or missing Target Node
            if target_id not in self.graph.nodes:
                if raw_edge.get("target_type") == "valuation":
                    val_payload = raw_edge.get("payload_ref", {})
                    # Need to canonicalize the valuation too
                    val_norm = ResponseNormalizer.normalize_entity(
                        entity_id=target_id,
                        entity_type="valuation",
                        name=f"Valuation",
                        payload=val_payload,
                        category="valuations",
                        source_url=raw_edge["source_endpoint"]
                    )
                    val_canon = self.registry.register(val_norm, source_artifact=raw_edge["source_artifact"])
                    target_id = val_canon.canonical_id # Update target_id to canonical
                    
                    self.graph.nodes[target_id] = GraphNode(
                        node_id=target_id,
                        node_type="valuation",
                        name=f"Valuation",
                        properties=val_canon.properties,
                        provenance=GraphNodeProvenance(
                            source_artifacts=[val_canon.first_seen_artifact],
                            source_endpoints=[raw_edge["source_endpoint"]],
                            confidence=val_canon.confidence
                        )
                    )
                else:
                    # Generic placeholder for missing targets
                    self.graph.nodes[target_id] = GraphNode(
                        node_id=target_id,
                        node_type=raw_edge.get("target_type", "unknown"),
                        name="unknown",
                        properties={"status": "inferred"},
                        provenance=GraphNodeProvenance(
                            source_artifacts=[raw_edge["source_artifact"]],
                            source_endpoints=[raw_edge["source_endpoint"]],
                            confidence=0.5
                        )
                    )
                    
            evidence = RelationshipEvidence(
                relationship_type=raw_edge["edge_type"],
                source_artifact=raw_edge["source_artifact"],
                source_endpoint=raw_edge["source_endpoint"],
                evidence_sources=["replay_payload"],
                confidence=raw_edge.get("confidence", 0.95)
            )
            
            self._add_edge(
                source_id=raw_edge["source_id"],
                target_id=target_id,
                edge_type=raw_edge["edge_type"],
                evidence=evidence,
                metadata={"inferred_from": raw_edge["category"], "source_endpoint": raw_edge["source_endpoint"]}
            )

        # 7.5 Incorporate Exports
        exports_path = self.extracted_dir.parent / "export_inventory.json"
        self._incorporate_exports(exports_path)

        # 7.7 Resolve Identities
        resolver = EntityIdentityResolver(extracted_dir=self.extracted_dir, output_dir=self.output_dir)
        self.graph.nodes = resolver.resolve(self.graph.nodes)

        # 8. Save Graph
        self._save_graph()
        
        log.info(f"[GraphBuilder] Graph construction complete: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")
        return self.graph

    def _save_graph(self):
        """Persist the canonical graph to JSON."""
        graph_out = self.output_dir / "entity_graph.json"
        nodes_out = self.output_dir / "nodes.json"
        edges_out = self.output_dir / "edges.json"
        
        nodes_list = [
            {
                "id": n.node_id,
                "type": n.node_type,
                "name": n.name,
                "properties": n.properties,
                "provenance": {
                    "source_artifacts": n.provenance.source_artifacts,
                    "source_endpoints": n.provenance.source_endpoints,
                    "confidence": n.provenance.confidence
                }
            }
            for n in self.graph.nodes.values()
        ]
        
        edges_list = [
            {
                "source": e.source_id,
                "target": e.target_id,
                "type": e.edge_type,
                "evidence": {
                    "relationship_type": e.evidence.relationship_type if e.evidence else e.edge_type,
                    "source_artifact": e.evidence.source_artifact if e.evidence else "",
                    "source_endpoint": e.evidence.source_endpoint if e.evidence else "",
                    "evidence_sources": e.evidence.evidence_sources if e.evidence else [],
                    "confidence": e.evidence.confidence if e.evidence else 1.0,
                },
                "metadata": e.metadata
            }
            for e in self.graph.edges
        ]
        
        output_data = {
            "summary": {
                "total_nodes": len(self.graph.nodes),
                "total_edges": len(self.graph.edges)
            },
            "nodes": nodes_list,
            "edges": edges_list
        }
        
        with open(graph_out, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
            
        with open(nodes_out, "w", encoding="utf-8") as f:
            json.dump(nodes_list, f, indent=2)
            
        with open(edges_out, "w", encoding="utf-8") as f:
            json.dump(edges_list, f, indent=2)

    def _incorporate_exports(self, exports_path: Path):
        """Process export inventory and generate edges based on rows."""
        import json
        if not exports_path.exists():
            return
            
        with open(exports_path, "r", encoding="utf-8") as f:
            try:
                exports = json.load(f)
            except Exception as e:
                log.error(f"[GraphBuilder] Failed to load exports: {e}")
                return
                
        for exp in exports:
            source_id = exp.get("entity_id", "unknown")
            domain = exp.get("business_domain", "unknown")
            rows = exp.get("parsed_rows", [])
            
            for i, row in enumerate(rows):
                row_id = f"{domain}_record_{uuid.uuid4().hex[:8]}"
                
                self.graph.nodes[row_id] = GraphNode(
                    node_id=row_id,
                    node_type=domain,
                    name=row.get("name", row.get("id", f"{domain} {i+1}")),
                    properties=row,
                    provenance=GraphNodeProvenance(
                        source_artifacts=[exp.get("raw_file_path", "")],
                        source_endpoints=[exp.get("source_url", "")],
                        confidence=1.0
                    )
                )
                
                evidence = RelationshipEvidence(
                    relationship_type="has_record",
                    source_artifact=exp.get("raw_file_path", ""),
                    source_endpoint=exp.get("source_url", ""),
                    evidence_sources=[exp.get("raw_file_path", "")],
                    confidence=1.0
                )
                
                self._add_edge(
                    source_id=source_id,
                    target_id=row_id,
                    edge_type="has_record",
                    evidence=evidence,
                    metadata={"business_domain": domain}
                )

