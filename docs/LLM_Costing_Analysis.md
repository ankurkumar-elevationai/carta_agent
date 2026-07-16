# LLM Costing Analysis — Carta MCP Agent

This document details the LLM usage and associated costs for the Carta Investment MCP Agent.

---

## 1. Current LLM Usage Profile

### Key Finding: Zero Direct LLM API Calls in Agent Runtime

The Carta agent is a **fully deterministic** system. It does **not** make any direct calls to OpenAI, Anthropic, Google, or any other LLM API during extraction, normalization, or MCP serving.

| Component | LLM Used? | Details |
| :--- | :--- | :--- |
| Browser Scraper (`provider.py`) | ❌ No | Deterministic Playwright navigation, CSS selectors |
| Replay Client (`replay_client.py`) | ❌ No | HTTPX / Browser Fetch with cookie auth replay |
| Network Collector (`network_collector.py`) | ❌ No | Passive traffic interception |
| Response Normalizer (`response_normalizer.py`) | ❌ No | Rule-based JSON parsing |
| Intelligence Extractor (`intelligence_extractor.py`) | ❌ No | Heuristic schema clustering, regex patterns |
| Endpoint Classifier (`endpoint_classifier.py`) | ❌ No | Rule-based URL pattern matching |
| Schema Clusterer (`schema_clusterer.py`) | ❌ No | Algorithmic fingerprint comparison |
| Entity/Graph Builder | ❌ No | Deterministic graph construction |
| Export Engine (`export_engine.py`) | ❌ No | JSON serialization |
| Canonical Adapter (`carta_adapter.py`) | ❌ No | Deterministic field mapping |
| Platform Schema Mapper (`platform_mapper.py`) | ❌ No | Rule-based schema transform (DIRECT_MAP, COMPUTED, etc.) |
| MCP Server (`mcp_server.py`) | ❌ No | JSON-RPC tool dispatch |

**Current Agent Runtime LLM Cost: $0.00 per extraction run.**

---

## 2. Where LLM Costs Are Incurred

LLM costs are incurred **externally** — by the AI client (Claude, Gemini, etc.) that connects to the MCP server and calls its tools. The cost depends on the LLM model selected by the client and the volume of tool calls + response tokens.

### 2.1 MCP Tool Call Token Estimation

The MCP server exposes **32 tools** with structured JSON schemas. When an LLM client connects, it must process:

| Token Category | Estimated Tokens | Notes |
| :--- | ---: | :--- |
| **Tool Definitions** (system prompt injection) | ~4,500 | 32 tools × ~140 tokens avg schema |
| **Resource Definitions** | ~300 | 4 resources with descriptions |
| **Per Tool Call (request)** | ~50–150 | Tool name + arguments JSON |
| **Per Tool Response (small)** | ~200–500 | `get_status`, `get_organization` |
| **Per Tool Response (medium)** | ~2,000–5,000 | `get_company`, `get_fund`, `get_cap_table` |
| **Per Tool Response (large)** | ~8,000–25,000 | `list_companies`, `get_investments`, `get_investment_transactions` |

### 2.2 Typical Session Cost Estimates

#### Scenario A: Single Company Lookup
> *User asks: "Show me details for MangoCart Inc."*

| Step | Tool Called | Est. Response Tokens |
| :--- | :--- | ---: |
| 1 | `search_entities(query="MangoCart")` | 300 |
| 2 | `get_company(company_id="...")` | 2,500 |
| 3 | `get_holding(company_id="...")` | 1,200 |
| 4 | `get_cap_table(company_id="...")` | 3,000 |
| **Total** | 4 tool calls | **~7,000 tokens** |

| Model | Input Cost | Output Cost | Total Session Cost |
| :--- | ---: | ---: | ---: |
| GPT-4o | $0.0025/1K × 11.5K = $0.029 | $0.010/1K × 1K = $0.010 | **~$0.04** |
| GPT-4o-mini | $0.00015/1K × 11.5K = $0.002 | $0.0006/1K × 1K = $0.001 | **~$0.003** |
| Claude Sonnet 4 | $0.003/1K × 11.5K = $0.035 | $0.015/1K × 1K = $0.015 | **~$0.05** |
| Claude Opus 4 | $0.015/1K × 11.5K = $0.173 | $0.075/1K × 1K = $0.075 | **~$0.25** |
| Gemini 2.5 Flash | $0.00015/1K × 11.5K = $0.002 | $0.001/1K × 1K = $0.001 | **~$0.003** |
| Gemini 2.5 Pro | $0.00125/1K × 11.5K = $0.014 | $0.010/1K × 1K = $0.010 | **~$0.02** |

#### Scenario B: Full Portfolio Review
> *User asks: "Give me a full portfolio summary across all funds and companies."*

| Step | Tool Called | Est. Response Tokens |
| :--- | :--- | ---: |
| 1 | `get_organization()` | 500 |
| 2 | `list_funds()` | 3,000 |
| 3 | `list_companies(include_holdings=true)` | 15,000 |
| 4 | `get_investments()` | 20,000 |
| 5 | `get_data_coverage()` | 2,000 |
| **Total** | 5 tool calls | **~40,500 tokens** |

