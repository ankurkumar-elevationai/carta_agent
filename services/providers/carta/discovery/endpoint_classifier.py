"""
Endpoint Classification Engine.

Automatically classifies discovered Carta API endpoints into semantic categories,
capabilities, and traffic classes based on URL patterns, query parameters, and response shape heuristics.
"""

import re
import logging
from typing import Optional
from pydantic import BaseModel

from ..models.extraction import TrafficClass, CapabilityTag, EndpointCategory

log = logging.getLogger(__name__)


# Layer 2: Regex map for Capabilities and Categories
_CAPABILITY_RULES: list[tuple[str, EndpointCategory, list[CapabilityTag]]] = [
    (r"/graphql", EndpointCategory.GRAPHQL, [CapabilityTag.GRAPHQL]),
    (r"/portfolio|/fund|/investment", EndpointCategory.PORTFOLIO, [CapabilityTag.PORTFOLIO_DATA, CapabilityTag.ENTITY_LIST]),
    (r"/cap.?table|/equity", EndpointCategory.CAP_TABLE, [CapabilityTag.CAP_TABLE]),
    (r"/valuation|/409a|/fmv|/post-money", EndpointCategory.VALUATIONS, [CapabilityTag.VALUATION_DATA, CapabilityTag.CAP_TABLE]),
    (r"/securit|/share.?class|/option|/warrant", EndpointCategory.SECURITIES, [CapabilityTag.CAP_TABLE]),
    (r"/holdings/", EndpointCategory.HOLDINGS, [CapabilityTag.CAP_TABLE, CapabilityTag.ENTITY_DETAIL]),
    (r"/investor|/entity|/company", EndpointCategory.INVESTORS, [CapabilityTag.ENTITY_DETAIL]),
    (r"/report|/export|/download", EndpointCategory.REPORTING, [CapabilityTag.REPORTING]),
    (r"/task|/job|/queue", EndpointCategory.TASKS, [CapabilityTag.BATCHABLE]),
    (r"/permission|/auth|/role|/access", EndpointCategory.PERMISSIONS, [CapabilityTag.AUTH_REQUIRED]),
    (r"/static|/asset|/chunk|/webpack|/__", EndpointCategory.INTERNAL, []),
]

# URLs matching these patterns are reclassified to their true category
# regardless of what the capability rules say. This prevents false positives.
_FALSE_POSITIVE_OVERRIDES = {
    r"/get-products": EndpointCategory.INTERNAL,
    r"/investor-search": EndpointCategory.INVESTORS,
    r"/fe-platform/": EndpointCategory.INTERNAL,
}

_COMPILED_RULES = [(re.compile(pat, re.IGNORECASE), cat, tags) for pat, cat, tags in _CAPABILITY_RULES]
_COMPILED_FP_OVERRIDES = [(re.compile(pat, re.IGNORECASE), cat) for pat, cat in _FALSE_POSITIVE_OVERRIDES.items()]


class ClassificationResult(BaseModel):
    traffic_class: TrafficClass
    category: EndpointCategory
    capability_tags: tuple[CapabilityTag, ...]
    confidence_distribution: dict[CapabilityTag, float]
    matched_rule: Optional[str] = None


FIRST_PARTY_DOMAINS = ["carta.team", "carta.com", "eshares.com"]

def is_first_party(url: str) -> bool:
    from urllib.parse import urlparse
    netloc = urlparse(url).netloc.lower()
    return any(d in netloc for d in FIRST_PARTY_DOMAINS)

def classify_traffic(url: str) -> TrafficClass:
    path = url.lower()
    if not is_first_party(url):
        if "datadoghq.com" in path or "sentry.io" in path:
            return TrafficClass.TELEMETRY
        if "segment.com" in path or "amplitude.com" in path or "pendo.io" in path:
            return TrafficClass.ANALYTICS
        return TrafficClass.EXTERNAL_SERVICE

    if "datadoghq.com" in path or "sentry.io" in path or "/api/v2/rum" in path or "/api/v2/logs" in path:
        return TrafficClass.TELEMETRY
    if "segment.com" in path or "amplitude.com" in path or "pendo.io" in path:
        return TrafficClass.ANALYTICS
    if "cdn." in path:
        return TrafficClass.CDN
    if "/mf-manifest.json" in path or "remoteentry.js" in path:
        return TrafficClass.MICROFRONTEND
    if path.endswith(".js") or path.endswith(".css") or path.endswith(".woff2") or "/static/" in path or "/bundles/" in path:
        return TrafficClass.STATIC_ASSET
    if "/graphql" in path:
        return TrafficClass.GRAPHQL
    if "/auth" in path or "/login" in path:
        return TrafficClass.AUTH
    if "/config" in path or "/feature-flags" in path or "/django-messages" in path:
        return TrafficClass.CONFIG
    if "/export" in path or "/download" in path or "format=csv" in path or ".csv" in path or ".xlsx" in path:
        return TrafficClass.EXPORT
    if "/api/" in path or "/valuate/" in path or "/firm/" in path or "/list_cached/" in path:
        return TrafficClass.BUSINESS_API
    return TrafficClass.UNKNOWN


