"""
API Dependency Graph Tracker (Phase 3).

Tracks dependencies between API calls (A -> B -> C) by observing temporal ordering
and shared IDs/tokens across requests and responses. This is essential for
replay reliability, automation, and workflow reconstruction.
"""

import logging
from typing import List, Optional
from urllib.parse import urlparse, parse_qs
from ..models.extraction import APIDependency

log = logging.getLogger(__name__)


class APIDependencyTracker:
    """
    Tracks API dependencies by monitoring which responses provide IDs that
    subsequent requests consume.
    """

    def __init__(self):
        self._dependencies: List[APIDependency] = []
        # Store recent responses: url -> extracted_ids
        self._recent_ids: dict[str, dict[str, str]] = {}
        # Simple ring buffer to prevent unbounded growth
        self._recent_urls: List[str] = []
        self._max_history = 100

    def observe_request(
        self, url: str, request_headers: dict, request_body: Optional[bytes] = None
    ):
        """Analyze outgoing request for dependencies on past responses."""
        clean_url = url.split("?")[0]
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Look for IDs in the URL path or query params that we've seen before
        for past_url in reversed(self._recent_urls):
            past_ids = self._recent_ids.get(past_url, {})
            matched_ids = {}

            for id_key, id_val in past_ids.items():
                if id_val and (id_val in clean_url or self._in_query(id_val, query_params)):
                    matched_ids[id_key] = id_val

            if matched_ids:
                dep = APIDependency(
                    source_url=past_url,
                    target_url=clean_url,
                    dependency_type="id_chain",
                    extracted_ids=matched_ids,
                )
                self._dependencies.append(dep)
                log.debug(f"[APIDependency] Found dependency: {past_url} -> {clean_url}")
                # Stop after finding the most recent parent
                break

    def observe_response(self, url: str, response_payload: dict):
        """Analyze incoming response to extract IDs for future requests."""
        if not isinstance(response_payload, dict):
            return

        clean_url = url.split("?")[0]
        extracted = self._extract_potential_ids(response_payload)

        if extracted:
            self._recent_ids[clean_url] = extracted
            if clean_url in self._recent_urls:
                self._recent_urls.remove(clean_url)
            self._recent_urls.append(clean_url)

            # Keep bounded history
            if len(self._recent_urls) > self._max_history:
                oldest = self._recent_urls.pop(0)
                self._recent_ids.pop(oldest, None)

    @property
    def dependencies(self) -> List[APIDependency]:
        return self._dependencies

    @staticmethod
    def _in_query(val: str, query_params: dict) -> bool:
        for q_vals in query_params.values():
            if val in q_vals:
                return True
        return False

    def _extract_potential_ids(self, payload: dict) -> dict[str, str]:
        """Extract fields ending in 'id', 'pk', or 'uuid'."""
        extracted = {}
        for k, v in payload.items():
            if isinstance(v, (str, int)):
                k_lower = k.lower()
                if k_lower.endswith("_id") or k_lower.endswith("_pk") or k_lower == "id" or k_lower == "uuid":
                    extracted[k] = str(v)
            elif isinstance(v, dict):
                nested = self._extract_potential_ids(v)
                extracted.update(nested)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # Just take the first item's IDs for simple dependency tracking
                nested = self._extract_potential_ids(v[0])
                extracted.update(nested)
        return extracted
