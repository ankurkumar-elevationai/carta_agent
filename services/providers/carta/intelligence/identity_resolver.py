import msgspec
import logging
import os
import orjson
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger(__name__)

class ResolvedIdentity(msgspec.Struct):
    entity_id: str
    entity_name: str
    legal_name: Optional[str]
    aliases: List[str]
    confidence: float
    resolution_source: str
    frequency: int = 1

class EntityIdentityResolver:
    """
    Resolves 'unknown' or incomplete entities by cross-referencing 
    hierarchical priority data sources using Authority + Frequency scoring.
    
    Authority Hierarchy:
    Valuation API      1.00
    Cap Table API      0.95
    Holdings API       0.90
    Investment API     0.85
    Notes API          0.70
    Exports            0.60
    """
    
    def __init__(self, extracted_dir: Path, output_dir: Path):
        self.extracted_dir = extracted_dir
        self.output_dir = output_dir
        # Map of entity_id -> dict mapping name -> ResolvedIdentity
        # This allows us to track frequency for DIFFERENT names of the same entity
        self.identity_candidates: Dict[str, Dict[str, ResolvedIdentity]] = {}
        self.report_stats = {
            "resolved": 0,
            "unresolved": 0,
            "source_breakdown": {}
        }

    def _scan_sources(self):
        """Scans extracted JSONs and Exports to build an identity mapping."""
        if not self.extracted_dir.exists():
            return
            
        for root, _, files in os.walk(self.extracted_dir):
            for file in files:
                if not file.endswith(".json"):
                    continue
                path = Path(root) / file
                
                try:
                    with open(path, "rb") as f:
                        payload = orjson.loads(f.read())
                        
                    self._extract_from_payload(payload, str(path))
                except Exception as e:
                    log.debug(f"[IdentityResolver] Error parsing {path}: {e}")

    def _extract_from_payload(self, payload: Any, source: str):
        if isinstance(payload, dict):
            # Attempt to find standard identity fields
            entity_id = str(payload.get("id") or payload.get("entity_id") or payload.get("investment_id") or payload.get("company_id") or payload.get("fund_id") or "")
            
            if not entity_id:
                # Traverse nested
                for v in payload.values():
                    if isinstance(v, (dict, list)):
                        self._extract_from_payload(v, source)
                return

            name = payload.get("name") or payload.get("company_name") or payload.get("legal_name") or payload.get("entity_name")
            legal = payload.get("legal_name")
            
            if name and entity_id:
                authority = 0.50
                source_type = "other_api"
                
                source_lower = source.lower()
                if "valuation" in source_lower:
                    authority = 1.00
                    source_type = "valuation_api"
                elif "cap_table" in source_lower or "captable" in source_lower:
                    authority = 0.95
                    source_type = "cap_table_api"
                elif "holding" in source_lower:
                    authority = 0.90
                    source_type = "holdings_api"
                elif "investment" in source_lower:
                    authority = 0.85
                    source_type = "investment_api"
                elif "note" in source_lower:
                    authority = 0.70
                    source_type = "notes_api"
                elif "export" in source_lower:
                    authority = 0.60
                    source_type = "exports"
                
                if entity_id not in self.identity_candidates:
                    self.identity_candidates[entity_id] = {}
                    
                candidates = self.identity_candidates[entity_id]
                
                if name in candidates:
                    existing = candidates[name]
                    existing.frequency += 1
                    # Base confidence is authority + (frequency * 0.01)
                    # We keep the highest authority seen for this name
                    highest_authority = max(existing.confidence - (existing.frequency - 1) * 0.01, authority)
                    existing.confidence = highest_authority + (existing.frequency * 0.01)
                    
                    if authority >= highest_authority:
                        existing.resolution_source = source_type
                        
                    if legal and not existing.legal_name:
                        existing.legal_name = legal
                else:
                    candidates[name] = ResolvedIdentity(
                        entity_id=entity_id,
                        entity_name=name,
                        legal_name=legal,
                        aliases=[],
                        confidence=authority + 0.01, # frequency = 1
                        resolution_source=source_type,
                        frequency=1
                    )

            # Recurse for nested lists/dicts
            for v in payload.values():
                if isinstance(v, (dict, list)):
                    self._extract_from_payload(v, source)
                    
        elif isinstance(payload, list):
            for item in payload:
                self._extract_from_payload(item, source)

    def resolve(self, nodes: Dict[str, Any]) -> Dict[str, Any]:
        """Apply resolved identities to the graph nodes."""
        self._scan_sources()
        
        for node_id, node in nodes.items():
            # If node name is missing or unknown
            if not node.name or node.name.lower() == "unknown":
                
                # We need to extract the raw ID (e.g. investment_uuid -> uuid)
                raw_id = node_id.split("_")[-1] if "_" in node_id else node_id
                
                candidates = self.identity_candidates.get(raw_id) or self.identity_candidates.get(node_id)
                
                if candidates:
                    # Pick the candidate with the highest final confidence
                    best_candidate = max(candidates.values(), key=lambda c: c.confidence)
                    
                    node.name = best_candidate.entity_name
                    if best_candidate.legal_name:
                        node.properties["legal_name"] = best_candidate.legal_name
                        
                    self.report_stats["resolved"] += 1
                    src = best_candidate.resolution_source
                    self.report_stats["source_breakdown"][src] = self.report_stats["source_breakdown"].get(src, 0) + 1
                    
                    log.info(f"[IdentityResolver] Resolved {node_id} -> {best_candidate.entity_name} ({src}, conf: {best_candidate.confidence:.2f})")
                else:
                    self.report_stats["unresolved"] += 1

        # Write report
        report_path = self.output_dir / "identity_resolution_report.json"
        with open(report_path, "w") as f:
            json_report = {
                "resolved": self.report_stats["resolved"],
                "unresolved": self.report_stats["unresolved"],
                "source_breakdown": self.report_stats["source_breakdown"]
            }
            f.write(orjson.dumps(json_report, option=orjson.OPT_INDENT_2).decode("utf-8"))
            
        log.info(f"[IdentityResolver] Complete. Resolved {self.report_stats['resolved']}, Unresolved {self.report_stats['unresolved']}")
        return nodes
