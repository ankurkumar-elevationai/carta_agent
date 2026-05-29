from typing import Any, List
import re

class URLHarvester:
    """
    Recursively scans JSON payloads to extract nested URLs.
    Targets keys matching: *_url, *_api_url, root_url.
    """

    # Regex to match target keys
    _KEY_PATTERN = re.compile(r"(_url|_api_url|^root_url)$", re.I)

    @classmethod
    def harvest(cls, payload: Any) -> List[str]:
        """Extracts all matching URLs from a payload."""
        urls = set()

        def _walk(obj: Any):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(k, str) and cls._KEY_PATTERN.search(k) and isinstance(v, str) and v.startswith("http"):
                        urls.add(v)
                    else:
                        _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(payload)
        return list(urls)
