import logging
import asyncio
from typing import Any, Optional
from collections import deque

log = logging.getLogger(__name__)

class TraversalContext:
    def __init__(self, url: str, entity_id: str, depth: int = 0, parent_url: Optional[str] = None):
        self.url = url
        self.entity_id = entity_id
        self.depth = depth
        self.parent_url = parent_url

class TraversalMiddleware:
    """
    Middleware for recursive capability traversal.
    Handles queueing, cycle prevention, rate limit backoffs, and `*_url` extraction.
    """
    
    def __init__(self, max_depth: int = 5):
        self.visited = set()
        self.queue: deque[TraversalContext] = deque()
        self.max_depth = max_depth

    def enqueue(self, context: TraversalContext):
        """Add a route to the traversal queue if not visited."""
        # Normalize URL to prevent dupes (strip pagination/timestamps if needed)
        normalized = context.url.split("?")[0]
        if normalized not in self.visited and context.depth <= self.max_depth:
            self.queue.append(context)
            self.visited.add(normalized)
            log.debug(f"[Traversal] Enqueued: {context.url} (depth={context.depth})")

    def dequeue(self) -> Optional[TraversalContext]:
        if self.queue:
            return self.queue.popleft()
        return None

    def has_next(self) -> bool:
        return len(self.queue) > 0

    def extract_urls(self, payload: Any, current_context: TraversalContext) -> list[TraversalContext]:
        """
        Recursively extract capabilities from payload via keys ending in `_url` or `_link`.
        """
        extracted = []
        
        def _walk(obj: Any):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(k, str) and (k.endswith("_url") or k.endswith("_link")) and isinstance(v, str) and v.startswith("http"):
                        extracted.append(
                            TraversalContext(
                                url=v,
                                entity_id=current_context.entity_id,
                                depth=current_context.depth + 1,
                                parent_url=current_context.url
                            )
                        )
                    else:
                        _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(payload)
        return extracted
