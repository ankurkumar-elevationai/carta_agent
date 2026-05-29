from dataclasses import dataclass, field
from typing import Optional, Set

@dataclass(slots=True)
class EndpointIdentity:
    path_pattern: str
    method: str

    schema_hash: Optional[str]
    response_kind: str

    auth_scope: Optional[str]
    capability_tags: Set[str] = field(default_factory=set)
