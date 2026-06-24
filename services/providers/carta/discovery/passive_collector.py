import os
import hashlib
import time
import orjson
import logging
import asyncio
import msgspec
import random
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..models.events import NetworkEvent, WebSocketFrame, WebSocketSession
from ..models.extraction import EventEnrichment, TrafficClass, CapabilityTag, ParsedResponseLayer
from .endpoint_classifier import EndpointClassifier, classify_traffic
from .interaction_tracker import InteractionProvenanceTracker
from ..intelligence.api_dependency_graph import APIDependencyTracker
from ..intelligence.schema_cluster import SchemaClusterEngine
from ..intelligence.schema_registry import SchemaRegistry

log = logging.getLogger(__name__)

class PassiveNetworkCollector:
    """
    Passive observer that ingests NetworkEvents, normalizes them, 
    detects schema drift via fingerprinting, and flushes to CAS via Bounded Async Queue.
    """
    def __init__(self, output_dir: str = "storage/network"):
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.parsed_dir = self.output_dir / "parsed"
        self.metadata_dir = self.output_dir / "metadata"
        
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        self.classifier = EndpointClassifier()
        self.schema_cluster_engine = SchemaClusterEngine()
        self.schema_registry = SchemaRegistry(self.output_dir / "schemas")
        
        # Phase 3 Trackers
        self.interaction_tracker = InteractionProvenanceTracker()
        self.dependency_tracker = APIDependencyTracker()
        self.discovered_exports = []
        
        self._ws_sessions: Dict[str, WebSocketSession] = {}
        
        # Async Queue & Backpressure
        self._queue = asyncio.Queue(maxsize=10000)
        self._dropped_events = 0
        self._batch_size = 100
        self._flush_interval = 1.0
        self._writer_task = None
        self._is_running = False
        
        self.last_network_activity_ts = time.time()
        self.active_request_count = 0
        self.active_urls = set()

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._writer_task = asyncio.create_task(self._writer_loop())
            log.info("[Collector] Started async background writer.")

    # Traffic classes that matter for network quiescence detection.
    # Static assets, CDN, microfrontend chunks, telemetry, analytics, auth,
    # config, and external services load continuously in the Carta SPA and
    # must NOT prevent wait_for_network_quiet from resolving.
    _QUIET_RELEVANT_CLASSES = frozenset({
        TrafficClass.BUSINESS_API,
        TrafficClass.GRAPHQL,
        TrafficClass.EXPORT,
    })

    def request_started(self, url: str, headers: Optional[dict] = None, body: Optional[bytes] = None):
        tc = classify_traffic(url)
        if tc in self._QUIET_RELEVANT_CLASSES:
            self.active_request_count += 1
            self.active_urls.add(url)
            self.last_network_activity_ts = time.time()
        
        # Track dependencies and interaction triggers regardless of class
        self.dependency_tracker.observe_request(url, headers or {}, body)
        self.interaction_tracker.record_endpoint_triggered(url)

    def request_finished(self, url: str):
        tc = classify_traffic(url)
        if tc in self._QUIET_RELEVANT_CLASSES:
            self.active_request_count = max(0, self.active_request_count - 1)
            self.active_urls.discard(url)
            self.last_network_activity_ts = time.time()

    async def wait_for_network_quiet(self, silence_ms: int = 1200, timeout_ms: int = 8000):
        start_time = time.time()
        silence_sec = silence_ms / 1000.0
        timeout_sec = timeout_ms / 1000.0

        while True:
            now = time.time()
            if now - start_time > timeout_sec:
                log.warning(f"[Collector] wait_for_network_quiet timeout reached. Count: {self.active_request_count}. URLs: {list(self.active_urls)[:5]}")
                return

            delta = now - self.last_network_activity_ts
            if self.active_request_count == 0 and delta > silence_sec:
                return

            await asyncio.sleep(0.1)

    def _extract_type_schema(self, obj: Any) -> Any:
        """Recursively extracts the structural type schema from a JSON payload."""
        if isinstance(obj, dict):
            # Sort keys canonically
            return {k: self._extract_type_schema(v) for k, v in sorted(obj.items()) if k not in ['id', 'uuid', 'timestamp', 'created_at', 'updated_at']}
        elif isinstance(obj, list):
            if len(obj) > 0:
                # Assume homogenous list
                return [self._extract_type_schema(obj[0])]
            return []
        elif obj is None:
            return "null"
        elif isinstance(obj, bool):
            return "bool"
        elif isinstance(obj, int):
            return "int"
        elif isinstance(obj, float):
            return "float"
        else:
            return "string"

    async def process_event(self, event: NetworkEvent):
        """
        Ingest a Canonical NetworkEvent.
        Order: Capture -> Normalize -> Parse -> Schema Fingerprint -> Classification -> Clustering -> Enrichment -> Persist
        """
        # 1. Early Telemetry Bypass
        traffic_class = classify_traffic(event.url)
        
        if traffic_class == TrafficClass.EXPORT:
            entity_id = getattr(self.interaction_tracker, '_current_entity_id', None)
            org_id = getattr(self.interaction_tracker, '_current_organization_id', None)
            self.discovered_exports.append({
                "url": event.url,
                "entity_id": entity_id,
                "organization_id": org_id,
                "headers": event.request_headers,
                "method": event.method
            })
        if traffic_class in (TrafficClass.TELEMETRY, TrafficClass.ANALYTICS):
            if random.random() > 0.05:
                return  # Drop 95% of telemetry
            # Minimal persistence
            event.enrichment = EventEnrichment(traffic_class=traffic_class)
            try:
                self._queue.put_nowait((event, None, None))
            except asyncio.QueueFull:
                self._dropped_events += 1
            return

        # 2. Parse & Normalize
        response_text = ""
        payload = None
        parsed_layer = None
        schema_fingerprint = None
        
        if event.response_body:
            try:
                response_text = event.response_body.decode('utf-8', 'ignore')
                payload = orjson.loads(event.response_body)
                
                # 3. Structural Fingerprinting
                type_schema = self._extract_type_schema(payload)
                schema_str = orjson.dumps(type_schema).decode()
                schema_fingerprint = hashlib.sha256(schema_str.encode()).hexdigest()
                
                # Create ParsedLayer
                top_keys = tuple(sorted(payload.keys())) if isinstance(payload, dict) else ()
                parsed_layer = ParsedResponseLayer(
                    parsed_ref="", # Will be set to hash later
                    top_level_keys=top_keys,
                    schema_trie_hash=schema_fingerprint,
                    normalized_schema_hash=schema_fingerprint,
                )
            except Exception:
                pass

        # 4. Classification & Capability Inference
        classification = self.classifier.classify(event.url, response_text)
        
        # 5. Schema Clustering
        schema_cluster_id = None
        if schema_fingerprint:
            schema_cluster_id = self.schema_cluster_engine.cluster_response(
                schema_fingerprint=schema_fingerprint,
                capability_tags=classification.capability_tags,
                traversal_context=None,
                graphql_operation=None,
                traffic_class=traffic_class
            )
            # Register schema
            self.schema_registry.register_schema(
                structural_fingerprint=schema_fingerprint,
                top_level_keys=parsed_layer.top_level_keys if parsed_layer else (),
                semantic_cluster_id=schema_cluster_id
            )

        # 6. Semantic Enrichment
            # Track response dependencies if valid payload
            if traffic_class == TrafficClass.BUSINESS_API and isinstance(payload, (dict, list)):
                # If it's a list, wrap it so the dependency tracker can process it
                payload_dict = payload if isinstance(payload, dict) else {"items": payload}
                self.dependency_tracker.observe_response(event.url, payload_dict)
                
            event.enrichment = EventEnrichment(
                schema_fingerprint=schema_fingerprint,
                traffic_class=traffic_class,
                endpoint_category=classification.category,
                capability_tags=classification.capability_tags,
                confidence_distribution=classification.confidence_distribution,
                schema_cluster_id=schema_cluster_id,
                confidence_score=classification.confidence_distribution.get(CapabilityTag.PORTFOLIO_DATA, 0.0)
            )

        # 7. Add to queue as tuple (event, parsed_layer, payload)
        try:
            self._queue.put_nowait((event, parsed_layer, payload))
        except asyncio.QueueFull:
            self._dropped_events += 1
            if self._dropped_events % 100 == 0:
                log.warning(f"[Collector] Queue full! Dropped {self._dropped_events} events so far.")

    async def process_ws_frame(self, req_id: str, timestamp: float, is_sent: bool, payload_data: str):
        if req_id not in self._ws_sessions:
            self._ws_sessions[req_id] = WebSocketSession(socket_id=req_id, url="", opened_at=timestamp, frames=[])
        try:
            payload_bytes = payload_data.encode('utf-8')
        except AttributeError:
            payload_bytes = b""
        frame = WebSocketFrame(timestamp=timestamp, is_sent=is_sent, payload=payload_bytes)
        self._ws_sessions[req_id].frames.append(frame)

    async def _writer_loop(self):
        buffer = []
        while self._is_running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self._flush_interval)
                buffer.append(item)
                if len(buffer) >= self._batch_size:
                    await self._flush_buffer(buffer)
                    buffer.clear()
            except asyncio.TimeoutError:
                if buffer:
                    await self._flush_buffer(buffer)
                    buffer.clear()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[Collector] Error in writer loop: {e}", exc_info=True)

    async def _flush_buffer(self, buffer: list):
        """Flush to Content-Addressed Storage (CAS)."""
        try:
            for item in buffer:
                ev, parsed_layer, payload = item
                
                # Determine hash identity
                body_hash = None
                if ev.response_body:
                    body_hash = hashlib.sha256(ev.response_body).hexdigest()
                
                # Determine identity (use body_hash or fallback to req_id+ts)
                identity = body_hash if body_hash else f"{ev.request_id}_{int(ev.timestamp * 1000)}"
                
                # Tier 3: Raw Blobs
                if body_hash and ev.response_body:
                    raw_file = self.raw_dir / f"{body_hash}.bin"
                    if not raw_file.exists():
                        raw_file.write_bytes(ev.response_body)
                
                # Tier 2: Parsed Semantic Cache (Msgpack)
                if parsed_layer and body_hash and payload:
                    parsed_layer.parsed_ref = body_hash
                    parsed_file = self.parsed_dir / f"{body_hash}.msgpack"
                    if not parsed_file.exists():
                        parsed_data = msgspec.msgpack.encode({"layer": msgspec.to_builtins(parsed_layer), "data": payload})
                        parsed_file.write_bytes(parsed_data)
                
                # Tier 1: Metadata
                meta_file = self.metadata_dir / f"{identity}.json"
                
                # Strip raw body to save metadata space
                ev_copy = msgspec.json.decode(msgspec.json.encode(ev), type=NetworkEvent)
                ev_copy.response_body = None
                
                ev_dict = msgspec.to_builtins(ev_copy)
                meta_file.write_bytes(orjson.dumps(ev_dict, option=orjson.OPT_INDENT_2))

            log.info(f"[Collector] Flushed {len(buffer)} events to CAS in {self.output_dir}. QSize: {self._queue.qsize()} | Dropped: {self._dropped_events}")
            
        except Exception as e:
            log.error(f"[Collector] Failed to flush to CAS: {e}", exc_info=True)

    async def shutdown(self):
        log.info("[Collector] Shutting down...")
        self._is_running = False
        buffer = []
        while not self._queue.empty():
            try:
                buffer.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if buffer:
            await self._flush_buffer(buffer)
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass

