"""
Export Frontend Data — v2 (Complete)
====================================
Scans every JSON file inside the latest output/exports/<run>/extracted/,
extracts ALL business data and writes frontend/data/business_data.json.

Data captured:
  1.  Funds (from permission groups, fund_admin_nav, workflow funds)
  2.  SPVs (subset of funds with "SPV" in name)
  3.  Portfolio Investments (from list_firm_investments, post-money-latest)
  4.  Cap Tables (from overview-captable endpoints)
  5.  Investors/Stakeholders (from cap table data)
  6.  Company Profiles (legal_name, incorporation, address, CEO, website)
  7.  Holdings Dashboard (held_since, cash_cost, ownership %)
  8.  Securities / Option Plans (name, fully_diluted, ownership)
  9.  409A Fair Market Values (price, effectiveDate, share class)
 10.  IRR / Performance (irr_percentage, multiple, transactions)
 11.  Contacts (company contacts with email, role)
 12.  Documents (capital call notices, etc.)
 13.  Fund Structure (Funds/SPVs/GP Entities hierarchy from nav)
 14.  Firm Entity Tabs (available modules per entity)
 15.  Historical Valuations (post-money-list rounds)
"""
import sys, os, json, re
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ── locate latest export ────────────────────────────────────────────
exports_root = project_root / "output" / "exports"
dirs = sorted(
    [d for d in exports_root.iterdir() if d.is_dir()],
    key=lambda d: d.stat().st_mtime, reverse=True,
)
latest = dirs[0]
extracted_dir = latest / "extracted"
print(f"[export] scanning {latest.name}")

# ── accumulators ────────────────────────────────────────────────────
funds = {}               # uuid -> {name, uuid, type, legal_name, url, ...}
spvs = {}                # uuid -> {}
investments_list = {}     # corporation_id -> {legal_name, dba, url, entity_type, ...}
cap_tables = {}           # company -> [{stakeholder, ownership, shares, cost, share_classes}]
investors_map = {}        # person name -> {total_ownership, investments}
company_profiles = {}     # entity_id -> {legal_name, date_of_incorporation, address, ceo, ...}
holdings_dashboard = {}   # entity_name -> {held_since, cash_cost, ownership, irr, multiple, ...}
securities = {}           # entity_name -> [{name, fully_diluted, ownership, ...}]
fmv_409a = {}             # entity_name -> [{id, price, effectiveDate, shareClassId, ...}]
irr_performance = {}      # entity_name -> {irr_percentage, multiple, transactions}
contacts = {}             # entity_name -> [{id, email, is_primary, ...}]
documents = []            # [{name, date, type, fund, ...}]
fund_structure = []       # [{header: "Funds", items: [{id, legal_name, url}]}, ...]
entity_tabs = {}          # entity_name -> [tab names]
valuations = {}           # company -> {post_money, funds_raised, share_class, currency}
historical_valuations = {} # entity_name -> [{currency, post_money, funds_raised, share_class}]
firm_info = {}
firm_investments = []     # raw list from list_firm_investments
export_records = []       # from export_inventory.json

def classify_fund_type(name: str) -> str:
    n = name.lower()
    if "spv" in n: return "SPV"
    if " gp" in n or n.endswith(" gp"): return "General Partner"
    if "management" in n or "manco" in n: return "Management Company"
    if "feeder" in n: return "Feeder Fund"
    if "fund" in n: return "Fund"
    return "Entity"

