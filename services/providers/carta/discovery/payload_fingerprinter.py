"""
Payload Fingerprinter.

Generates stable, privacy-safe fingerprints of API response shapes
for schema drift detection and regression monitoring.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Fingerprint(BaseModel):
    endpoint: str
    method: str
    shape_hash: str
    root_keys: list[str]
    first_seen: datetime
    last_seen: datetime
    observation_count: int = 1


class PayloadFingerprinter:
    """
    Tracks response shape fingerprints per endpoint to detect schema drift.
    Never stores actual payload values — only structural hashes.
    """

    def __init__(self):
        self._fingerprints: dict[str, Fingerprint] = {}
        self._drift_log: list[dict] = []

    @staticmethod
    def compute_shape_hash(payload: Any) -> Optional[str]:
        """Generate a deterministic SHA256 hash of the response root-level keys."""
        if payload is None:
            return None
        try:
            if isinstance(payload, dict):
                keys = sorted(payload.keys())
            elif isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
                keys = sorted(payload[0].keys())
            else:
                return None
            return hashlib.sha256(",".join(keys).encode("utf-8")).hexdigest()
        except Exception:
            return None

    @staticmethod
    def extract_root_keys(payload: Any) -> list[str]:
        if isinstance(payload, dict):
            return sorted(payload.keys())
        if isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
            return sorted(payload[0].keys())
        return []

    def fingerprint(self, endpoint: str, method: str, payload: Any) -> Optional[Fingerprint]:
        """Record a fingerprint observation. Returns the fingerprint and detects drift."""
        shape_hash = self.compute_shape_hash(payload)
        if not shape_hash:
            return None

        cache_key = f"{method}:{endpoint}"
        now = datetime.utcnow()
        root_keys = self.extract_root_keys(payload)

        existing = self._fingerprints.get(cache_key)
        if existing:
            if existing.shape_hash != shape_hash:
                # DRIFT DETECTED
                drift_event = {
                    "endpoint": endpoint,
                    "method": method,
                    "old_hash": existing.shape_hash,
                    "new_hash": shape_hash,
                    "old_keys": existing.root_keys,
                    "new_keys": root_keys,
                    "detected_at": now.isoformat(),
                }
                self._drift_log.append(drift_event)
                log.warning(
                    f"[PayloadFingerprinter] SCHEMA DRIFT detected on {method} {endpoint}: "
                    f"old={existing.shape_hash[:12]}… new={shape_hash[:12]}…"
                )
                # Update to new shape
                existing.shape_hash = shape_hash
                existing.root_keys = root_keys
                existing.last_seen = now
                existing.observation_count += 1
                return existing
            else:
                existing.last_seen = now
                existing.observation_count += 1
                return existing
        else:
            fp = Fingerprint(
                endpoint=endpoint,
                method=method,
                shape_hash=shape_hash,
                root_keys=root_keys,
                first_seen=now,
                last_seen=now,
            )
            self._fingerprints[cache_key] = fp
            log.info(f"[PayloadFingerprinter] New fingerprint for {method} {endpoint}: {shape_hash[:12]}…")
            return fp

    @property
    def drift_events(self) -> list[dict]:
        return list(self._drift_log)

    def has_drifted(self, method: str, endpoint: str) -> bool:
        return any(
            d["endpoint"] == endpoint and d["method"] == method
            for d in self._drift_log
        )

    def to_summary(self) -> dict:
        result = {}
        for key, fp in self._fingerprints.items():
            result[key] = {
                "shape_hash": fp.shape_hash,
                "root_keys": fp.root_keys,
                "first_seen": fp.first_seen.isoformat(),
                "last_seen": fp.last_seen.isoformat(),
                "observation_count": fp.observation_count,
            }
        return result
