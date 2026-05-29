import logging
import time
import base64
import zlib
import gzip
import asyncio
from typing import Dict, Any
from playwright.async_api import Page, CDPSession
from ..models.events import NetworkEvent

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

log = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/json",
    "application/graphql-response+json",
    "text/json",
}

class CDPPageObserver:
    def __init__(self, page: Page, cdp: CDPSession, network_collector):
        self.page = page
        self.cdp = cdp
        self.network_collector = network_collector
        self._pending_requests = {}
        
        # Bound methods for strong references (avoiding garbage collected lambdas)
        self._on_req_bound = self._on_request_will_be_sent
        self._on_res_bound = self._on_response_received
        self._on_load_bound = self._on_loading_finished
        self._on_ws_recv_bound = self._on_ws_frame_received
        self._on_ws_sent_bound = self._on_ws_frame_sent
        
    def attach(self):
        self.cdp.on("Network.requestWillBeSent", self._on_req_bound)
        self.cdp.on("Network.responseReceived", self._on_res_bound)
        self.cdp.on("Network.loadingFinished", self._on_load_bound)
        self.cdp.on("Network.webSocketFrameReceived", self._on_ws_recv_bound)
        self.cdp.on("Network.webSocketFrameSent", self._on_ws_sent_bound)

    def detach(self):
        try:
            self.cdp.remove_listener("Network.requestWillBeSent", self._on_req_bound)
            self.cdp.remove_listener("Network.responseReceived", self._on_res_bound)
            self.cdp.remove_listener("Network.loadingFinished", self._on_load_bound)
            self.cdp.remove_listener("Network.webSocketFrameReceived", self._on_ws_recv_bound)
            self.cdp.remove_listener("Network.webSocketFrameSent", self._on_ws_sent_bound)
        except Exception:
            pass

    def _on_request_will_be_sent(self, event: dict):
        req = event.get("request", {})
        req_id = event.get("requestId")
        self._pending_requests[req_id] = {
            "url": req.get("url"),
            "method": req.get("method"),
            "initiator": event.get("initiator", {}),
            "resource_type": event.get("type", ""),
            "request_headers": req.get("headers", {}),
            "request_body": req.get("postData", "").encode('utf-8') if req.get("hasPostData") else None,
            "timestamp": event.get("timestamp", time.time())
        }
        if self.network_collector and hasattr(self.network_collector, "request_started"):
            self.network_collector.request_started(req.get("url", ""))

    def _on_response_received(self, event: dict):
        res = event.get("response", {})
        req_id = event.get("requestId")
        if req_id in self._pending_requests:
            self._pending_requests[req_id].update({
                "status": res.get("status", 0),
                "response_headers": {k.lower(): v for k, v in res.get("headers", {}).items()},
                "timing": res.get("timing", {})
            })

    def _on_loading_finished(self, event: dict):
        req_id = event.get("requestId")
        if req_id in self._pending_requests:
            url = self._pending_requests[req_id].get("url", "")
            if self.network_collector and hasattr(self.network_collector, "request_finished"):
                self.network_collector.request_finished(url)
                
        # Fire off an async task to fetch body without blocking the listener loop
        asyncio.create_task(self._process_loading_finished(event))

    async def _process_loading_finished(self, event: dict):
        req_id = event.get("requestId")
        if req_id not in self._pending_requests:
            return
            
        pending = self._pending_requests.pop(req_id)
        headers = pending.get("response_headers", {})
        content_type = headers.get("content-type", "").lower().split(";")[0].strip()
        
        # 1. MIME Filtering BEFORE decompression or body fetching (Mistake #1)
        if content_type and not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
            return
            
        response_body = None
        try:
            body_res = await self.cdp.send("Network.getResponseBody", {"requestId": req_id})
            body_str = body_res.get("body", "")
            is_base64 = body_res.get("base64Encoded", False)
            
            if body_str:
                # 2. Base64 Decode if needed
                if is_base64:
                    raw_bytes = base64.b64decode(body_str)
                    
                    # 3. Inspect Content-Encoding and Conditionally Decompress
                    encoding = headers.get("content-encoding", "").lower()
                    if encoding == "gzip":
                        try:
                            raw_bytes = gzip.decompress(raw_bytes)
                        except Exception as e: 
                            log.debug(f"Failed to decompress gzip: {e}")
                    elif encoding == "br" and HAS_BROTLI:
                        try:
                            raw_bytes = brotli.decompress(raw_bytes)
                        except Exception as e:
                            log.debug(f"Failed to decompress brotli: {e}")
                    elif encoding == "deflate":
                        try:
                            raw_bytes = zlib.decompress(raw_bytes)
                        except Exception as e:
                            log.debug(f"Failed to decompress deflate: {e}")
                else:
                    # If not base64 encoded, Playwright CDP already decompressed and decoded it as string
                    raw_bytes = body_str.encode('utf-8')
                        
                response_body = raw_bytes
        except Exception:
            # Endpoint may not have a body or failed to fetch
            pass
            
        network_event = NetworkEvent(
            request_id=req_id,
            url=pending.get("url", ""),
            method=pending.get("method", ""),
            status=pending.get("status", 0),
            timestamp=pending.get("timestamp", time.time()),
            resource_type=pending.get("resource_type", ""),
            initiator=pending.get("initiator", {}),
            request_headers=pending.get("request_headers", {}),
            response_headers=headers,
            request_body=pending.get("request_body"),
            response_body=response_body
        )
        
        if self.network_collector and hasattr(self.network_collector, "process_event"):
            await self.network_collector.process_event(network_event)

    def _on_ws_frame_received(self, event: dict):
        req_id = event.get("requestId")
        timestamp = event.get("timestamp", time.time())
        res = event.get("response", {})
        payload_data = res.get("payloadData", "")
        if self.network_collector and hasattr(self.network_collector, "process_ws_frame"):
            # Don't block, fire async
            asyncio.create_task(self.network_collector.process_ws_frame(req_id, timestamp, False, payload_data))

    def _on_ws_frame_sent(self, event: dict):
        req_id = event.get("requestId")
        timestamp = event.get("timestamp", time.time())
        res = event.get("response", {})
        payload_data = res.get("payloadData", "")
        if self.network_collector and hasattr(self.network_collector, "process_ws_frame"):
            asyncio.create_task(self.network_collector.process_ws_frame(req_id, timestamp, True, payload_data))

class CDPPageRegistry:
    def __init__(self, network_collector):
        self.network_collector = network_collector
        self.observers: Dict[Page, CDPPageObserver] = {}

    async def register_page(self, page: Page):
        if page in self.observers:
            return
        log.info(f"[CDPPageRegistry] Attaching CDP session to page {page.url}")
        cdp = await page.context.new_cdp_session(page)
        
        await cdp.send("Network.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Page.enable")
        
        observer = CDPPageObserver(page, cdp, self.network_collector)
        observer.attach()
        self.observers[page] = observer

    def unregister_page(self, page: Page):
        if page in self.observers:
            log.info("[CDPPageRegistry] Detaching CDP session.")
            self.observers[page].detach()
            del self.observers[page]
