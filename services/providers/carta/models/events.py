import msgspec
from typing import Optional, List
from .extraction import EventEnrichment, GraphQLMetadata

class NetworkEvent(msgspec.Struct):
    request_id: str
    url: str
    method: str
    status: int
    timestamp: float
    resource_type: str
    initiator: dict
    request_headers: dict
    response_headers: dict
    request_body: Optional[bytes]
    response_body: Optional[bytes]
    enrichment: Optional[EventEnrichment] = None
    graphql_metadata: Optional[GraphQLMetadata] = None
class WebSocketFrame(msgspec.Struct):
    timestamp: float
    is_sent: bool
    payload: bytes

class WebSocketSession(msgspec.Struct):
    socket_id: str
    url: str
    opened_at: float
    frames: List[WebSocketFrame]
