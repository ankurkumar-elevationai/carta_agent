"""
Intelligence Extractor.

After passive network discovery has catalogued all the internal APIs Carta uses,
this component replays the high-value business API calls using the captured auth
context and saves structured JSON payloads as the final extracted intelligence.

Flow:
  PassiveNetworkCollector (discovery) → EndpointClassifier (categorization)
      → IntelligenceExtractor (replay & persist)
"""

import os
import json
import time
import asyncio
import logging
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode

from ..discovery.endpoint_classifier import EndpointClassifier, ClassificationResult
from ..models.extraction import (
    TrafficClass,
    EndpointCategory,
    CapabilityTag,
    DiscoveredEntity,
)
from ..api.replay_client import (
    CartaReplayClient,
    ReplayTarget,
    ReplayResult,
    ReplayScenario,
    ReplayException,
)

log = logging.getLogger(__name__)

# Categories worth replaying — these contain actual business data
_EXTRACTABLE_CATEGORIES = frozenset({
    EndpointCategory.PORTFOLIO,
    EndpointCategory.VALUATIONS,
    EndpointCategory.INVESTORS,
    EndpointCategory.CAP_TABLE,
    EndpointCategory.SECURITIES,
    EndpointCategory.REPORTING,
    EndpointCategory.GRAPHQL,
})

# URL path fragments that are platform/config noise, not company data
_PLATFORM_NOISE_PATHS = frozenset({
    "/pendo-config",
    "/account-switcher",
    "/global-nav-config",
    "/django-messages",
    "/launch-app-shell-config",
    "/mf-manifest.json",
    "/feature-flags",
})


class ExtractionManifest:
    """Tracks what was extracted and what failed."""

    def __init__(self):
        self.extracted: list[dict] = []
        self.failed: list[dict] = []
        self.skipped: list[dict] = []
        self.started_at: float = time.time()
        self.completed_at: Optional[float] = None

    def record_success(self, url: str, category: str, output_path: str, latency_ms: int, keys: list[str]):
        self.extracted.append({
            "url": url,
            "category": category,
            "output_path": output_path,
            "latency_ms": latency_ms,
            "top_level_keys": keys,
        })

    def record_failure(self, url: str, category: str, error: str):
        self.failed.append({
            "url": url,
            "category": category,
            "error": error,
        })

    def record_skip(self, url: str, reason: str):
        self.skipped.append({
            "url": url,
            "reason": reason,
        })

    def to_dict(self) -> dict:
        self.completed_at = time.time()
        duration = self.completed_at - self.started_at
        return {
            "summary": {
                "total_extracted": len(self.extracted),
                "total_failed": len(self.failed),
                "total_skipped": len(self.skipped),
                "duration_seconds": round(duration, 2),
            },
            "extracted": self.extracted,
            "failed": self.failed,
            "skipped": self.skipped,
        }


