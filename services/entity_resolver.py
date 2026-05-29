import re
import json
import logging
from dataclasses import dataclass
from typing import List, Dict
from rapidfuzz import fuzz

log = logging.getLogger(__name__)

class EntityResolutionError(Exception):
    """Raised when no search candidate meets the minimum confidence threshold."""
    pass

class RetryableBrowserError(Exception):
    """Raised when Playwright fails due to network or navigation timeouts."""
    pass

class EntityValidationError(Exception):
    """Raised when the loaded profile page title does not match the requested company name."""
    pass

@dataclass
class SearchCandidate:
    index: int
    text: str
    normalized: str
    score: float

def normalize_company_name(name: str) -> str:
    """Normalizes a company name for fuzzy matching."""
    if not name:
        return ""
    name = name.lower()

    # Remove parentheticals e.g. "(NYS: BX)"
    name = re.sub(r"\(.*?\)", "", name)

    # Remove punctuation
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)

    return name.strip()

def resolve_entity(query: str, candidates: List[Dict[str, str]], min_score: float = 75.0) -> SearchCandidate:
    """
    Ranks search candidates against the query and returns the best match.
    Raises EntityResolutionError if no candidate meets the min_score.
    
    candidates: List of dicts e.g. [{"index": 0, "text": "Blackstone (NYS: BX)"}, ...]
    """
    if not candidates:
        raise EntityResolutionError(f"No search results found for query: '{query}'")

    normalized_query = normalize_company_name(query)
    best_candidate = None
    best_score = -1.0
    
    candidate_objects = []

    for c in candidates:
        text = c.get("text", "")
        index = c.get("index", 0)
        normalized_candidate = normalize_company_name(text)

        # Weighted hybrid score
        partial_score = fuzz.partial_ratio(normalized_query, normalized_candidate)
        token_sort_score = fuzz.token_sort_ratio(normalized_query, normalized_candidate)
        
        score = max(partial_score, token_sort_score)
        
        # Exact prefix boost
        if normalized_candidate.startswith(normalized_query):
            score += 10.0
            
        candidate_obj = SearchCandidate(
            index=index,
            text=text,
            normalized=normalized_candidate,
            score=score
        )
        candidate_objects.append(candidate_obj)

        if score > best_score:
            best_score = score
            best_candidate = candidate_obj

    # Save Candidate Logs for debugging
    log_data = {
        "query": query,
        "normalized_query": normalized_query,
        "candidates": [
            {"text": c.text, "normalized": c.normalized, "score": c.score} 
            for c in candidate_objects
        ],
        "selected": best_candidate.text if best_candidate else None
    }
    log.info(f"Entity Resolution Log:\n{json.dumps(log_data, indent=2)}")

    if best_score < min_score or not best_candidate:
        raise EntityResolutionError(
            f"No candidate met the minimum score of {min_score}. "
            f"Best was '{best_candidate.text if best_candidate else 'None'}' with score {best_score}."
        )

    return best_candidate
