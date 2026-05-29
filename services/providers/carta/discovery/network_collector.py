"""
Network Collector — Autonomous API Intelligence Harvester.

Hooks into Playwright page events to passively capture all API traffic,
classify endpoints, infer schemas, fingerprint payloads, and detect pagination.

CRITICAL: This module NEVER stores full financial payloads or PII.
It only persists structural metadata (schemas, keys, hashes, categories).
"""

import os
import re
import json
import logging
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from typing import Optional
from pydantic import BaseModel

from .endpoint_classifier import EndpointClassifier, EndpointCategory
from .schema_inference import SchemaInferenceEngine
from .payload_fingerprinter import PayloadFingerprinter
from .pagination_engine import detect_pagination, PaginationState

log = logging.getLogger(__name__)

# Domains / patterns to completely ignore
_IGNORE_PATTERNS = re.compile(
    r"(\.js$|\.css$|\.png$|\.jpg$|\.jpeg$|\.gif$|\.svg$|\.woff|\.ttf|"
    r"fonts\.|analytics\.|sentry\.|datadog\.|segment\.|hotjar\.|"
    r"google-analytics\.|googletagmanager\.|facebook\.com|doubleclick|"
    r"cdn\.segment|launchdarkly|amplitude|mixpanel|intercom|"
    r"__webpack|chunk\.|manifest\.|favicon|sw\.js)",
    re.IGNORECASE,
)

# Content types we care about
_API_CONTENT_TYPES = {"application/json", "text/json"}


class CapturedEndpoint(BaseModel):
    url: str
    path: str
    method: str
    status: int
    content_type: Optional[str] = None
    query_params: dict = {}
    response_keys: list[str] = []
    response_size: int = 0
    service_domain: str = ""
    category: str = "unknown"
    pagination: Optional[PaginationState] = None
    shape_hash: Optional[str] = None
    captured_at: str = ""


class NetworkCollector:
    """
    Autonomous API Intelligence Harvester.
    Attaches to a Playwright page and passively collects endpoint intelligence.
    """

    def __init__(self, output_dir: str = "output/carta/discovery"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.classifier = EndpointClassifier()
        self.schema_engine = SchemaInferenceEngine()
        self.fingerprinter = PayloadFingerprinter()

        self._endpoints_path = os.path.join(self.output_dir, "discovered_endpoints.jsonl")
        self._intelligence_path = os.path.join(self.output_dir, "api_intelligence.json")
        self._schemas_path = os.path.join(self.output_dir, "inferred_schemas.json")
        self._fingerprints_path = os.path.join(self.output_dir, "fingerprints.json")
        self._drift_path = os.path.join(self.output_dir, "drift_events.jsonl")

        self._capture_count = 0

    def attach(self, page):
        """Attach request/response listeners to a Playwright page."""
        page.on("response", self._on_response)
        log.info("[NetworkCollector] Attached to page for passive API traffic capture.")

    def detach(self, page):
        """Detach listeners."""
        try:
            page.remove_listener("response", self._on_response)
        except Exception:
            pass
        log.info("[NetworkCollector] Detached from page.")

    async def _on_response(self, response):
        """Handle a Playwright response event."""
        try:
            request = response.request
            url = request.url

            # Filter out noise
            if _IGNORE_PATTERNS.search(url):
                return

            # Only process API-like responses
            content_type = response.headers.get("content-type", "")
            is_json = any(ct in content_type.lower() for ct in _API_CONTENT_TYPES)
            if not is_json:
                return

            method = request.method
            status = response.status
            parsed = urlparse(url)
            path = parsed.path
            domain = parsed.netloc
            query_params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}

            # Classify
            classification = self.classifier.classify(url)

            # Skip internal noise
            if classification.category == EndpointCategory.INTERNAL:
                return

            # Try to read response body for schema inference
            payload = None
            response_size = 0
            response_keys = []

            try:
                body = await response.body()
                response_size = len(body)

                # Only parse JSON bodies under 500KB to avoid memory issues
                if response_size < 500_000 and status == 200:
                    try:
                        payload = await response.json()
                    except Exception:
                        pass

                if payload:
                    if isinstance(payload, dict):
                        response_keys = sorted(payload.keys())
                    elif isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
                        response_keys = sorted(payload[0].keys())
            except Exception:
                pass

            # Schema inference (structural only)
            if payload and status == 200:
                self.schema_engine.infer(path, method, status, payload)

            # Fingerprint (shape hash only)
            shape_hash = None
            if payload and status == 200:
                fp = self.fingerprinter.fingerprint(path, method, payload)
                if fp:
                    shape_hash = fp.shape_hash

            # Pagination detection
            pagination = None
            if payload and status == 200:
                pagination = detect_pagination(payload, query_params)

            # Build captured endpoint record
            captured = CapturedEndpoint(
                url=url,
                path=path,
                method=method,
                status=status,
                content_type=content_type,
                query_params=query_params,
                response_keys=response_keys,
                response_size=response_size,
                service_domain=domain,
                category=classification.category.value,
                pagination=pagination,
                shape_hash=shape_hash,
                captured_at=datetime.utcnow().isoformat(),
            )

            # Persist to JSONL
            self._append_jsonl(self._endpoints_path, captured.model_dump())
            self._capture_count += 1

            if self._capture_count % 10 == 0:
                self._persist_intelligence()

            log.info(
                f"[NetworkCollector] Captured: {method} {path} "
                f"→ {classification.category.value} "
                f"(status={status}, keys={len(response_keys)}, size={response_size})"
            )

        except Exception as e:
            log.debug(f"[NetworkCollector] Error processing response: {e}")

    def _append_jsonl(self, path: str, data: dict):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except Exception as e:
            log.error(f"[NetworkCollector] Failed to write to {path}: {e}")

    def _persist_intelligence(self):
        """Flush accumulated intelligence to disk."""
        try:
            # Classification summary
            intelligence = {
                "classification_summary": self.classifier.summary(),
                "total_captured": self._capture_count,
                "last_updated": datetime.utcnow().isoformat(),
                "endpoints_by_category": {},
            }
            for cat in EndpointCategory:
                paths = self.classifier.get_by_category(cat)
                if paths:
                    intelligence["endpoints_by_category"][cat.value] = paths

            with open(self._intelligence_path, "w", encoding="utf-8") as f:
                json.dump(intelligence, f, indent=2, default=str)

            # Schemas
            with open(self._schemas_path, "w", encoding="utf-8") as f:
                json.dump(self.schema_engine.to_summary(), f, indent=2, default=str)

            # Fingerprints
            with open(self._fingerprints_path, "w", encoding="utf-8") as f:
                json.dump(self.fingerprinter.to_summary(), f, indent=2, default=str)

            # Drift events
            for drift in self.fingerprinter.drift_events:
                self._append_jsonl(self._drift_path, drift)

        except Exception as e:
            log.error(f"[NetworkCollector] Failed to persist intelligence: {e}")

    def flush(self):
        """Force-flush all accumulated intelligence to disk."""
        self._persist_intelligence()
        log.info(
            f"[NetworkCollector] Flushed intelligence: "
            f"{self._capture_count} endpoints captured, "
            f"{len(self.schema_engine.all_schemas())} schemas inferred, "
            f"{len(self.fingerprinter.drift_events)} drift events."
        )

    def summary(self) -> dict:
        return {
            "total_captured": self._capture_count,
            "classification": self.classifier.summary(),
            "schemas_inferred": len(self.schema_engine.all_schemas()),
            "drift_events": len(self.fingerprinter.drift_events),
        }
