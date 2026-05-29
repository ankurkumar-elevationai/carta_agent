from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def normalize_url(url: str) -> str:
    """Normalizes a URL by ensuring standard formatting."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower()))

def strip_query_noise(url: str) -> str:
    """Removes non-essential query parameters like cache busters."""
    noise_params = {'t', '_', 'timestamp', 'cb', 'v'}
    parsed = urlparse(url)
    query = parse_qsl(parsed.query)
    filtered_query = [(k, v) for k, v in query if k.lower() not in noise_params]
    new_query = urlencode(filtered_query)
    return urlunparse(parsed._replace(query=new_query))

def canonicalize_path(path: str) -> str:
    """Canonicalizes an API path by removing trailing slashes or duplicate slashes."""
    import re
    # Remove multiple slashes
    canonical = re.sub(r'/+', '/', path)
    # Remove trailing slash unless it's just '/'
    if canonical != '/' and canonical.endswith('/'):
        canonical = canonical[:-1]
    return canonical
