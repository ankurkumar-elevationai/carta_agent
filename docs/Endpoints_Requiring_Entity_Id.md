# Carta API Endpoints Requiring Entity ID

This document outlines the API endpoints in OpenClaw Carta that require a target `entity_id` (representing the portfolio company or fund) to be fetched successfully. 

During a full discovery crawler run, the system automatically resolves the `entity_id` from the traversed pages. For fast-path direct syncs, this ID is parsed from the target URL config (`CARTA_TARGET_URL`) or passed explicitly.

---

## 1. Endpoints Requiring `entity_id`

| Platform Endpoint Name | Underlying template URL | Category | Description |
|---|---|---|---|
| **`get_investment_extra_info`** | `/api/corporations/{firm_id}/corporation_info/{entity_id}/` | `cap_table` | Fetches corporate profile and cap table overview. |
| **`get_investment_valuations`** | `/api/investors/portfolio/fund/{firm_id}/entity/{entity_id}/tabs/` | `valuations` | Fetches share class structures and valuations. |
| **`get_capital_calls`** | `/api/investors/transactions/fund/{firm_id}/entity/{entity_id}/transactions/` | `portfolio` | Fetches capital transactions, additions, debits, and credits. |
| **`get_investment_transactions`** | `/api/investors/transactions/fund/{firm_id}/entity/{entity_id}/transactions/` | `portfolio` | Similar to capital calls, lists transactions on the ledger. |
| **`get_investment_certificates`** | `/partner-portfolios/{firm_id}/fund/{entity_id}/portfolio-entity-overview/` | `portfolio` | Fetches digital certificate information and quantities. |
| **`get_documents`** | `/api/investors/fund/{firm_id}/get_received_documents/sent_from/{entity_id}/` | `portfolio` | Fetches documents, tax notices, and updates sent from the entity. |
| **`get_partner_metrics`** | `/v2/partners/organization/{org_uuid}/fund/{fund_uuid}/metrics/` | `portfolio` | Fetches LP partner metrics (vintage year, NAV, Called, Paid, etc.). |
| **`get_investment_team`** | `/v2/partners/list-primary-partner-contacts/org/{org_uuid}/fund/{fund_uuid}` | `portfolio` | Fetches contact lists and primary partner contact emails. |

---

## 2. Endpoints NOT Requiring `entity_id`

The following global endpoints do not target a specific sub-entity and can be resolved at the firm level:

| Platform Endpoint Name | Underlying template URL | Category | Description |
|---|---|---|---|
| **`get_investments`** | `/api/investors/portfolio/firm/{org_id}/list_individual_portfolio_investments/{firm_id}/list/` | `portfolio` | The master list of all individual portfolio investments. |
| **`get_investment_firm`** | `/api/investors/organization/{org_id}/address_api/` | `investors` | Address and details of the organization/firm. |
