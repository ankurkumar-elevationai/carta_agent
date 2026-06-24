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
    InteractionProvenance,
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
    EndpointCategory.HOLDINGS,
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
        api_collector = None,
        min_replay_score: float = 50.0,
    ):
        self.classifier = classifier
        self.replay_client = replay_client
        self.output_dir = Path(output_dir)
        self.rate_limit_delay = rate_limit_delay
        self.entity_manifest = entity_manifest or []
        self.manifest = ExtractionManifest()
        self.api_collector = api_collector
        self.min_replay_score = min_replay_score
        self.roi_yield: dict[str, int] = {}
        self.roi_attempts: dict[str, int] = {}

    def _find_entity_for_url(self, url: str) -> Optional[DiscoveredEntity]:
        """Attempt to map a URL back to an entity from the manifest using interaction provenance."""
        # 1. High-confidence match: resolve via interaction provenance context
        prov = self._find_provenance_for_url(url)
        if prov and prov.entity_context:
            for entity in self.entity_manifest:
                if entity.entity_id == prov.entity_context:
                    return entity

        # 2. Low-confidence fallback: string matching on URL
        url_lower = url.lower()
        for entity in self.entity_manifest:
            if entity.detail_url and entity.detail_url.lower() in url_lower:
                return entity
            raw_id = entity.entity_id.split("_")[-1]
            if raw_id.isdigit() and f"/{raw_id}/" in url_lower:
                return entity
        return None

    def _find_provenance_for_url(self, url: str) -> Optional[InteractionProvenance]:
        clean_url = url.split("?")[0]
        if not self.api_collector or not hasattr(self.api_collector, "interaction_tracker"):
            return None
        # Reverse search to find the latest context triggering this endpoint
        for prov in reversed(self.api_collector.interaction_tracker.history):
            if clean_url in prov.triggered_endpoints:
                return prov
        return None

    def score_endpoint(
        self,
        url: str,
        classification: ClassificationResult,
        response_metadata: dict,
        traversal_context: Optional[InteractionProvenance]
    ) -> float:
        clean_path = url.lower().split("?")[0]
        
        # 1. ALWAYS_REPLAY bypass
        ALWAYS_REPLAY = {"portfolio", "investors", "valuations", "cap_table", "securities", "holdings", "export", "post-money"}
        if any(family in clean_path for family in ALWAYS_REPLAY) or classification.category.value in ALWAYS_REPLAY:
            return 100.0

        # 2. Export Promotion
        EXPORT_KEYWORDS = {"export", "download", "csv", "xlsx", "report"}
        if any(kw in clean_path for kw in EXPORT_KEYWORDS):
            return 100.0

        # 3. Hard Skips / Noise
        if classification.traffic_class in (TrafficClass.TELEMETRY, TrafficClass.ANALYTICS, TrafficClass.CONFIG, TrafficClass.STATIC_ASSET, TrafficClass.CDN):
            return 0.0

        NOISE_KEYWORDS = {
            "feature-flag", "permission", "role", "access", "telemetry", "datadog", 
            "sentry", "pendo", "amplitude", "segment", "config", "health", 
            "ping", "heartbeat", "django-messages", "preference", "setting", 
            "tracking", "metrics", "analytics", "launch-app-shell-config", 
            "account-switcher", "global-nav-config", "mf-manifest.json"
        }
        if any(kw in clean_path for kw in NOISE_KEYWORDS):
            return 0.0

        # Base score by category
        score = 0.0
        category_scores = {
            EndpointCategory.PORTFOLIO: 90.0,
            EndpointCategory.VALUATIONS: 90.0,
            EndpointCategory.INVESTORS: 90.0,
            EndpointCategory.CAP_TABLE: 90.0,
            EndpointCategory.SECURITIES: 90.0,
            EndpointCategory.HOLDINGS: 90.0,
            EndpointCategory.REPORTING: 80.0,
            EndpointCategory.GRAPHQL: 70.0,
        }
        score = category_scores.get(classification.category, 30.0)

        # 4. Context Adjustments
        if traversal_context:
            valuable_ui = {"portfolio", "investor", "valuation", "cap table", "equity", "security"}
            ui_path_str = " ".join(traversal_context.ui_path).lower()
            if any(kw in ui_path_str for kw in valuable_ui):
                score += 15.0
            
            if traversal_context.entity_context:
                score += 15.0

        # 5. Metadata Adjustments
        if response_metadata:
            keys = [k.lower() for k in response_metadata.get("top_level_keys", [])]
            valuable_keys = {
                "share_class", "fmv", "fair_market_value", "valuation", "ownership", 
                "authorized", "issued", "legal_name", "investor", "securities",
                "holdings", "transactions"
            }
            if any(k in valuable_keys for k in keys):
                score += 20.0
            
            if response_metadata.get("item_count", 0) > 0:
                score += 10.0

        return min(100.0, score)

    def _count_entities(self, payload) -> int:
        if not payload:
            return 0
        
        def is_business_entity(d) -> bool:
            if not isinstance(d, dict):
                return False
            # Strong keys — any one of these confirms business entity
            strong_keys = {
                "share_class", "fmv", "fair_market_value", "valuation", "ownership_pct",
                "authorized", "issued", "legal_name", "investor", "securities",
                "holdings", "investment_id", "canonical_investment_id", "canonical_captable_id",
                "fmv_date", "fmv_status",
                # Holdings-specific keys
                "rows", "totals", "equity_grants", "shares", "options", "warrants",
                "convertibles", "grant_type", "rsu", "rsa", "sar", "piu",
                "exercise_price", "vesting_schedule", "grant_date",
                # Valuation-specific keys (strong)
                "post_money", "funds_raised", "share_price", "price_per_share",
                "round_name", "round_type", "financing", "financing_round",
            }
            return any(k in d for k in strong_keys)

        if isinstance(payload, list):
            if all(isinstance(x, dict) for x in payload):
                return sum(1 for x in payload if is_business_entity(x))
            return len(payload)
            
        if isinstance(payload, dict):
            if is_business_entity(payload):
                return 1
            for k in ["results", "items", "data", "investments", "valuations", "securities", "share_classes", "holdings"]:
                if k in payload and isinstance(payload[k], list):
                    lst = payload[k]
                    if all(isinstance(x, dict) for x in lst):
                        return sum(1 for x in lst if is_business_entity(x))
                    return len(lst)
                    
        return 0

    def _get_endpoint_family(self, url: str, category: EndpointCategory) -> str:
        path = url.lower()
        for family in ["holdings", "investors", "valuations", "cap_table", "portfolio", "securities", "reporting"]:
            if family in path:
                return family
        return category.value

    def _discover_replay_targets(self) -> list[tuple[str, ClassificationResult]]:
        """
        Scan the classifier's history and return deduplicated high-value targets.
        Returns list of (url, classification) tuples.
        """
        seen_normalized: set[str] = set()
        targets: list[tuple[str, ClassificationResult]] = []

        for url, classification in self.classifier._history.items():
            clean_path = url.split("?")[0].split("#")[0]
            
            # Fetch cached response metadata
            metadata = getattr(self.classifier, "response_metadata", {}).get(clean_path, {})
            
            # Fetch traversal context
            prov = self._find_provenance_for_url(url)
            
            # Compute capability score
            score = self.score_endpoint(url, classification, metadata, prov)
            
            # Skip if score is below configurable threshold
            if score < self.min_replay_score:
                self.manifest.record_skip(url, f"low_value_score={score:.1f} (threshold={self.min_replay_score})")
                continue

            # Skip platform noise (fallback check)
            if _is_platform_noise(url):
                self.manifest.record_skip(url, "platform_noise")
                continue

            # Deduplicate
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
            manifest_data = self.manifest.to_dict()
            manifest_data["_metrics"] = {
                "endpoints_discovered": len(self.classifier._history),
                "endpoints_replayed": 0,
                "endpoints_skipped": len(self.manifest.skipped),
                "successful_replays": 0,
                "failed_replays": 0,
                "new_entities_found": len(self.entity_manifest),
                "roi_metrics": {}
            }
            return manifest_data

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
                            "entity_type": entity.entity_type if entity else None,
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

                    # Count entities for ROI yield
                    entity_count = self._count_entities(result.payload)
                    family = self._get_endpoint_family(url, classification.category)
                    self.roi_attempts[family] = self.roi_attempts.get(family, 0) + 1
                    if entity_count > 0:
                        self.roi_yield[family] = self.roi_yield.get(family, 0) + entity_count

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
                        f"({result.latency_ms}ms, entities={entity_count}, keys={top_keys[:5]})"
                    )
                else:
                    family = self._get_endpoint_family(url, classification.category)
                    self.roi_attempts[family] = self.roi_attempts.get(family, 0) + 1
                    self.manifest.record_failure(
                        url=url,
                        category=classification.category.value,
                        error=f"Empty payload (status={result.status_code if result else 'None'})",
                    )

            except Exception as e:
                family = self._get_endpoint_family(url, classification.category)
                self.roi_attempts[family] = self.roi_attempts.get(family, 0) + 1
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
        
        # Merge attempts and entities into combined metrics structure
        roi_combined = {}
        all_families = set(self.roi_attempts.keys()) | set(self.roi_yield.keys())
        for fam in all_families:
            roi_combined[fam] = {
                "attempts": self.roi_attempts.get(fam, 0),
                "entities": self.roi_yield.get(fam, 0)
            }

        # Add rich metrics block for the PerformanceProfiler
        manifest_data["_metrics"] = {
            "endpoints_discovered": len(self.classifier._history),
            "endpoints_replayed": len(self.manifest.extracted) + len(self.manifest.failed),
            "endpoints_skipped": len(self.manifest.skipped),
            "successful_replays": len(self.manifest.extracted),
            "failed_replays": len(self.manifest.failed),
            "new_entities_found": len(self.entity_manifest),
            "roi_metrics": roi_combined
        }
        
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

        # Extraction coverage report
        total_artifacts = len(self.manifest.extracted)
        attributed_count = 0
        named_count = 0
        unknown_names = 0
        for entry in self.manifest.extracted:
            output_path = entry.get("output_path")
            if output_path:
                try:
                    import pathlib
                    artifact = json.loads(pathlib.Path(output_path).read_text(encoding="utf-8"))
                    meta = artifact.get("_meta", {})
                    if meta.get("entity_id") is not None:
                        attributed_count += 1
                    ename = meta.get("entity_name")
                    if ename and ename != "unknown":
                        named_count += 1
                    else:
                        unknown_names += 1
                except Exception:
                    unknown_names += 1

        coverage_pct = (named_count / total_artifacts * 100) if total_artifacts > 0 else 0.0
        log.info(
            f"[IntelligenceExtractor] Entity Naming Coverage: "
            f"Attributed={attributed_count}/{total_artifacts}, "
            f"Named={named_count}/{total_artifacts}, "
            f"Unknown={unknown_names}, "
            f"Coverage={coverage_pct:.1f}%"
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
