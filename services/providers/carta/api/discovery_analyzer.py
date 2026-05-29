import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

from .replay_client import ReplayResult, CartaReplayStrategy

log = logging.getLogger(__name__)

class DiscoveryAnalyzer:
    """
    Separated Analyzer that incrementally monitors, fingerprints,
    and merges observed API schema metadata to output/carta/api_intelligence.json.
    """

    def __init__(self, output_path: str = "output/carta/api_intelligence.json"):
        self.output_path = output_path
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

    async def analyze(self, endpoint: str, result: ReplayResult, method: str = "GET") -> None:
        """Processes a ReplayResult, fingerprints the shape, and merges metadata incrementally."""
        if result.status_code != 200 or not result.payload:
            return

        log.info(f"[DiscoveryAnalyzer] Analyzing contract structure for: {endpoint}")
        
        # Determine root response keys
        response_keys = []
        if isinstance(result.payload, dict):
            response_keys = sorted(list(result.payload.keys()))
        elif isinstance(result.payload, list) and len(result.payload) > 0 and isinstance(result.payload[0], dict):
            response_keys = sorted(list(result.payload[0].keys()))

        # Load existing intelligence
        intelligence = self._load_intelligence()

        # Retrieve or initialize endpoint metadata
        meta = intelligence.setdefault(endpoint, {
            "methods_seen": [],
            "response_keys": [],
            "shape_hashes": [],
            "supports_httpx": False,
            "requires_csrf": True,
            "last_seen": ""
        })

        # Incremental merges
        if method not in meta["methods_seen"]:
            meta["methods_seen"].append(method)

        for key in response_keys:
            if key not in meta["response_keys"]:
                meta["response_keys"].append(key)
        meta["response_keys"].sort()

        if result.shape_hash and result.shape_hash not in meta["shape_hashes"]:
            meta["shape_hashes"].append(result.shape_hash)

        if result.strategy_used == CartaReplayStrategy.HTTPX:
            meta["supports_httpx"] = True

        meta["last_seen"] = datetime.utcnow().isoformat()

        # Save back
        self._save_intelligence(intelligence)
        log.info(f"[DiscoveryAnalyzer] Dynamic metadata successfully merged for: {endpoint}")

    def _load_intelligence(self) -> Dict[str, Any]:
        """Safely reads the intelligence database."""
        if not os.path.exists(self.output_path):
            return {}
        try:
            with open(self.output_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"[DiscoveryAnalyzer] Failed to read {self.output_path}: {e}")
            return {}

    def _save_intelligence(self, data: Dict[str, Any]) -> None:
        """Safely serializes metadata with indentation."""
        try:
            # Temporary file write + atomic rename for durability
            temp_path = self.output_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.output_path):
                os.remove(self.output_path)
            os.rename(temp_path, self.output_path)
        except Exception as e:
            log.error(f"[DiscoveryAnalyzer] Failed to save {self.output_path}: {e}")
