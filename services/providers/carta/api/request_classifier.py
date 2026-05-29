from enum import Enum

class RequestType(str, Enum):
    GRAPHQL = "graphql"
    EXPORT = "export"
    ENTITY = "entity"
    INVESTMENT = "investment"
    UNKNOWN = "unknown"

IGNORED_DOMAINS = {
    "sentry.io",
    "datadog",
    "segment",
    "google-analytics",
    "stats.g.doubleclick.net",
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".css", ".js", ".map"
}

def classify_request(url: str) -> RequestType:
    lowered = url.lower()
    
    if "graphql" in lowered:
        return RequestType.GRAPHQL
    if "export" in lowered:
        return RequestType.EXPORT
    if "investment" in lowered:
        return RequestType.INVESTMENT
    if "entity" in lowered:
        return RequestType.ENTITY
        
    return RequestType.UNKNOWN

def should_ignore_request(url: str) -> bool:
    lowered_url = url.lower()
    
    # Check ignored domains
    for domain in IGNORED_DOMAINS:
        if domain in lowered_url:
            return True
            
    # Check static asset extensions
    for ext in IGNORED_EXTENSIONS:
        # Avoid false positives if the string happens to be in the URL path, 
        # but a simple ends_with or checking near the end is better.
        # Splitting by '?' to remove query params first:
        base_url = lowered_url.split('?')[0]
        if base_url.endswith(ext):
            return True
            
    return False