# ── walk every JSON ─────────────────────────────────────────────────
file_count = 0
for root, _, files in os.walk(extracted_dir):
    for fname in files:
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        fpath = Path(root) / fname
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue

        meta = raw.get("_meta", {})
        data = raw.get("data", {})
        if not data:
            continue
        file_count += 1

        source_url = meta.get("source_url", "")
        category = meta.get("category", "")
        entity_name = meta.get("entity_name", "")
        entity_id = meta.get("entity_id", "")
        entity_type = meta.get("entity_type", "")
        company = entity_name or entity_id

        # ── 1. Fund permission groups ──────────────────────────────
        if isinstance(data, dict) and "firm_member" in data:
            fm = data["firm_member"]
            if fm.get("firm_name"):
                firm_info["name"] = fm["firm_name"]
                firm_info["admin"] = fm.get("name", "")
                firm_info["title"] = fm.get("title", "")
                firm_info["email"] = fm.get("email", "")
            for fpg in fm.get("fund_permission_groups", []):
                fn = fpg.get("fund_name", "")
                fu = fpg.get("fund_uuid", "")
                if not fn: continue
                ftype = classify_fund_type(fn)
                target = spvs if ftype == "SPV" else funds
                if fu not in target:
                    target[fu] = {
                        "uuid": fu, "name": fn, "type": ftype,
                        "permissions": fpg.get("permission_group_keys", []),
                    }

        # ── 2. Fund admin nav (fund structure hierarchy) ───────────
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict) and "header" in first and "items" in first:
                fund_structure.clear()
                for group in data:
                    header = group.get("header", "")
                    items = []
                    for item in group.get("items", []):
                        if isinstance(item, dict):
                            fn = item.get("legal_name", "")
                            fu = item.get("uuid", "")
                            ftype = classify_fund_type(fn) if fn else "Entity"
                            items.append({
                                "id": item.get("id"),
                                "uuid": fu,
                                "legal_name": fn,
                                "url": item.get("url", ""),
                                "type": ftype,
                            })
                            # Also add to funds/spvs
                            target = spvs if ftype == "SPV" else funds
                            if fu and fu not in target:
                                target[fu] = {"uuid": fu, "name": fn, "type": ftype, "carta_id": item.get("id")}
                    fund_structure.append({"header": header, "items": items})

        # ── 3. list_firm_investments ───────────────────────────────
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict) and "corporation_id" in first:
                firm_investments = data
                for inv in data:
                    cid = str(inv.get("corporation_id", ""))
                    if cid:
                        investments_list[cid] = {
                            "corporation_id": cid,
                            "legal_name": inv.get("legal_name", ""),
                            "dba": inv.get("dba"),
                            "url": inv.get("url", ""),
                            "entity_type": inv.get("entity_type", ""),
                            "is_fund_investment": inv.get("is_fund_investment", False),
                            "group_name": inv.get("group_name", ""),
                        }

        if not isinstance(data, dict):
            continue

        # ── 4. Cap table ───────────────────────────────────────────
        if "captable" in data and isinstance(data["captable"], list):
            if company not in cap_tables:
                cap_tables[company] = []
            for stakeholder in data["captable"]:
                sname = stakeholder.get("name", "unknown")
                ownership = stakeholder.get("ownership", 0) or 0
                total_shares = 0
                total_cost = 0
                share_types = []
                for pfix in stakeholder.get("prefixes", []):
                    if not pfix.get("is_empty", True):
                        qty = pfix.get("quantity") or 0
                        cost = pfix.get("cost") or 0
                        total_shares += qty
                        total_cost += cost
                        share_types.append({
                            "class": pfix.get("prefix", ""),
                            "shares": qty,
                            "ownership_pct": round(pfix.get("ownership", 0) or 0, 4),
                            "cost": cost,
                        })
                cap_tables[company].append({
                    "stakeholder": sname,
                    "total_ownership_pct": round(ownership, 4),
                    "total_shares": total_shares,
                    "total_cost": total_cost,
                    "share_classes": share_types,
                })
                if sname not in investors_map:
                    investors_map[sname] = {"total_ownership_pct": 0, "investments": []}
                investors_map[sname]["total_ownership_pct"] += ownership
                investors_map[sname]["investments"].append(company)

        # ── 5. Post-money / valuation ──────────────────────────────
        if "post_money" in data and "share_class" in data:
            valuations[company] = {
                "post_money": data.get("post_money"),
                "funds_raised": data.get("funds_raised"),
                "share_class": data.get("share_class"),
                "currency": data.get("currency", "$"),
            }

        # ── 6. Company profiles ────────────────────────────────────
        if "legal_name" in data and "date_of_incorporation" in data:
            company_profiles[company] = {
                "legal_name": data.get("legal_name"),
                "date_of_incorporation": data.get("date_of_incorporation"),
                "address": data.get("address"),
                "ceo": data.get("ceo"),
                "website": data.get("website"),
                "description": data.get("description"),
            }

        # ── 7. Holdings dashboard ──────────────────────────────────
        if "held_since" in data and "cash_cost" in data:
            holdings_dashboard[company] = {
                "held_since": data.get("held_since"),
                "cash_cost": data.get("cash_cost"),
                "ownership_pct": data.get("ownership"),
                "currency": data.get("currency"),
                "irr_percentage": data.get("irr_percentage"),
                "multiple": data.get("multiple"),
                "captable_access_level": data.get("captable_access_level"),
                "show_cost_card": data.get("show_cost_card"),
            }

        # ── 8. Securities / option plans ───────────────────────────
        if "fully_diluted" in data and "name" in data:
            if company not in securities:
                securities[company] = []
            securities[company].append({
                "name": data.get("name"),
                "fully_diluted": data.get("fully_diluted"),
                "ownership_pct": data.get("ownership"),
                "committed_fully_diluted": data.get("committed_fully_diluted"),
                "committed_ownership": data.get("committed_ownership"),
                "is_only_option_plan": data.get("is_only_option_plan"),
            })

        # ── 9. IRR / Performance ───────────────────────────────────
        if "irr_percentage" in data:
            irr_performance[company] = {
                "irr_percentage": data.get("irr_percentage"),
                "multiple": data.get("multiple"),
                "transactions_count": len(data.get("transactions", [])),
                "transactions": data.get("transactions", [])[:5],  # sample
            }

        # ── 10. Contacts ──────────────────────────────────────────
        if "contacts" in data and isinstance(data["contacts"], list) and len(data["contacts"]) > 0:
            if company not in contacts:
                contacts[company] = []
            for c in data["contacts"]:
                if isinstance(c, dict):
                    contacts[company].append({
                        "name": c.get("name", ""),
                        "email": c.get("email", ""),
                        "is_primary": c.get("is_primary", False),
                        "title": c.get("title", ""),
                    })

        # ── 11. Documents ─────────────────────────────────────────
        if "results" in data and isinstance(data["results"], list):
            for doc in data["results"]:
                if isinstance(doc, dict) and "document_name" in doc:
                    documents.append({
                        "name": doc.get("document_name", ""),
                        "date": doc.get("document_date", ""),
                        "type": doc.get("document_type", ""),
                        "fund_name": doc.get("fund_name", ""),
                        "firm_name": doc.get("firm_name", ""),
                        "stakeholder": doc.get("stakeholder_name", ""),
                        "capital_account": doc.get("capital_account_name", ""),
                        "file_type": doc.get("file_type", ""),
                    })

        # ── 12. Entity tabs ───────────────────────────────────────
        if "firm_entity_tabs" in source_url or ("holdings" in data and "overview" in data):
            tabs = [k for k in data.keys()]
            entity_tabs[company] = tabs

        # ── 13. Workflow / tasks ──────────────────────────────────
        if "results" in data and isinstance(data["results"], list):
            for item in data["results"]:
                if isinstance(item, dict) and "workflow" in item:
                    wf = item["workflow"]
                    for wf_fund in wf.get("funds", []):
                        fn = wf_fund.get("name", "")
                        fu = wf_fund.get("uuid", "")
                        if fn and fu and fu not in funds and fu not in spvs:
                            ftype = classify_fund_type(fn)
                            target = spvs if ftype == "SPV" else funds
                            target[fu] = {"uuid": fu, "name": fn, "type": ftype, "carta_id": wf_fund.get("carta_id")}

        # ── 14. Holdings rows (equity grants, options, etc.) ──────
        if "rows" in data and isinstance(data["rows"], list):
            for row in data["rows"]:
                if isinstance(row, dict):
                    sn = row.get("security_name") or row.get("name", "")
                    if sn and company not in securities:
                        securities[company] = []
                    if sn:
                        securities[company].append({
                            "name": sn,
                            "shares": row.get("quantity") or row.get("shares", 0),
                            "cost_basis": row.get("cost_basis") or row.get("cost", 0),
                            "current_value": row.get("current_value", 0),
                            "ownership_pct": row.get("ownership_percentage", 0),
                            "source": "equity_grant",
                        })

        # ── 15. Firm overview init ────────────────────────────────
        if "organizationName" in data:
            firm_info["organization_name"] = data["organizationName"]
            firm_info["firm_id"] = data.get("firmId")
            firm_info["firm_uuid"] = data.get("firmUuid")

        # ── 16. 409A FMV data ─────────────────────────────────────
        # (these come as top-level lists, already handled above)

