import hashlib
import logging
from typing import Dict

from ..models.extraction import NormalizedEntity, CanonicalEntity

log = logging.getLogger(__name__)


class CanonicalRegistry:
    """
    Maintains a registry of canonical entities, detecting duplicates, 
    resolving aliases, and generating deterministic canonical IDs.
    """

    def __init__(self, firm_id: int):
        self.firm_id = firm_id
        # Maps canonical_id -> CanonicalEntity
        self.registry: Dict[str, CanonicalEntity] = {}
        # Maps alias (lowercase) -> canonical_id
        self.alias_map: Dict[str, str] = {}

    def _generate_deterministic_id(self, normalized_name: str, entity_type: str) -> str:
        """Generate a SHA256 deterministic ID based on normalized name, type, and org_pk."""
        raw_str = f"{normalized_name}:{entity_type}:{self.firm_id}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]

    def _normalize_string(self, text: str) -> str:
        """Standardize a string for alias matching."""
        if not text:
            return ""
        # Remove common corporate suffixes and make lowercase
        text = text.lower().replace(",", "").replace(".", "")
        suffixes = [" inc", " llc", " ltd", " lp", " l.p.", " corporation", " corp"]
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
        return text.strip()

    def register(self, entity: NormalizedEntity, source_artifact: str) -> CanonicalEntity:
        """
        Ingest a NormalizedEntity, resolve duplicates/aliases, and return the CanonicalEntity.
        """
        norm_name = self._normalize_string(entity.display_name)
        
        # Determine canonical ID based on existing aliases or generate a new one
        canonical_id = self.alias_map.get(norm_name)
        
        if not canonical_id:
            # Check if any aliases match
            for alias in entity.aliases:
                norm_alias = self._normalize_string(alias)
                if norm_alias in self.alias_map:
                    canonical_id = self.alias_map[norm_alias]
                    break
        
        if not canonical_id:
            # Generate a new deterministic ID
            canonical_id = self._generate_deterministic_id(norm_name, entity.entity_type)
            # Create a new CanonicalEntity
            canonical_entity = CanonicalEntity(
                canonical_id=canonical_id,
                entity_type=entity.entity_type,
                display_name=entity.display_name,
                aliases=entity.aliases.copy(),
                confidence=1.0,
                first_seen_artifact=source_artifact,
                last_seen_artifact=source_artifact,
                source_count=1,
                properties=entity.properties.copy()
            )
            self.registry[canonical_id] = canonical_entity
            
            # Map aliases
            self.alias_map[norm_name] = canonical_id
            for alias in entity.aliases:
                norm_alias = self._normalize_string(alias)
                if norm_alias:
                    self.alias_map[norm_alias] = canonical_id
        else:
            # Update existing CanonicalEntity
            canonical_entity = self.registry[canonical_id]
            canonical_entity.source_count += 1
            canonical_entity.last_seen_artifact = source_artifact
            
            # Merge aliases
            all_aliases = set(canonical_entity.aliases + entity.aliases)
            if entity.display_name != canonical_entity.display_name:
                all_aliases.add(entity.display_name)
            canonical_entity.aliases = sorted(list(all_aliases))
            
            # Update alias map
            for alias in canonical_entity.aliases:
                norm_alias = self._normalize_string(alias)
                if norm_alias and norm_alias not in self.alias_map:
                    self.alias_map[norm_alias] = canonical_id
                    
            # Merge properties (newer takes precedence for simplicity)
            for k, v in entity.properties.items():
                if v is not None:
                    canonical_entity.properties[k] = v

        return canonical_entity
