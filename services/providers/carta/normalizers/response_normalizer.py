"""
Response Normalization Layer (Phase 6).

Acts as an Anti-Corruption Layer (ACL) between Carta's highly volatile
API schemas and our canonical Entity Graph.
"""

import logging
import hashlib
from typing import Dict, Any, Optional, List

from ..models.extraction import NormalizedEntity, RelationshipCandidate

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
        category: str,
        source_url: str = ""
    ) -> NormalizedEntity:
        """
        Extract canonical attributes based on the entity type and payload category.
        """
        properties = {}
        status = "unknown"
        aliases = []

        if not isinstance(payload, dict):
            return NormalizedEntity(
                canonical_id=entity_id,
                entity_type=entity_type,
                display_name=name,
                aliases=aliases,
                properties=properties,
                source_url=source_url
            )

        # Safe extraction helpers
        def _get_first_valid(*keys):
            for k in keys:
                if k in payload and payload[k] is not None:
                    return payload[k]
            return None

        # 1. Type-specific normalization
        if entity_type == "investment":
            status = _get_first_valid("status", "stage", "investment_status") or "unknown"
            properties["security_type"] = _get_first_valid("security_type", "securityType")
            properties["ownership_percentage"] = _get_first_valid("ownership_percentage", "ownership")
            properties["status"] = status
            
        elif entity_type in ("fund", "spv"):
            status = _get_first_valid("fund_status", "status", "state") or "unknown"
            properties["nav"] = _get_first_valid("net_asset_value", "nav", "total_value")
            properties["vehicle_type"] = _get_first_valid("vehicle_type", "type")
            properties["status"] = status

        elif entity_type == "organization":
            properties["account_type"] = _get_first_valid("account_type", "type")

        # 2. Category-specific normalization (deep properties)
        if category == "cap_table":
            properties["total_shares"] = _get_first_valid("total_shares", "shares_outstanding")
            properties["valuation"] = _get_first_valid("post_money_valuation", "valuation", "post_money")
        elif category == "valuations" or category == "valuation":
            properties["latest_valuation"] = _get_first_valid("amount", "value", "latest_value", "post_money", "valuation")
            properties["share_price"] = _get_first_valid("share_price", "price_per_share")
            properties["funds_raised"] = _get_first_valid("funds_raised")
            properties["currency"] = _get_first_valid("currency")
            properties["status_409a"] = _get_first_valid("status_409a", "fmv_status")

        # Strip None values
        properties = {k: v for k, v in properties.items() if v is not None}
        
        # Add alias if legal_name or dba exists but differs
        legal_name = _get_first_valid("legal_name", "company_name")
        dba = _get_first_valid("dba")
        if legal_name and legal_name != name:
            aliases.append(legal_name)
        if dba and dba != name:
            aliases.append(dba)

        return NormalizedEntity(
            canonical_id=entity_id,
            entity_type=entity_type,
            display_name=name,
            aliases=aliases,
            properties=properties,
            source_url=source_url
        )

    @staticmethod
    def extract_relationships(
        source_entity_id: str,
        source_entity_type: str,
        payload: Dict[str, Any],
        parent_org_pk: Optional[int] = None,
        artifact_id: str = ""
    ) -> List[RelationshipCandidate]:
        """
        Extract edges (relationships) from an entity's payload.
        Returns a list of RelationshipCandidate objects.
        """
        candidates = []
        if not isinstance(payload, dict):
            return candidates

        # 1. Organization -> Fund
        if parent_org_pk and source_entity_type in ("fund", "spv"):
            candidates.append(RelationshipCandidate(
                source=f"org_{parent_org_pk}",
                target=source_entity_id,
                edge_type="manages",
                confidence=1.0,
                evidence=["parent_org_pk"],
                origin_artifact_id=artifact_id,
                metadata={"target_type": source_entity_type}
            ))

        # 2. Fund -> Investment (from fund payload)
        if "investments" in payload and isinstance(payload["investments"], list):
            for inv in payload["investments"]:
                if isinstance(inv, dict):
                    inv_id = inv.get("id") or inv.get("investment_id")
                    if inv_id:
                        candidates.append(RelationshipCandidate(
                            source=source_entity_id,
                            target=f"investment_{inv_id}",
                            edge_type="invested_in",
                            confidence=0.9,
                            evidence=["investments_list"],
                            origin_artifact_id=artifact_id,
                            metadata={"target_type": "investment"}
                        ))

        # 2b. Fund -> Investment (from investment payload) - FIX FOR ORPHANED INVESTMENTS
        if source_entity_type == "investment":
            fund_id = payload.get("fund_id") or payload.get("parent_fund_id") or payload.get("fund_uuid") or payload.get("firm_uuid")
            if fund_id:
                candidates.append(RelationshipCandidate(
                    source=f"fund_{fund_id}",
                    target=source_entity_id,
                    edge_type="invested_in",
                    confidence=0.95,
                    evidence=["fund_id_in_investment_payload"],
                    origin_artifact_id=artifact_id,
                    metadata={"target_type": "investment"}
                ))

        # 3. Investment -> PortfolioCompany
        corp_id = payload.get("corporation_id") or payload.get("company_id")
        if corp_id and source_entity_type == "investment":
            candidates.append(RelationshipCandidate(
                source=source_entity_id,
                target=f"company_{corp_id}",
                edge_type="issued_by",
                confidence=0.95,
                evidence=["company_id"],
                origin_artifact_id=artifact_id,
                metadata={"target_type": "portfolio_company"}
            ))

        # 4. Fund -> Investor
        if "investors" in payload and isinstance(payload["investors"], list):
            for investor in payload["investors"]:
                if isinstance(investor, dict):
                    inv_id = investor.get("id") or investor.get("investor_id")
                    if inv_id:
                        candidates.append(RelationshipCandidate(
                            source=source_entity_id,
                            target=f"investor_{inv_id}",
                            edge_type="has_investor",
                            confidence=0.9,
                            evidence=["investors_list"],
                            origin_artifact_id=artifact_id,
                            metadata={"target_type": "investor"}
                        ))

        # 5. PortfolioCompany -> Valuation
        if source_entity_type == "portfolio_company" or (source_entity_type == "investment" and corp_id):
            portco_id = f"company_{corp_id}" if corp_id else source_entity_id
            
            val_keys = ["post_money", "valuation", "fmv", "amount", "latest_value", "funds_raised"]
            has_val = any(k in payload and payload[k] is not None for k in val_keys)
            
            if has_val:
                val_hash = hashlib.sha256(str(payload).encode()).hexdigest()[:12]
                val_id = f"valuation_{val_hash}"
                
                # Create the node implicitly through a RelationshipCandidate? 
                # For now, GraphBuilder handles payload_ref. We'll pass it in evidence as a stringified representation
                # and maybe GraphBuilder should just extract valuation nodes instead.
                # Actually, GraphBuilder expects payload_ref in raw_edges to build the node. Let's adapt.
                # But RelationshipCandidate doesn't have a payload field.
                # We can skip implicit node creation for valuations, but the existing code relied on it.
                # Let's just create the candidate.
                candidates.append(RelationshipCandidate(
                    source=portco_id,
                    target=val_id,
                    edge_type="valued_at",
                    confidence=0.8,
                    evidence=["valuation_keys"],
                    origin_artifact_id=artifact_id,
                    metadata={"target_type": "valuation", "payload_ref": payload}
                ))
                ))

        # 6. Generic Universal UUID edges
        org_uuid = payload.get("organization_uuid") or payload.get("organization_id")
        if org_uuid:
            candidates.append(RelationshipCandidate(
                source=f"org_{org_uuid}",
                target=source_entity_id,
                edge_type="manages" if source_entity_type in ("fund", "spv") else "owns",
                confidence=0.9,
                evidence=["organization_uuid"],
                origin_artifact_id=artifact_id,
                metadata={"target_type": source_entity_type}
            ))

        investor_id = payload.get("investor_id")
        if investor_id and source_entity_type in ("investment", "security"):
            candidates.append(RelationshipCandidate(
                source=f"investor_{investor_id}",
                target=source_entity_id,
                edge_type="invested_in",
                confidence=0.9,
                evidence=["investor_id"],
                origin_artifact_id=artifact_id,
                metadata={"target_type": source_entity_type}
            ))

        security_id = payload.get("security_id")
        if security_id and source_entity_type in ("investment", "portfolio_company"):
            candidates.append(RelationshipCandidate(
                source=source_entity_id,
                target=f"security_{security_id}",
                edge_type="holds_security",
                confidence=0.9,
                evidence=["security_id"],
                origin_artifact_id=artifact_id,
                metadata={"target_type": "security"}
            ))

        return candidates
