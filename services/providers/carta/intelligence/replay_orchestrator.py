"""
Replay Orchestrator (Phase 7).

Leverages the canonical Entity Graph and its provenance metadata to
execute targeted, browser-less data extraction. Allows for rapid
re-extraction of specific entities (e.g., updating a valuation)
without running a full SPA traversal.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from ..api.replay_client import CartaReplayClient, ReplayTarget, ReplayScenario
from ..models.extraction import CartaEntityGraph, GraphNode

log = logging.getLogger(__name__)


class ReplayOrchestrator:
    """
    Executes targeted data extraction using Graph Provenance.
    Bypasses the UI and network collector entirely.
    """

    def __init__(self, replay_client: CartaReplayClient, graph_path: Path, output_dir: Path):
        self.replay_client = replay_client
        self.graph_path = Path(graph_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.graph: Optional[CartaEntityGraph] = None

    def load_graph(self) -> bool:
        """Load the entity graph from disk."""
        if not self.graph_path.exists():
            log.error(f"[ReplayOrchestrator] Graph not found at {self.graph_path}")
            return False

        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = {}
            for n in data.get("nodes", []):
                # We only need enough structure to replay
                from ..models.extraction import GraphNode, GraphProvenance
                
                prov_data = n.get("provenance", {})
                
                # In the JSON we saved sources count, but we need the actual source_urls
                # Wait, GraphBuilder saved: "sources": len(n.provenance.source_urls)
                # We need to fix GraphBuilder to save actual source URLs!
                # Let's assume we modify GraphBuilder to save "source_urls"
                source_urls = prov_data.get("source_urls", [])

                nodes[n["id"]] = GraphNode(
                    entity_id=n["id"],
                    entity_type=n.get("type", "unknown"),
                    name=n.get("name", "unknown"),
                    status=n.get("status", "unknown"),
                    metadata=n.get("metadata", {}),
                    provenance=GraphProvenance(
                        source_urls=tuple(source_urls),
                        extraction_timestamp=prov_data.get("extraction_timestamp", ""),
                        confidence=prov_data.get("confidence", 1.0),
                        schema_cluster_ids=()
                    )
                )

            # Edges aren't strictly needed for simple replay, skipping for now
            self.graph = CartaEntityGraph(
                graph_id=data.get("graph_id", str(uuid.uuid4())),
                firm_id=data.get("firm_id", 0),
                firm_name=data.get("firm_name", "unknown"),
                created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
                nodes=nodes,
                edges=[],
            )
            log.info(f"[ReplayOrchestrator] Loaded graph with {len(nodes)} nodes.")
            return True
            
        except Exception as e:
            log.error(f"[ReplayOrchestrator] Failed to load graph: {e}")
            return False

    async def replay_entity(self, entity_id: str) -> dict:
        """Targeted re-extraction of a specific entity."""
        if not self.graph:
            if not self.load_graph():
                return {"status": "error", "message": "Graph not loaded"}

        if entity_id not in self.graph.nodes:
            log.warning(f"[ReplayOrchestrator] Entity {entity_id} not found in graph.")
            return {"status": "error", "message": "Entity not found"}

        node = self.graph.nodes[entity_id]
        source_urls = node.provenance.source_urls

        if not source_urls:
            log.warning(f"[ReplayOrchestrator] No provenance (source_urls) for entity {entity_id}.")
            return {"status": "error", "message": "No provenance data"}

        log.info(f"[ReplayOrchestrator] Replaying {len(source_urls)} endpoints for entity {entity_id} ({node.name})...")
        
        results = {}
        for url in source_urls:
            try:
                target = ReplayTarget(
                    method="GET",
                    url=url,
                    headers={},
                    inferred_capabilities={"entity_refresh"}
                )
                
                result = await self.replay_client.get(
                    target=target,
                    scenario=ReplayScenario.AUTO_FALLBACK
                )
                
                if result and result.payload:
                    results[url] = result.payload
                    
            except Exception as e:
                log.error(f"[ReplayOrchestrator] Replay failed for {url}: {e}")
                
        # Save results
        out_file = self.output_dir / f"replay_{entity_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({
                "entity_id": entity_id,
                "entity_name": node.name,
                "replayed_urls": list(results.keys()),
                "data": results
            }, f, indent=2)
            
        log.info(f"[ReplayOrchestrator] Replay complete for {entity_id}. Saved to {out_file.name}")
        return {"status": "success", "entity_id": entity_id, "endpoints_replayed": len(results)}

    async def replay_category(self, entity_type: str) -> dict:
        """Re-extract all entities of a specific type (e.g., 'investment')."""
        if not self.graph:
            if not self.load_graph():
                return {"status": "error"}
                
        targets = [n for n in self.graph.nodes.values() if n.entity_type == entity_type]
        log.info(f"[ReplayOrchestrator] Found {len(targets)} entities of type '{entity_type}' to replay.")
        
        overall_results = {}
        for node in targets:
            res = await self.replay_entity(node.entity_id)
            overall_results[node.entity_id] = res
            
        return {"status": "success", "replayed_entities": len(targets)}
