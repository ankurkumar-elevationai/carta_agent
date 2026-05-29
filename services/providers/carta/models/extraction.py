import msgspec
from typing import Any
from enum import Enum

class TrafficClass(str, Enum):
    BUSINESS_API = "business_api"
    GRAPHQL = "graphql"
    TELEMETRY = "telemetry"
    ANALYTICS = "analytics"
    STATIC_ASSET = "static_asset"
    MICROFRONTEND = "microfrontend"
    SESSION = "session"
    AUTH = "auth"
    CONFIG = "config"
    CDN = "cdn"
    UNKNOWN = "unknown"

class CapabilityTag(str, Enum):
    PAGINATED = "paginated"
    SEARCHABLE = "searchable"
    GRAPHQL = "graphql"
    ENTITY_LIST = "entity_list"
    VALUATION_DATA = "valuation_data"
    CAP_TABLE = "cap_table"
    PORTFOLIO_DATA = "portfolio_data"
    REPORTING = "reporting"
    STREAMING = "streaming"
    MUTATION = "mutation"
    AUTH_REQUIRED = "auth_required"
    ENTITY_DETAIL = "entity_detail"
    READ_ONLY = "read_only"
    MUTABLE = "mutable"
    SEARCH_INDEXED = "search_indexed"
    BATCHABLE = "batchable"
    SUMMARY_VIEW = "summary_view"

class EndpointCategory(str, Enum):
    PORTFOLIO = "portfolio"
    VALUATIONS = "valuations"
    INVESTORS = "investors"
    CAP_TABLE = "cap_table"
    SECURITIES = "securities"
    REPORTING = "reporting"
    TASKS = "tasks"
    PERMISSIONS = "permissions"
    GRAPHQL = "graphql"
    INTERNAL = "internal"
    UNKNOWN = "unknown"

class TraversalContext(msgspec.Struct, kw_only=True):
    page_url: str
    tab_name: str | None = None
    entity_path: tuple[str, ...] = ()
    drilldown_depth: int = 0
    interaction_type: str = "LOAD"
    navigation_mode: str = "DIRECT"
    entity_id: str | None = None

class ParsedResponseLayer(msgspec.Struct, kw_only=True):
    parsed_ref: str
    top_level_keys: tuple[str, ...] = ()
    schema_trie_hash: str
    normalized_schema_hash: str
    entity_density: float = 0.0
    structural_metrics: dict[str, int] = msgspec.field(default_factory=dict)


class EventEnrichment(msgspec.Struct, kw_only=True):
    schema_version: int = 1
    schema_fingerprint: str | None = None
    traffic_class: TrafficClass = TrafficClass.UNKNOWN
    endpoint_category: EndpointCategory = EndpointCategory.UNKNOWN
    capability_tags: tuple[CapabilityTag, ...] = ()
    entity_types: tuple[str, ...] = ()
    confidence_distribution: dict[CapabilityTag, float] = msgspec.field(default_factory=dict)
    schema_cluster_id: str | None = None
    confidence_score: float = 0.0
    graphql_operation: str | None = None
    inferred_entity_type: str | None = None
    traversal_context: TraversalContext | None = None

class GraphQLMetadata(msgspec.Struct, kw_only=True):
    operation_name: str | None = None
    sha256_hash: str | None = None
    variables: dict[str, Any] | None = None
    persisted_query: bool = False

class EntityIdentity(msgspec.Struct, kw_only=True):
    source_fingerprint: str
    source_operation: str | None
    source_endpoint: str

class InvestmentEntity(msgspec.Struct, kw_only=True):
    canonical_investment_id: str | None = None
    canonical_firm_id: str | None = None
    company_name: str
    legal_name: str | None = None
    stage: str | None = None
    valuation: float | None = None
    ownership_pct: float | None = None
    security_type: str | None = None
    identity: EntityIdentity | None = None

class ValuationEntity(msgspec.Struct, kw_only=True):
    canonical_valuation_id: str | None = None
    canonical_investment_id: str | None = None
    date: str | None = None
    fmv: float | None = None
    status_409a: str | None = None
    identity: EntityIdentity | None = None