def _normalize_url_for_dedup(url: str) -> str:
    """Normalize URL by stripping volatile query params for deduplication."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    # Remove date/time/session volatile params
    volatile_keys = {"date", "timestamp", "t", "ts", "dd-request-id", "batch_time", "dd-evp-origin-version", "dd-api-key"}
    stable_params = {k: v for k, v in params.items() if k.lower() not in volatile_keys}
    stable_query = urlencode(stable_params, doseq=True)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{'?' + stable_query if stable_query else ''}"


def _is_platform_noise(url: str) -> bool:
    """Check if URL is platform infrastructure noise, not company data."""
    path_lower = url.lower()
    for noise in _PLATFORM_NOISE_PATHS:
        if noise in path_lower:
            return True
    return False


def _url_to_filename(url: str) -> str:
    """Generate a safe, deterministic filename from a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class IntelligenceExtractor:
    """
    Replays discovered internal API endpoints to extract structured business data.

    After the PassiveNetworkCollector + EndpointClassifier have categorized all
    network traffic during SPA traversal, this component:
    1. Filters for high-value business endpoints
    2. Deduplicates URLs
    3. Replays each endpoint via CartaReplayClient
    4. Saves structured JSON responses organized by category
    5. Produces an extraction manifest
    """

    def __init__(
        self,
        classifier: EndpointClassifier,
        replay_client: CartaReplayClient,
        output_dir: Path,
        rate_limit_delay: float = 1.0,
        entity_manifest: list[DiscoveredEntity] = None,
    ):
        self.classifier = classifier
        self.replay_client = replay_client
        self.output_dir = Path(output_dir)
        self.rate_limit_delay = rate_limit_delay
        self.entity_manifest = entity_manifest or []
        self.manifest = ExtractionManifest()

    def _find_entity_for_url(self, url: str) -> Optional[DiscoveredEntity]:
        """Attempt to map a URL back to an entity from the manifest."""
        url_lower = url.lower()
        for entity in self.entity_manifest:
            # 1. Match by detail_url
            if entity.detail_url and entity.detail_url.lower() in url_lower:
                return entity
            # 2. Match by raw Carta ID (if the entity_id was generated like 'investment_123')
            raw_id = entity.entity_id.split("_")[-1]
            if raw_id.isdigit() and f"/{raw_id}/" in url_lower:
                return entity
        return None

    def _discover_replay_targets(self) -> list[tuple[str, ClassificationResult]]:
        """
        Scan the classifier's history and return deduplicated high-value targets.
        Returns list of (url, classification) tuples.
        """
        seen_normalized: set[str] = set()
        targets: list[tuple[str, ClassificationResult]] = []

        for url, classification in self.classifier._history.items():
            # 1. Only extract business API or GraphQL traffic
            if classification.category not in _EXTRACTABLE_CATEGORIES:
                self.manifest.record_skip(url, f"category={classification.category.value}")
                continue

            # 2. Skip platform noise
            if _is_platform_noise(url):
                self.manifest.record_skip(url, "platform_noise")
                continue

            # 3. Deduplicate
            normalized = _normalize_url_for_dedup(url)
            if normalized in seen_normalized:
                self.manifest.record_skip(url, "duplicate")
                continue
            seen_normalized.add(normalized)

            targets.append((url, classification))

        # Sort by category for organized output
        targets.sort(key=lambda t: t[1].category.value)
        return targets

    async def extract(self) -> dict:
        """
        Main extraction entry point.
        Returns the extraction manifest as a dict.
        """
        targets = self._discover_replay_targets()

        if not targets:
            log.warning("[IntelligenceExtractor] No high-value endpoints discovered. Extraction skipped.")
            return self.manifest.to_dict()

        log.info(f"[IntelligenceExtractor] Discovered {len(targets)} high-value endpoints to replay.")

        for url, classification in targets:
            entity = self._find_entity_for_url(url)
            
            # Group by entity_id if available, otherwise just category
            if entity:
                category_dir = self.output_dir / classification.category.value / entity.entity_id
            else:
                category_dir = self.output_dir / classification.category.value / "global"
                
            category_dir.mkdir(parents=True, exist_ok=True)

            try:
                result = await self._replay_endpoint(url, classification)

                if result and result.payload:
                    # Save the extracted data
                    filename = _url_to_filename(url)
                    output_path = category_dir / f"{filename}.json"

                    # Build rich output with provenance
                    output_data = {
                        "_meta": {
                            "source_url": url,
                            "category": classification.category.value,
                            "capability_tags": [t.value for t in classification.capability_tags],
                            "replay_strategy": result.strategy_used.value,
                            "status_code": result.status_code,
                            "latency_ms": result.latency_ms,
                            "shape_hash": result.shape_hash,
                            "x_carta_trace_id": result.x_carta_trace_id,
                            "entity_id": entity.entity_id if entity else None,
                            "entity_name": entity.name if entity else None,
                            "org_pk": entity.parent_org_pk if entity else None,
                        },
                        "data": result.payload,
                    }

                    output_path.write_text(
                        json.dumps(output_data, indent=2, default=str),
                        encoding="utf-8",
                    )

                    top_keys = []
                    if isinstance(result.payload, dict):
                        top_keys = list(result.payload.keys())[:20]

                    self.manifest.record_success(
                        url=url,
                        category=classification.category.value,
                        output_path=str(output_path),
                        latency_ms=result.latency_ms,
                        keys=top_keys,
                    )

                    log.info(
                        f"[IntelligenceExtractor] ✓ {classification.category.value}: "
                        f"{url.split('?')[0]} → {output_path.name} "
                        f"({result.latency_ms}ms, keys={top_keys[:5]})"
                    )
                else:
                    self.manifest.record_failure(
                        url=url,
                        category=classification.category.value,
                        error=f"Empty payload (status={result.status_code if result else 'None'})",
                    )

            except Exception as e:
                log.warning(f"[IntelligenceExtractor] ✗ Failed to replay {url}: {e}")
                self.manifest.record_failure(
                    url=url,
                    category=classification.category.value,
                    error=str(e),
                )

            # Rate limiting between requests
            await asyncio.sleep(self.rate_limit_delay)

        # Save manifest
        manifest_data = self.manifest.to_dict()
        manifest_path = self.output_dir / "_extraction_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, default=str),
            encoding="utf-8",
        )

        log.info(
            f"[IntelligenceExtractor] Extraction complete: "
            f"{manifest_data['summary']['total_extracted']} extracted, "
            f"{manifest_data['summary']['total_failed']} failed, "
            f"{manifest_data['summary']['total_skipped']} skipped "
            f"in {manifest_data['summary']['duration_seconds']}s"
        )

        return manifest_data

    async def _replay_endpoint(self, url: str, classification: ClassificationResult) -> Optional[ReplayResult]:
        """Replay a single endpoint using the CartaReplayClient."""
        target = ReplayTarget(
            method="GET",
            url=url,
            headers={},
            body_hash=None,
            inferred_capabilities={t.value for t in classification.capability_tags},
        )

        try:
            result = await self.replay_client.get(
                target=target,
                scenario=ReplayScenario.AUTO_FALLBACK,
            )
            return result
        except ReplayException as e:
            log.warning(f"[IntelligenceExtractor] Replay failed for {url}: {e}")
            raise
