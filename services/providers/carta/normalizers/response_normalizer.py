"""
Response Normalization Layer (Phase 6).

Acts as an Anti-Corruption Layer (ACL) between Carta's highly volatile
API schemas and our canonical Entity Graph.
"""

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class ResponseNormalizer:
    """
    Normalizes raw Carta API payloads into a canonical graph representation.
    Isolates schema drift from downstream graph construction.
    """

    @staticmethod
    def normalize_entity(
        entity_id: str,
        entity_type: str,
        name: str,
        payload: Dict[str, Any],
        category: str
    ) -> Dict[str, Any]:
        """
        Extract canonical attributes based on the entity type and payload category.
        """
        canonical = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "name": name,
            "status": "unknown",
            "metadata": {},
        }

        # Safe extraction helpers
        def _get_first_valid(*keys):
            for k in keys:
                if k in payload and payload[k] is not None:
                    return payload[k]
            return None

        # 1. Type-specific normalization
        if entity_type == "investment":
            canonical["status"] = _get_first_valid("status", "stage", "investment_status")
            canonical["metadata"]["security_type"] = _get_first_valid("security_type", "securityType")
            canonical["metadata"]["ownership_percentage"] = _get_first_valid("ownership_percentage", "ownership")
            
        elif entity_type in ("fund", "spv"):
            canonical["status"] = _get_first_valid("fund_status", "status", "state")
            canonical["metadata"]["nav"] = _get_first_valid("net_asset_value", "nav", "total_value")
            canonical["metadata"]["vehicle_type"] = _get_first_valid("vehicle_type", "type")

        # 2. Category-specific normalization (deep properties)
        if category == "cap_table":
            canonical["metadata"]["total_shares"] = _get_first_valid("total_shares", "shares_outstanding")
            canonical["metadata"]["valuation"] = _get_first_valid("post_money_valuation", "valuation")
        elif category == "valuations":
            canonical["metadata"]["latest_valuation"] = _get_first_valid("amount", "value", "latest_value")

        # Strip None values
        canonical["metadata"] = {k: v for k, v in canonical["metadata"].items() if v is not None}
        
        return canonical

    @staticmethod
    def extract_relationships(
        source_entity_id: str,
        payload: Dict[str, Any]
    ) -> list[Dict[str, str]]:
        """
        Extract edges (relationships) from an entity's payload.
        Returns a list of dicts: {"target_id": "...", "edge_type": "..."}
        """
        edges = []

        # Find nested entity IDs that imply relationships
        # For instance, a fund might list its investments
        
        # This is highly dependent on schema analysis, but we can look for generic patterns
        if "investments" in payload and isinstance(payload["investments"], list):
            for inv in payload["investments"]:
                if isinstance(inv, dict):
                    inv_id = inv.get("id") or inv.get("investment_id")
                    if inv_id:
                        edges.append({
                            "target_id": f"investment_{inv_id}",
                            "edge_type": "invests_in"
                        })
                        
        if "company_id" in payload:
            edges.append({
                "target_id": f"company_{payload['company_id']}",
                "edge_type": "issued_by"
            })

        return edges
