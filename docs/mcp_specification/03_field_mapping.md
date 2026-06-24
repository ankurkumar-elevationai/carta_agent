# JSON to Database Field Mapping

This document provides the mapping between the raw JSON paths extracted from the Carta Sandbox APIs and the canonical PostgreSQL schema `02_database_schema.sql`.

## 1. Organizations (`organizations` table)
| JSON Path | Data Type | PostgreSQL Column | Description |
|-----------|-----------|-------------------|-------------|
| `_meta.org_pk` | integer | `external_org_pk` | Carta internal Organization ID |
| `data.firm-id` | string | `external_org_pk` | Alternative Firm ID |
| `data.firm-uuid` | uuid | `id` / `external_org_pk` | Firm UUID |
| *(Inferred)* | string | `name` | Extracted from GP entity names |

## 2. Funds & SPVs (`funds` table)
| JSON Path | Data Type | PostgreSQL Column | Description |
|-----------|-----------|-------------------|-------------|
| `_meta.entity_id` | string | `external_fund_id` | Extracted unique string (e.g. `fund_1117`) |
| `data.fund-name` | string | `name` | Display name of the fund/SPV |
| `data.fund-id` | integer | `external_fund_id` | Carta internal Fund ID |
| `_meta.entity_type` | string | `type` | Mapped to `entity_type` ENUM (Fund/SPV) |
| `data.general-ledger-enabled` | boolean | `general_ledger_enabled` | Boolean flag |
| `data.in-app-valuations-enabled` | boolean | `in_app_valuations_enabled` | Boolean flag |

## 3. Portfolio Companies (`portfolio_companies` table)
| JSON Path | Data Type | PostgreSQL Column | Description |
|-----------|-----------|-------------------|-------------|
| `_meta.entity_id` | string | `external_company_id`| Extracted string (e.g. `investment_366`) |
| `_meta.entity_name` | string | `name` | Display name of the company |
| `data.industry` | string | `industry` | (If available in profile API) |

## 4. Investors (`investors` table)
| JSON Path | Data Type | PostgreSQL Column | Description |
|-----------|-----------|-------------------|-------------|
| `_meta.entity_id` | string | `external_investor_id`| Extracted string (e.g. `partner_1811`) |
| `_meta.entity_name` | string | `name` | Investor display name |
| `data.owner_id` | integer | `external_investor_id`| Found within cap table rows |

## 5. Securities / Cap Table (`securities` table)
| JSON Path | Data Type | PostgreSQL Column | Description |
|-----------|-----------|-------------------|-------------|
| `data.rows[].id` | integer | `external_security_id`| Certificate ID / Issuable ID |
| `data.rows[].label` | string | `label` | Certificate label (e.g. CS-1) |
| `data.rows[].issue_date` | string | `issue_date` | Date of issuance (parsed from MM/DD/YYYY)|
| `data.rows[].issuable_type` | string | `issuable_type` | Common, Preferred, Option, etc. |
| `data.rows[].stock_type` | string | `stock_type` | Underlying stock classification |
| `data.rows[].status` | string | `status` | Outstanding, Canceled, etc. |
| `data.rows[].currency` | string | `currency` | Typically `$` |
| `data.rows[].quantity` | float | `quantity` | Number of shares / units |
| `data.rows[].cost` | float | `cost` | Total cost basis |
| `data.rows[].value` | float | `value` | Current market value |
| `data.rows[].has_vesting` | boolean | `has_vesting` | If true, vesting schedule exists |
| `data.rows[].qsbs` | boolean | `qsbs_eligible` | QSBS qualification status |

## 6. Documents (`documents` table)
| JSON Path | Data Type | PostgreSQL Column | Description |
|-----------|-----------|-------------------|-------------|
| `data.export-soi-api-url` | string | `document_url` | API link to SOI report |
| `data.financials-export-url`| string | `document_url` | API link to financials |

## 7. Unknown/Dynamic Fields (`raw_metadata` JSONB column)
Any fields not explicitly mapped to a structured column are stored in the `raw_metadata` JSONB column on their respective tables. Example fields from the `Field Catalog` that belong in JSONB:
- `data.time_vested`
- `data.eligible_for_settlement`
- `data.requires_two_person`
- `data.is_signing_state`
