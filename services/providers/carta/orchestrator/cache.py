import os
import json
import time
import hashlib
import logging
from typing import Optional, Any, Dict, TypedDict

log = logging.getLogger(__name__)

class CacheEntry(TypedDict):
    metadata: Dict[str, Any]
    extracted_at: float
    version: str
    checksum: str
    data: Any

class CacheManager:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_path(self, name: str) -> str:
        return os.path.join(self.cache_dir, f"{name}.json")

    def _generate_checksum(self, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, name: str, ttl_seconds: int) -> Optional[Any]:
        path = self._get_path(name)
        if not os.path.exists(path):
            log.debug(f"[Cache] Cache miss: {name} does not exist.")
            return None
        
        try:
            with open(path, "r") as f:
                entry: CacheEntry = json.load(f)
            
            # Check TTL
            age = time.time() - entry["extracted_at"]
            if age > ttl_seconds:
                log.debug(f"[Cache] Cache stale: {name} expired (age: {age:.1f}s, TTL: {ttl_seconds}s).")
                return None
            
            # Verify Checksum
            expected_checksum = self._generate_checksum(entry["data"])
            if entry["checksum"] != expected_checksum:
                log.warning(f"[Cache] Checksum mismatch for {name}. Treating as cache miss.")
                return None
            
            log.debug(f"[Cache] Cache hit (fresh): {name} (age: {age:.1f}s).")
            return entry["data"]
        except Exception as e:
            log.error(f"[Cache] Error reading cache file for {name}: {e}")
            return None

    def set(self, name: str, data: Any, version: str = "1.0", metadata: Optional[Dict[str, Any]] = None) -> None:
        path = self._get_path(name)
        try:
            checksum = self._generate_checksum(data)
            entry: CacheEntry = {
                "metadata": metadata or {},
                "extracted_at": time.time(),
                "version": version,
                "checksum": checksum,
                "data": data
            }
            with open(path, "w") as f:
                json.dump(entry, f, indent=2)
            log.debug(f"[Cache] Cached {name} successfully.")
        except Exception as e:
            log.error(f"[Cache] Failed to write cache for {name}: {e}")
