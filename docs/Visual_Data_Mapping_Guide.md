# Platform UI Visual Data Mapping Guide

This guide maps visual components from the Investment Module platform UI screenshots to the extracted Carta database fields. Use this as a reference to see exactly which metrics are populated, computed, or require external enrichment.

---

## 1. Venture SPV View (OpenAI SPV)

### Metrics & Overview
This screen displays SPV asset performance, totals, and historical transactions.

![SPV Metrics Annotated](file:///C:/Users/iaman/.gemini/antigravity/brain/6a4bc825-55e4-4dd6-abbf-bd0ab142c42d/spv_metrics_annotated_1783660362589.png)

| Callout ID | UI Element | Mapped Status | Carta Source Field | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **OpenAI SPV** (Title) | 🟢 Full | `data.name` | **DIRECT_MAP**: Core SPV entity name. |
| **2** | **SPV Total Size** ($80M) | 🟢 Full | `totals.committed[].value` | **DIRECT_MAP**: Total LP commitment. |
| **3** | **Your Commitment** ($25M) | 🟢 Full | `holdings_summary.cash_cost` | **DIRECT_MAP**: LP cost basis. |
| **4** | **Commitment %** (31%) | 🟡 Partial | `Your Commitment / SPV Size` | **COMPUTED**: Derived division. |
| **5** | **Current SPV Value** ($600M) | 🟢 Full | `totals.value` | **DIRECT_MAP**: SPV Gross Asset Value. |
| **6** | **Your Position Value** ($187.5M) | 🟢 Full | `holdings_summary.value` | **DIRECT_MAP**: Market value of holdings. |
| **7** | **SPV MOIC** (7.50x) | 🟢 Full | `holdings_summary.multiple` | **DIRECT_MAP**: TVPI multiple. |
| **8** | **Performance Chart** | 🟢 Full | `fmv_409a[].valuation` | **AGGREGATED**: Historical chart timeline. |
| **9** | **Transaction History** | 🟢 Full | `irr.transactions[]` | **DIRECT_MAP**: All debits & credits. |
| **10** | **Strategy** (Late Stage) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **11** | **Sector** (AI) | 🟡 Partial | `profile.industry` | **DIRECT_MAP**: Startup sector. |
| **12** | **Geography** (North America) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **13** | **Vintage** (2022) | 🟡 Partial | `holdings_summary.held_since` | **COMPUTED**: Vintage year extraction. |

---

### SPV Structure & Exit Modeling
This screen details terms, fees, waterfall exit payouts, and team members.

![SPV Structure Annotated](file:///C:/Users/iaman/.gemini/antigravity/brain/6a4bc825-55e4-4dd6-abbf-bd0ab142c42d/spv_structure_annotated_1783660391749.png)

| Callout ID | UI Element | Mapped Status | Carta Source Field | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **SPV Name** | 🟢 Full | `data.name` | **DIRECT_MAP**: Legal name. |
| **2** | **Formation Date** | 🟢 Full | `data.overview.formation_date`| **DIRECT_MAP**: Formation metadata. |
| **3** | **Total LPs** (15) | 🟢 Full | Count of `investors[]` | **AGGREGATED**: Total investor count. |
| **4** | **Management Fee** (0%) | 🟡 Partial | `fund_terms.management_fee` | **DIRECT_MAP**: Fee percentage. |
| **5** | **Carried Interest** (20%) | 🟢 Full | `carried_interest.carry_pct` | **DIRECT_MAP**: Carry terms. |
| **6** | **Entity Type** (Delaware LLC) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **7** | **Portfolio Company Table** | 🟢 Full | `holdings` | **DIRECT_MAP**: Company detail rows. |
| **8** | **Latest Round** (Series E) | 🟢 Full | `share_classes[].name` | **DIRECT_MAP**: Round Series text. |
| **9** | **Post-Money** ($300.0B) | 🟢 Full | `valuation.post_money` | **DIRECT_MAP**: Valuation cap. |
| **10** | **Waterfall Exit Model** | 🔴 None | *No native source* | **N/A**: Interactive platform exit calculator. |
| **11** | **TVPI** (7.62x) | 🟢 Full | `holdings_summary.multiple` | **COMPUTED**: Position TVPI. |
| **12** | **Net IRR** (142.5%) | 🟢 Full | `holdings_summary.irr_percentage`| **DIRECT_MAP**: IRR percentage. |
| **13** | **SPV Deployed** ($48.5M) | 🟡 Partial | `sum(holdings.cash_cost)` | **COMPUTED**: Sum of capital deployed. |
| **14** | **Min Investment** | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Require manual stub. |
| **15** | **Key People** | 🟢 Full | `contacts[]` | **DECOMPOSED**: Name splitting logic. |

---

## 2. Venture Fund View (Sequoia Capital Fund XIV)

### Metrics & Overview
This screen displays Fund commitments, called capital, current NAV, and NAV history.

![Fund Overview Annotated](file:///C:/Users/iaman/.gemini/antigravity/brain/6a4bc825-55e4-4dd6-abbf-bd0ab142c42d/fund_overview_annotated_1783660447465.png)

| Callout ID | UI Element | Mapped Status | Carta Source Field | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Sequoia Capital Fund XIV** | 🟢 Full | `fund.name` | **DIRECT_MAP**: Legal fund name. |
| **2** | **Committed Capital** ($15M) | 🟢 Full | `totals.committed` | **DIRECT_MAP**: Total LP commitment. |
| **3** | **Capital Called** ($9M) | 🟢 Full | `totals.contributed` | **DIRECT_MAP**: Called capital to date. |
| **4** | **Deployment Ratio** (60%) | 🟡 Partial | `Capital Called / Commitment`| **COMPUTED**: Derived percentage. |
| **5** | **Current NAV** ($19.5M) | 🟢 Full | `totals.value` | **DIRECT_MAP**: Fund net asset value. |
| **6** | **Distributions** ($1.2M) | 🟢 Full | `totals.distributed` | **DIRECT_MAP**: Total returned cash. |
| **7** | **Net IRR** (12.5%) | 🟢 Full | `holdings_summary.irr_percentage`| **DIRECT_MAP**: Internal rate of return. |
| **8** | **Fund Performance (NAV)** | 🟢 Full | `fmv_409a` or valuations | **AGGREGATED**: Historical timeline chart. |
| **9** | **Transaction History** | 🟢 Full | `irr.transactions[]` | **DIRECT_MAP**: Ledger events list. |
| **10** | **Strategy** (Multi-Sector) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **11** | **Sector** | 🟡 Partial | `profile.industry` | **DIRECT_MAP**: Sector metadata. |
| **12** | **Geography** (North America) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **13** | **Vintage** (2022) | 🟡 Partial | `holdings_summary.held_since` | **COMPUTED**: Mapped from vintage year. |

---

## 3. Venture Direct View (Anduril Direct)

### Metrics & Overview
This screen displays direct equity investments, cost basis, valuation multiples, and company profile detail.

![Direct Overview Annotated](file:///C:/Users/iaman/.gemini/antigravity/brain/6a4bc825-55e4-4dd6-abbf-bd0ab142c42d/direct_overview_annotated_1783660462971.png)

| Callout ID | UI Element | Mapped Status | Carta Source Field | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Anduril Direct** | 🟢 Full | `company` | **DIRECT_MAP**: Direct holding name. |
| **2** | **Invested Amount** ($3.0M) | 🟢 Full | `holdings_summary.cash_cost` | **DIRECT_MAP**: User cost basis. |
| **3** | **Current Value** ($7.2M) | 🟢 Full | `holdings_summary.value` | **DIRECT_MAP**: Current value. |
| **4** | **Unrealized Gain** ($4.2M) | 🟡 Partial | `Value - Invested` | **COMPUTED**: Derived gain. |
| **5** | **MOIC** (2.40x) | 🟢 Full | `holdings_summary.multiple` | **DIRECT_MAP**: Value multiple. |
| **6** | **Net IRR** (+44.5%) | 🟢 Full | `holdings_summary.irr_percentage`| **DIRECT_MAP**: IRR performance. |
| **7** | **Performance Chart** | 🟢 Full | `fmv_409a[].valuation` | **AGGREGATED**: Valuation timeline. |
| **8** | **Transaction History** | 🟢 Full | `irr.transactions[]` | **DIRECT_MAP**: Ledger events list. |
| **9** | **Strategy** (Series F) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **10** | **Sector** (Defense Tech) | 🟡 Partial | `profile.industry` | **DIRECT_MAP**: Sector category. |
| **11** | **Geography** (North America) | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded stub. |
| **12** | **Vintage** (2022) | 🟡 Partial | `holdings_summary.held_since` | **COMPUTED**: Mapped from vintage year. |