# ── Handle 409A FMV data (top-level list responses) ─────────────────
for root_dir, _, files in os.walk(extracted_dir):
    for fname in files:
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        fpath = Path(root_dir) / fname
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except:
            continue
        if not isinstance(raw, dict): continue
        meta = raw.get("_meta", {})
        data = raw.get("data")
        if "409a" in meta.get("source_url", "") and isinstance(data, list):
            company = meta.get("entity_name") or meta.get("entity_id", "")
            fmv_409a[company] = []
            for item in data:
                if isinstance(item, dict):
                    price_data = item.get("price", {})
                    fmv_409a[company].append({
                        "id": item.get("id"),
                        "price": price_data.get("amount") if isinstance(price_data, dict) else None,
                        "currency": price_data.get("currencyCode") if isinstance(price_data, dict) else None,
                        "effective_date": item.get("effectiveDate"),
                        "share_class_id": item.get("shareClassId"),
                        "is_common": item.get("isCommon"),
                        "is_primary": item.get("isPrimary"),
                    })

# ── Deduplicate investors ───────────────────────────────────────────
for name, inv in investors_map.items():
    inv["investments"] = list(set(inv["investments"]))
    inv["total_ownership_pct"] = round(inv["total_ownership_pct"], 4)

# ── Merge investment data from all sources ──────────────────────────
merged_investments = []
# Start with firm investments list (most complete)
all_companies = set()
for cid, inv in investments_list.items():
    name = inv.get("legal_name", "")
    all_companies.add(name)
    merged_investments.append({
        "corporation_id": cid,
        "company": name,
        "dba": inv.get("dba"),
        "entity_type": inv.get("entity_type"),
        "group_name": inv.get("group_name"),
        "is_fund_investment": inv.get("is_fund_investment"),
        # Merge from other sources
        "valuation": valuations.get(name, {}),
        "profile": company_profiles.get(name, {}),
        "holdings_summary": holdings_dashboard.get(name, {}),
        "irr": irr_performance.get(name, {}),
        "cap_table": cap_tables.get(name, []),
        "securities": securities.get(name, []),
        "fmv_409a": fmv_409a.get(name, []),
        "contacts": contacts.get(name, []),
        "tabs": entity_tabs.get(name, []),
    })