def classify_endpoint(url: str, response_text: str = "") -> ClassificationResult:
    """Classify a URL using layered heuristics."""
    path = url.split("?")[0].split("#")[0]
    traffic_class = classify_traffic(url)

    capabilities = set()
    category = EndpointCategory.UNKNOWN
    matched_rule = "fallback"
    
    # 1. Regex Map
    for compiled_re, rule_cat, tags in _COMPILED_RULES:
        if compiled_re.search(path):
            category = rule_cat
            capabilities.update(tags)
            matched_rule = compiled_re.pattern
            break

    if traffic_class == TrafficClass.EXPORT:
        category = EndpointCategory.EXPORT if hasattr(EndpointCategory, "EXPORT") else EndpointCategory.UNKNOWN
        capabilities.add(CapabilityTag.REPORTING)
        matched_rule = "traffic_class:export"

    # 1b. False positive overrides — reclassify mismatched URLs
    for fp_re, fp_cat in _COMPILED_FP_OVERRIDES:
        if fp_re.search(path):
            category = fp_cat
            matched_rule = f"fp_override:{fp_re.pattern}"
            break

    # 2. Query Params
    if "page=" in url or "limit=" in url or "offset=" in url:
        capabilities.add(CapabilityTag.PAGINATED)
    if "search=" in url or "query=" in url or "q=" in url:
        capabilities.add(CapabilityTag.SEARCHABLE)

    # 3. Response Schema Heuristics
    if response_text:
        resp_lower = response_text.lower()
        if "share_class" in resp_lower or "cap_table" in resp_lower:
            category = EndpointCategory.CAP_TABLE
            capabilities.add(CapabilityTag.CAP_TABLE)
            matched_rule = "heuristic:share_class"
        elif "409a" in resp_lower or "fair_market_value" in resp_lower:
            category = EndpointCategory.VALUATIONS
            capabilities.add(CapabilityTag.VALUATION_DATA)
            matched_rule = "heuristic:409a"

    # Normalize distribution
    confidence_distribution = {}
    if capabilities:
        weight = 1.0 / len(capabilities)
        for cap in capabilities:
            confidence_distribution[cap] = weight

    return ClassificationResult(
        traffic_class=traffic_class,
        category=category,
        capability_tags=tuple(sorted(capabilities)),
        confidence_distribution=confidence_distribution,
        matched_rule=matched_rule
    )


class EndpointClassifier:
    """Stateful classifier that tracks classification history."""

    def __init__(self):
        self._history: dict[str, ClassificationResult] = {}
        self.response_metadata: dict[str, dict] = {}

    @property
    def total_classified(self) -> int:
        return len(self._history)

    def classify(self, url: str, response_text: str = "") -> ClassificationResult:
        path = url.split("?")[0].split("#")[0]
        # Only use cache if no response text provided
        if path in self._history and not response_text:
            return self._history[path]
            
        result = classify_endpoint(url, response_text)
        
        if path not in self._history or response_text:
            self._history[path] = result
            log.debug(f"[EndpointClassifier] {path} → {result.traffic_class.value} | {result.category.value} | caps={len(result.capability_tags)}")
            
        if response_text:
            try:
                import json
                payload = json.loads(response_text)
                keys = list(payload.keys()) if isinstance(payload, dict) else []
                item_count = 0
                if isinstance(payload, list):
                    item_count = len(payload)
                elif isinstance(payload, dict):
                    for k in ["results", "items", "data", "investments", "valuations", "securities", "share_classes", "holdings"]:
                        if k in payload and isinstance(payload[k], list):
                            item_count = len(payload[k])
                            break
                self.response_metadata[path] = {
                    "top_level_keys": keys,
                    "item_count": item_count,
                    "content_length": len(response_text)
                }
            except Exception:
                pass

        return self._history[path]

    def get_by_category(self, category: EndpointCategory) -> list[str]:
        """Return all classified paths belonging to a category."""
        return [p for p, r in self._history.items() if r.category == category]

    def summary(self) -> dict[str, int]:
        """Return count of endpoints per category."""
        counts: dict[str, int] = {}
        for r in self._history.values():
            counts[r.category.value] = counts.get(r.category.value, 0) + 1
        return counts