| Model | Input Cost | Output Cost | Total Session Cost |
| :--- | ---: | ---: | ---: |
| GPT-4o | $0.0025/1K × 45K = $0.113 | $0.010/1K × 2K = $0.020 | **~$0.13** |
| GPT-4o-mini | $0.00015/1K × 45K = $0.007 | $0.0006/1K × 2K = $0.001 | **~$0.008** |
| Claude Sonnet 4 | $0.003/1K × 45K = $0.135 | $0.015/1K × 2K = $0.030 | **~$0.17** |
| Claude Opus 4 | $0.015/1K × 45K = $0.675 | $0.075/1K × 2K = $0.150 | **~$0.83** |
| Gemini 2.5 Flash | $0.00015/1K × 45K = $0.007 | $0.001/1K × 2K = $0.002 | **~$0.009** |
| Gemini 2.5 Pro | $0.00125/1K × 45K = $0.056 | $0.010/1K × 2K = $0.020 | **~$0.08** |

#### Scenario C: Data Sync to Platform
> *User triggers: "Sync MangoCart data to the platform."*

| Step | Tool Called | Est. Response Tokens |
| :--- | :--- | ---: |
| 1 | `download_report(company_name="MangoCart, Inc.")` | 800 |
| 2 | `get_extraction_status()` | 300 |
| 3 | `sync_to_platform(company_name="MangoCart, Inc.")` | 500 |
| **Total** | 3 tool calls | **~1,600 tokens** |

| Model | Input Cost | Output Cost | Total Session Cost |
| :--- | ---: | ---: | ---: |
| GPT-4o | $0.0025/1K × 6.1K = $0.015 | $0.010/1K × 0.8K = $0.008 | **~$0.02** |
| GPT-4o-mini | $0.00015/1K × 6.1K = $0.001 | $0.0006/1K × 0.8K = $0.0005 | **~$0.002** |
| Claude Sonnet 4 | $0.003/1K × 6.1K = $0.018 | $0.015/1K × 0.8K = $0.012 | **~$0.03** |
| Gemini 2.5 Flash | $0.00015/1K × 6.1K = $0.001 | $0.001/1K × 0.8K = $0.001 | **~$0.002** |

---

## 3. Monthly Cost Projections

Based on estimated daily usage patterns:

| Usage Level | Sessions/Day | Avg Tokens/Session | Model | Monthly Cost |
| :--- | ---: | ---: | :--- | ---: |
| **Light** (dev/testing) | 5 | 10K | GPT-4o-mini | **~$0.50** |
| **Light** (dev/testing) | 5 | 10K | Gemini 2.5 Flash | **~$0.50** |
| **Moderate** (daily ops) | 20 | 15K | GPT-4o | **~$30** |
| **Moderate** (daily ops) | 20 | 15K | Claude Sonnet 4 | **~$40** |
| **Heavy** (automated pipelines) | 100 | 20K | GPT-4o-mini | **~$12** |
| **Heavy** (automated pipelines) | 100 | 20K | Gemini 2.5 Flash | **~$12** |
| **Heavy** (automated pipelines) | 100 | 20K | GPT-4o | **~$200** |

---

## 4. Future LLM Costs (Phase 2 Enrichment)

The architecture doc references a planned **Phase 2: LLM Enrichment Layer** to populate the 8 stub tables (`investment_thesis`, `recent_developments`, `growth_signals`, etc.) that require qualitative data Carta doesn't store.

### Enrichment Use Cases & Estimated Costs

| Enrichment Task | Input Source | Est. Tokens/Call | Calls/Company | Cost/Company (GPT-4o) |
| :--- | :--- | ---: | ---: | ---: |
| Investment Thesis Generation | PDF pitch deck (10-20 pages) | 15,000 in + 2,000 out | 1 | **$0.06** |
| Growth Signals Extraction | News articles + financials | 8,000 in + 1,000 out | 1 | **$0.03** |
| Sector Classification | Company description | 500 in + 100 out | 1 | **$0.002** |
| Recent Developments Summary | News feed / press releases | 5,000 in + 1,000 out | 1 | **$0.02** |
| Lead Investor Identification | Crunchbase/PitchBook data | 2,000 in + 500 out | 1 | **$0.01** |

**Phase 2 enrichment cost per company**: ~$0.12 (GPT-4o) or ~$0.005 (GPT-4o-mini)
**For 35 portfolio companies (full sweep)**: ~$4.20 (GPT-4o) or ~$0.18 (GPT-4o-mini)

---

## 5. Cost Optimization Recommendations

| Strategy | Impact | Implementation |
| :--- | :--- | :--- |
| **Use GPT-4o-mini or Gemini Flash for routine queries** | 10-20x cost reduction | Route simple lookups to cheaper models |
| **Cache MCP tool responses** | 50-80% token reduction | 6-hour TTL cache on `business_data.json` reads |
| **Truncate large tool responses** | 30-50% token reduction | Paginate `list_companies` and `get_investments` (limit + offset) |
| **Batch enrichment with mini models** | 90% cost reduction vs. GPT-4o | Use GPT-4o-mini for sector tags, titles, classifications |
| **Reserve premium models for complex queries** | Cost-efficient quality | Use Claude Opus/GPT-4o only for multi-step reasoning |

---

## 6. Summary

| Category | Cost |
| :--- | :--- |
| **Agent Runtime (extraction, normalization, MCP serving)** | **$0.00** |
| **LLM Client Queries (per single company lookup)** | **$0.003 – $0.25** (depends on model) |
| **LLM Client Queries (monthly, moderate usage)** | **$12 – $40** |
| **Phase 2 Enrichment (full portfolio, one-time)** | **$0.18 – $4.20** |

> **Bottom line**: The Carta agent itself is free to run. All LLM costs are incurred by the external client making MCP tool calls. For production, using **Gemini 2.5 Flash** or **GPT-4o-mini** for routine queries keeps costs under **$15/month** even at high volume.
