"""
Pagination Engine.

Detects and tracks pagination strategies used by Carta API endpoints.
Supports page-based, offset-based, and cursor-based pagination discovery.
"""

import logging
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel

log = logging.getLogger(__name__)


class PaginationStrategy(str, Enum):
    PAGE = "page"
    OFFSET = "offset"
    CURSOR = "cursor"
    UNKNOWN = "unknown"
    NONE = "none"


class PaginationState(BaseModel):
    strategy: PaginationStrategy = PaginationStrategy.UNKNOWN
    next_cursor: Optional[str] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    page_size: Optional[int] = None
    total_count: Optional[int] = None
    has_more: bool = False


# Known pagination signal keys in response bodies
_PAGE_SIGNALS = {"page", "page_number", "current_page", "pageNumber"}
_OFFSET_SIGNALS = {"offset", "skip", "start"}
_CURSOR_SIGNALS = {"cursor", "next_cursor", "after", "endCursor", "next_token"}
_COUNT_SIGNALS = {"count", "total", "total_count", "totalCount", "total_results"}
_NEXT_SIGNALS = {"next", "next_url", "next_page", "nextPage"}
_PAGE_SIZE_SIGNALS = {"page_size", "pageSize", "per_page", "perPage", "limit"}


def detect_pagination(payload: Any, query_params: Optional[dict] = None) -> PaginationState:
    """Detect pagination strategy from a response payload and/or query params."""
    if not isinstance(payload, dict):
        return PaginationState(strategy=PaginationStrategy.NONE)

    keys = set(payload.keys())

    # Check for cursor signals
    cursor_found = keys & _CURSOR_SIGNALS
    if cursor_found:
        cursor_key = next(iter(cursor_found))
        cursor_val = payload.get(cursor_key)
        count_key = next(iter(keys & _COUNT_SIGNALS), None)
        return PaginationState(
            strategy=PaginationStrategy.CURSOR,
            next_cursor=str(cursor_val) if cursor_val else None,
            has_more=bool(cursor_val),
            total_count=payload.get(count_key) if count_key else None,
        )

    # Check for page-based signals
    page_found = keys & _PAGE_SIGNALS
    if page_found:
        page_key = next(iter(page_found))
        size_key = next(iter(keys & _PAGE_SIZE_SIGNALS), None)
        count_key = next(iter(keys & _COUNT_SIGNALS), None)
        next_key = next(iter(keys & _NEXT_SIGNALS), None)
        return PaginationState(
            strategy=PaginationStrategy.PAGE,
            current_page=payload.get(page_key),
            page_size=payload.get(size_key) if size_key else None,
            total_count=payload.get(count_key) if count_key else None,
            has_more=bool(payload.get(next_key)) if next_key else False,
        )

    # Check for offset signals
    offset_found = keys & _OFFSET_SIGNALS
    if offset_found:
        count_key = next(iter(keys & _COUNT_SIGNALS), None)
        size_key = next(iter(keys & _PAGE_SIZE_SIGNALS), None)
        return PaginationState(
            strategy=PaginationStrategy.OFFSET,
            total_count=payload.get(count_key) if count_key else None,
            page_size=payload.get(size_key) if size_key else None,
            has_more=True,
        )

    # Check for "next" URL signal (common REST pattern: {"next": "http://...", "results": [...]})
    next_found = keys & _NEXT_SIGNALS
    if next_found:
        next_key = next(iter(next_found))
        count_key = next(iter(keys & _COUNT_SIGNALS), None)
        size_key = next(iter(keys & _PAGE_SIZE_SIGNALS), None)
        return PaginationState(
            strategy=PaginationStrategy.PAGE,
            has_more=bool(payload.get(next_key)),
            total_count=payload.get(count_key) if count_key else None,
            page_size=payload.get(size_key) if size_key else None,
        )

    # Also check query params for pagination hints
    if query_params:
        qkeys = set(query_params.keys())
        if qkeys & _PAGE_SIGNALS:
            return PaginationState(strategy=PaginationStrategy.PAGE, has_more=True)
        if qkeys & _OFFSET_SIGNALS:
            return PaginationState(strategy=PaginationStrategy.OFFSET, has_more=True)
        if qkeys & _CURSOR_SIGNALS:
            return PaginationState(strategy=PaginationStrategy.CURSOR, has_more=True)
        if qkeys & _PAGE_SIZE_SIGNALS:
            return PaginationState(strategy=PaginationStrategy.PAGE, has_more=True)

    return PaginationState(strategy=PaginationStrategy.NONE)