# Also add companies from valuations that aren't in investments_list
for name in valuations:
    if name not in all_companies:
        merged_investments.append({
            "company": name,
            "valuation": valuations.get(name, {}),
            "profile": company_profiles.get(name, {}),
            "holdings_summary": holdings_dashboard.get(name, {}),
            "irr": irr_performance.get(name, {}),
            "cap_table": cap_tables.get(name, []),
            "securities": securities.get(name, []),
            "fmv_409a": fmv_409a.get(name, []),
            "contacts": contacts.get(name, []),
            "tabs": entity_tabs.get(name, []),
        })

# ── Extract Export Inventory ─────────────────────────────────────────
inventory_path = latest / "export_inventory.json"
if inventory_path.exists():
    try:
        export_records = json.loads(inventory_path.read_text(encoding="utf-8"))
    except Exception:
        export_records = []

# ── Extract Entity Graph ────────────────────────────────────────────
entity_graph = {"nodes": [], "edges": [], "summary": {}}
graph_path = latest / "graph" / "entity_graph.json"
if graph_path.exists():
    try:
        entity_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── Extract Performance Profile ─────────────────────────────────────
performance_profile = {}
perf_path = latest / "performance_profile.json"
if perf_path.exists():
    try:
        performance_profile = json.loads(perf_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── Extract Coverage Report ─────────────────────────────────────────
coverage_report = {}
cov_path = latest / "coverage_report.json"
if cov_path.exists():
    try:
        coverage_report = json.loads(cov_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── Extract Domain Inventory ────────────────────────────────────────
domain_inventory = []
dom_path = latest / "domain_inventory.json"
if dom_path.exists():
    try:
        domain_inventory = json.loads(dom_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── Extract Fund Relationships ──────────────────────────────────────
fund_relationships = []
for root, _, files_list in os.walk(extracted_dir):
    for fname in files_list:
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        fpath = Path(root) / fname
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        meta = raw.get("_meta", {})
        data = raw.get("data", {})
        if isinstance(data, dict) and "relationships" in data:
            rels = data["relationships"]
            if isinstance(rels, list):
                for rel in rels:
                    if isinstance(rel, dict):
                        fund_relationships.append({
                            "entity": meta.get("entity_name", ""),
                            "entity_type": meta.get("entity_type", ""),
                            "related_fund": rel.get("fund_name", ""),
                            "direction": rel.get("investment_direction", ""),
                            "url": rel.get("fund_overview_url", ""),
                        })

# ── Extract Schema Clusters Summary ─────────────────────────────────
schema_summary = {"total_clusters": 0, "total_members": 0, "categories": {}}
sc_path = latest / "schemas" / "schema_clusters.json"
if sc_path.exists():
    try:
        sc_data = json.loads(sc_path.read_text(encoding="utf-8"))
        schema_summary["total_clusters"] = sc_data.get("summary", {}).get("total_clusters", 0)
        schema_summary["total_members"] = sc_data.get("summary", {}).get("total_members", 0)
        cat_counts = defaultdict(int)
        for c in sc_data.get("clusters", []):
            cat_counts[c.get("category", "unknown")] += 1
        schema_summary["categories"] = dict(cat_counts)
    except Exception:
        pass

# ── Build final output ──────────────────────────────────────────────
output = {
    "firm": firm_info,
    "summary": {
        "total_funds": len(funds),
        "total_spvs": len(spvs),
        "total_investments": len(merged_investments),
        "total_investors": len(investors_map),
        "total_documents": len(documents),
        "total_companies_with_profiles": len(company_profiles),
        "total_companies_with_irr": len(irr_performance),
        "total_companies_with_409a": len(fmv_409a),
        "total_securities": sum(len(v) for v in securities.values()),
        "total_contacts": sum(len(v) for v in contacts.values()),
        "files_processed": file_count,
    },
    "funds": list(funds.values()),
    "spvs": list(spvs.values()),
    "fund_structure": fund_structure,
    "investments": merged_investments,
    "cap_tables": {k: v for k, v in cap_tables.items() if v},
    "investors": [
        {"name": name, **data}
        for name, data in sorted(
            investors_map.items(),
            key=lambda x: x[1]["total_ownership_pct"],
            reverse=True,
        )
    ],
    "documents": documents,
    "company_profiles": company_profiles,
    "holdings_dashboard": holdings_dashboard,
    "securities": securities,
    "fmv_409a": fmv_409a,
    "irr_performance": irr_performance,
    "contacts": contacts,
    "entity_tabs": entity_tabs,
    "export_records": export_records,
    "entity_graph": entity_graph,
    "performance_profile": performance_profile,
    "coverage_report": coverage_report,
    "domain_inventory": domain_inventory,
    "fund_relationships": fund_relationships,
    "schema_summary": schema_summary,
}

# ── Write ────────────────────────────────────────────────────────────
out_dir = project_root / "frontend" / "data"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "business_data.json"
out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

print(f"[export] Done!")
print(f"  Firm:              {firm_info.get('name', 'N/A')}")
print(f"  Funds:             {len(funds)}")
print(f"  SPVs:              {len(spvs)}")
print(f"  Investments:       {len(merged_investments)}")
print(f"  Investors:         {len(investors_map)}")
print(f"  Company Profiles:  {len(company_profiles)}")
print(f"  Holdings Summary:  {len(holdings_dashboard)}")
print(f"  Securities:        {sum(len(v) for v in securities.values())}")
print(f"  409A FMVs:         {sum(len(v) for v in fmv_409a.values())}")
print(f"  IRR/Performance:   {len(irr_performance)}")
print(f"  Contacts:          {sum(len(v) for v in contacts.values())}")
print(f"  Documents:         {len(documents)}")
print(f"  Fund Structure:    {len(fund_structure)} groups")
print(f"  Entity Tabs:       {len(entity_tabs)}")
print(f"  Cap Tables:        {len(cap_tables)}")
print(f"  Export Records:    {len(export_records)}")
print(f"  Files scanned:     {file_count}")
print(f"  Output:            {out_path}")
print(f"  Output size:       {out_path.stat().st_size / 1024:.0f} KB")
