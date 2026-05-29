import os
import json
import uuid
import logging
import hashlib
from typing import Dict, Any
from .request_classifier import classify_request, should_ignore_request, RequestType
from .graphql_registry import GraphQLRegistry

log = logging.getLogger(__name__)

SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "x-csrf-token",
    "x-api-key"
}

def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    sanitized = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADERS:
            sanitized[k] = "***REDACTED***"
        else:
            sanitized[k] = v
    return sanitized

def compute_payload_fingerprint(payload: Any) -> str:
    if not payload:
        return ""
    try:
        # Sort keys to ensure stable hashes for identical payloads
        dumped = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(dumped.encode()).hexdigest()
    except Exception:
        return ""

class NetworkInterceptor:
    def __init__(self, output_dir: str, max_capture_bytes: int):
        self.output_dir = output_dir
        self.max_capture_bytes = max_capture_bytes
        self.graphql_registry = GraphQLRegistry()
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.graphql_requests_path = os.path.join(self.output_dir, "graphql_requests.jsonl")
        self.graphql_responses_path = os.path.join(self.output_dir, "graphql_responses.jsonl")
        self.exports_path = os.path.join(self.output_dir, "exports.jsonl")
        self.failed_requests_path = os.path.join(self.output_dir, "failed_requests.jsonl")
        self.request_map_path = os.path.join(self.output_dir, "request_map.json")
        
        # In-memory map to correlate requests and responses by URL/Network Request ID
        # Playwright Request object has no built-in ID that maps nicely across events sometimes,
        # but we can monkey-patch or use a weakref/URL mapping. 
        # Actually, Playwright's request object reference stays the same.
        self.request_map = {}

    def _append_jsonl(self, path: str, data: dict):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            log.error(f"[Interceptor] Failed to write to {path}: {e}")

    def _save_request_map(self):
        try:
            with open(self.request_map_path, "w", encoding="utf-8") as f:
                json.dump(self.request_map, f, indent=2)
        except Exception:
            pass

    async def handle_request(self, request):
        url = request.url
        if should_ignore_request(url):
            return

        req_type = classify_request(url)
        if req_type == RequestType.UNKNOWN:
            return

        request_id = uuid.uuid4().hex
        # Store in map using Playwright's request object as key or URL + method
        # A robust way is to just attach it to the request object directly if possible,
        # but Playwright Request objects are frozen. We'll use id(request).
        self.request_map[id(request)] = request_id

        headers = sanitize_headers(request.headers)
        
        metadata = {
            "request_id": request_id,
            "url": url,
            "method": request.method,
            "type": req_type.value,
            "headers": headers,
        }

        # Handle Payload
        if request.post_data:
            metadata["payload_size"] = len(request.post_data.encode("utf-8"))
            if req_type == RequestType.GRAPHQL:
                op_details = self.graphql_registry.extract_operation_details(request.post_data)
                metadata["operation_name"] = op_details.get("operationName")
                
                # Fingerprint variables
                vars_fingerprint = compute_payload_fingerprint(op_details.get("variables", {}))
                metadata["variables_hash"] = vars_fingerprint
                
                self.graphql_registry.track_request(
                    metadata["operation_name"], 
                    op_details.get("variables", {})
                )
                
                # Log to graphql requests
                self._append_jsonl(self.graphql_requests_path, metadata)
            else:
                self._append_jsonl(self.exports_path, metadata)
                
    async def handle_response(self, response):
        request = response.request
        url = request.url
        
        request_id = self.request_map.get(id(request))
        if not request_id:
            # We didn't capture the request (ignored or unknown)
            return
            
        req_type = classify_request(url)
        status = response.status
        
        metadata = {
            "request_id": request_id,
            "url": url,
            "status": status,
            "type": req_type.value,
        }
        
        if status >= 400:
            self._append_jsonl(self.failed_requests_path, metadata)
            return

        try:
            # Check content length
            headers = response.headers
            content_length = int(headers.get("content-length", 0))
            
            # If server didn't provide content-length, we might have to read it.
            # Wait for body to be available. Playwright response.body() reads the buffer.
            body_bytes = await response.body()
            metadata["response_size"] = len(body_bytes)
            
            if req_type == RequestType.GRAPHQL:
                if len(body_bytes) <= self.max_capture_bytes:
                    body_json = await response.json()
                    
                    if "data" in body_json and isinstance(body_json["data"], dict):
                        metadata["root_keys"] = list(body_json["data"].keys())
                        
                    # Find operation name from registry map if possible, 
                    # but we didn't store it in a way we can retrieve easily without looking up.
                    # We can parse the request again to find it.
                    if request.post_data:
                        op_details = self.graphql_registry.extract_operation_details(request.post_data)
                        op_name = op_details.get("operationName")
                        metadata["operation_name"] = op_name
                        self.graphql_registry.track_response(op_name, body_json)
                        
                        # Fingerprint response
                        metadata["response_hash"] = compute_payload_fingerprint(body_json)
                        
                else:
                    metadata["error"] = "response_too_large_truncated"
                    
                self._append_jsonl(self.graphql_responses_path, metadata)
                
            elif req_type == RequestType.EXPORT:
                metadata["response_size"] = len(body_bytes)
                self._append_jsonl(self.exports_path, metadata)

        except Exception as e:
            metadata["error"] = str(e)
            self._append_jsonl(self.failed_requests_path, metadata)
