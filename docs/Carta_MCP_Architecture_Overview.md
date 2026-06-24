# Carta Investment MCP Server - Architecture & Project Overview

This document provides a comprehensive, end-to-end overview of the OpenClaw Carta MCP Server project. It details the purpose, architecture, data workflows, and the exposed Model Context Protocol (MCP) toolset.

---

## 1. Project Purpose

The Carta Investment MCP Server acts as an intelligent bridge between raw equity data extracted from Carta and an external enterprise platform. 

Carta stores highly complex, deeply nested JSON data regarding venture capital funds, portfolio companies, cap tables, transactions, and valuations. However, external platforms require data to be presented in a strictly flat, relational 19-table database structure (the "Investment Module Schema"). 

This project solves that by ingesting Carta data, decoupling it into a provider-agnostic "Canonical Data Model", and then strictly mapping it into the 19 mandated platform tables, exposing the results via MCP tools for AI agents or external clients to consume.

---

## 2. System Architecture

The architecture is built on a **Canonical Data Layer** pattern. This ensures that the platform schema is not tightly coupled to Carta. If future data sources (like PitchBook or Affinity) are added, they only need to map to the Canonical Store, requiring zero changes to the MCP endpoints.

### Core Components

1. **Raw Extraction (`frontend/data/business_data.json`)**
   - The initial source of truth containing deeply nested JSON representing the firm, funds, investments, cap tables, and relationships.

2. **The Adapter (`services/adapters/carta_adapter.py`)**
   - Ingests the raw `business_data.json`.
   - Uses a deterministic UUID5 generator (`uuid5(tenant_id:entity_id)`) to ensure that identical entities always generate the same unique ID across runs.
   - Normalizes the nested JSON into flat, standardized Python dataclasses.

3. **Canonical Entity Store (`services/canonical_entities.py` & `canonical_store.py`)**
   - An in-memory registry holding 10 provider-agnostic entities:
     `Organization`, `Fund`, `PortfolioCompany`, `Investor`, `Holding`, `Security`, `Valuation`, `Transaction`, `Document`, and `Person`.
   - Provides efficient indexing for O(1) lookups and aggregation (e.g., fetching a Company along with all its transactions and valuations).

4. **Platform Schema Mapper (`services/platform_schema.py` & `platform_mapper.py`)**
   - Defines the 19 strict Pydantic models required by the external platform (`inv_investment`, `inv_cap_call`, etc.).
   - Contains the transformation logic to convert Canonical Entities into Platform schemas. 
   - Handles 5 transform patterns: *Direct Map, Computed, Decomposed, Aggregated, and Enrichment Required (Stubs).*

5. **Coverage Analyzer (`services/coverage_analyzer.py`)**
   - Dynamically inspects the Platform Schema Mapper outputs to generate a real-time matrix of how many fields and tables are successfully populated vs. empty.

6. **MCP Server (`scripts/mcp_server.py`)**
   - Built on the official Anthropic MCP Python SDK.
   - Runs a Server-Sent Events (SSE) server on port 8080 (proxied via FastAPI).
   - Exposes the mapped schemas as discrete, callable AI tools.

---

## 3. Data Flow & Workflows

### A. Initialization Workflow (Server Startup)
1. `mcp_server.py` starts and mounts the SSE transport.
2. It locates `business_data.json` on disk.
3. It initializes the `CanonicalEntityStore` and passes the JSON to the `CartaAdapter`.
4. The adapter extracts ~35 companies, ~37 funds, and hundreds of transactions, registering them into the canonical store.
5. The `PlatformSchemaMapper` and `CoverageAnalyzer` are instantiated and linked to the store.

### B. Query Workflow (Client Execution)
1. An external AI agent or client connects to the MCP Server and requests a tool (e.g., `get_investments`).
2. The MCP server calls `PlatformSchemaMapper.map_inv_investment()`.
3. The mapper queries the `CanonicalEntityStore` for all `PortfolioCompany` entities and aggregates their `Holding` and `Valuation` records.
4. The data is transformed into a list of Pydantic `InvInvestment` objects.
5. The server wraps the response in a strict versioned envelope:
   ```json
   {
     "schema_version": "v1",
     "mapper_version": "v1",
     "table": "inv_investment",
     "record_count": 34,
     "data": [ ... ]
   }
   ```
6. The JSON payload is returned to the client.

---

## 4. Exposed MCP Interface

### Resources
- `platform://{tenant_id}/coverage`: Returns the JSON output of the Coverage Analyzer, showing exactly which of the 19 tables have data and what the overall field population percentage is.

### Platform Schema Tools (19 Target Tables)
These tools directly correspond to the 19 tables in the Investment Module schema. 
*Note: Tools marked with `(Stub)` currently return 0 records because Carta does not store qualitative narrative data. These are placeholders for future LLM enrichment.*

1. `get_investments` (Core company and holding details)
2. `get_investment_extra_info` (Company descriptions)
3. `get_investment_team` (Founders, Contacts)
4. `get_investment_valuations` (Historical 409A and post-money valuations)
5. `get_capital_calls` (Debit transactions)
6. `get_investment_log` (Point-in-time cumulative investment values)
7. `get_investment_transactions` (All inflows and outflows)
8. `get_investment_firm` (GP profile and AUM)
9. `get_investment_focus` (Portfolio costs and MOIC)
10. `get_investment_sectors` *(Stub)*
11. `get_investment_certificates` (Cap table share certificates)
12. `get_distribution_history` (Credit transactions / returns)
13. `get_liquidity_distributions` (Liquidity events)
14. `get_investment_expenses` *(Stub)*
15. `get_investment_interest` *(Stub)*
16. `get_investment_services` *(Stub)*
17. `get_usage_logs` *(Stub - N/A for Venture)*
18. `get_recent_developments` *(Stub)*
19. `get_growth_signals` *(Stub)*

### Legacy Extraction Tools
The server also maintains the original Carta-native tools for raw data interaction:
- `download_report` / `download_batch`: Trigger data ingestion jobs.
- `get_company`, `list_funds`, `get_cap_table`, `get_entity_graph`: Raw entity and relationship queries.

---

## 5. Technology Stack
- **Language**: Python 3.11+
- **Protocol**: Model Context Protocol (MCP) via `mcp` library (Server-Sent Events)
- **Web Framework**: Starlette / FastAPI / Uvicorn (HTTP routing & SSE mounting)
- **Data Validation**: Pydantic (Strict schema enforcement)
- **Database (Tasks)**: SQLite (`tasks.db` for tracking extraction jobs)
- **Data Ingestion**: Local JSON caching (`business_data.json`, `nodes.json`, `edges.json`)

---

## 6. Known Limitations & Future Roadmap

**Phase 2: LLM Enrichment Layer**
Because Carta only stores hard quantitative financial data, 8 of the 19 platform tables currently return 0 records (e.g., `investment_thesis`, `research_growing_traction`). 

To populate these, a future phase can implement an LLM Enrichment Engine. This engine would use PyMuPDF to extract text from the attached PDF documents (like Investment Memos and Subscription Agreements) and use an LLM (OpenAI/Anthropic) to dynamically generate the qualitative summaries needed to populate the remaining tables.