class CapTableEntity(msgspec.Struct, kw_only=True):
    canonical_captable_id: str | None = None
    canonical_investment_id: str | None = None
    share_class: str | None = None
    authorized: int | None = None
    issued: int | None = None
    identity: EntityIdentity | None = None

class EntityGraph(msgspec.Struct, kw_only=True):
    firm_id: str
    investments: list[InvestmentEntity] = []
    valuations: list[ValuationEntity] = []
    cap_tables: list[CapTableEntity] = []


# ────────────────────────────────────────────────────────────────────
# Phase 1: Organization Discovery
# ────────────────────────────────────────────────────────────────────

class OrganizationNode(msgspec.Struct, kw_only=True):
    """Represents a single organization/account the user has access to."""
    org_pk: int
    name: str
    account_type: str           # "investment firm", "portfolio", "company"
    landing_url: str
    is_target: bool = False
    is_favorite: bool = False
    most_recent_rank: int = 99999


# ────────────────────────────────────────────────────────────────────
# Phase 2: Entity Discovery
# ────────────────────────────────────────────────────────────────────

class DiscoveredEntity(msgspec.Struct, kw_only=True):
    """A fund, SPV, investment, or company discovered via API enumeration."""
    entity_id: str
    entity_type: str            # "fund", "spv", "investment", "company"
    name: str
    parent_org_pk: int
    detail_url: str | None = None
    security_type: str | None = None
    stage: str | None = None
    raw_data: dict = msgspec.field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────
# Phase 3: Interaction Provenance & API Dependencies
# ────────────────────────────────────────────────────────────────────

class InteractionProvenance(msgspec.Struct, kw_only=True):
    """Records WHY an API was triggered — the UI interaction that caused it."""
    interaction_type: str           # "TAB_CLICK", "ROW_DRILLDOWN", "MODAL_OPEN", "PAGE_LOAD"
    ui_path: tuple[str, ...] = ()   # ["Tasks", "Capital Calls", "Review Capital Call"]
    triggered_endpoints: tuple[str, ...] = ()
    entity_context: str | None = None
    timestamp: float = 0.0


class APIDependency(msgspec.Struct, kw_only=True):
    """Tracks API call chain dependencies (A → B → C)."""
    source_url: str
    target_url: str
    dependency_type: str        # "bootstrap", "cursor", "id_chain", "auth_refresh"
    extracted_ids: dict[str, str] = msgspec.field(default_factory=dict)


class DrilldownResult(msgspec.Struct, kw_only=True):
    """Result of drilldown traversal for a single entity."""
    entity_id: str
    routes_visited: tuple[str, ...] = ()
    apis_discovered: int = 0
    tabs_explored: int = 0
    errors: tuple[str, ...] = ()


# ────────────────────────────────────────────────────────────────────
# Phase 6: Entity Graph
# ────────────────────────────────────────────────────────────────────

class GraphNode(msgspec.Struct, kw_only=True):
    """A node in the canonical entity graph."""
    node_id: str
    node_type: str              # "organization", "fund", "investment", "valuation", "cap_table", "security"
    name: str
    properties: dict = msgspec.field(default_factory=dict)
    source_urls: tuple[str, ...] = ()


class GraphEdge(msgspec.Struct, kw_only=True):
    """A typed edge between two graph nodes."""
    source_id: str
    target_id: str
    edge_type: str              # "owns", "invested_in", "valued_at", "has_security", "managed_by"
    metadata: dict = msgspec.field(default_factory=dict)


class GraphProvenance(msgspec.Struct, kw_only=True):
    """Provenance metadata for the entity graph."""
    task_id: str
    created_at: str
    total_api_calls: int = 0
    total_interactions: int = 0
    discovery_duration_s: float = 0.0
    extraction_duration_s: float = 0.0
    schema_clusters: int = 0


class CartaEntityGraph(msgspec.Struct, kw_only=True):
    """The canonical output — a structured entity graph."""
    graph_id: str
    firm_id: int
    firm_name: str
    created_at: str
    nodes: dict[str, GraphNode] = msgspec.field(default_factory=dict)
    edges: list[GraphEdge] = msgspec.field(default_factory=list)
    provenance: GraphProvenance | None = None
