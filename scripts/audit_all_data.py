"""
Deep Audit: Scan every JSON file in the latest export and catalog
all unique data shapes, top-level keys, and business-relevant fields
that the frontend should be displaying.
"""
import sys, os, json
from pathlib import Path
from collections import defaultdict, Counter

project_root = Path(__file__).parent.parent
exports_root = project_root / "output" / "exports"
dirs = sorted([d for d in exports_root.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
latest = dirs[0]
extracted_dir = latest / "extracted"

print(f"Auditing: {latest.name}")
print(f"Extracted dir: {extracted_dir}")
print("=" * 80)

# Track everything
total_files = 0
skipped_files = 0
category_counts = Counter()
shape_catalog = defaultdict(list)  # shape_signature -> [example_paths]
all_top_keys = defaultdict(Counter)  # category -> {top_key: count}
url_patterns = defaultdict(int)
entity_types_seen = Counter()
data_shapes = defaultdict(lambda: defaultdict(int))  # category -> data_shape -> count

# Business data trackers
biz_data = {
    "fund_names": set(),
    "fund_uuids": set(),
    "company_names": set(),
    "investor_names": set(),
    "document_types": set(),
    "share_classes": set(),
    "security_names": set(),
    "captable_companies": set(),
    "holding_companies": set(),
    "valuation_companies": set(),
    "workflow_templates": set(),
    "firm_names": set(),
    "urls_with_business_data": [],
}

# Uncaptured data tracker
uncaptured_shapes = []

for root, _, files in os.walk(extracted_dir):
    for fname in files:
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        fpath = Path(root) / fname
        total_files += 1
        
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            skipped_files += 1
            continue
        
        if not isinstance(raw, dict):
            skipped_files += 1
            continue
        
        meta = raw.get("_meta", {})
        data = raw.get("data", {})
        category = meta.get("category", "unknown")
        source_url = meta.get("source_url", "")
        entity_name = meta.get("entity_name", "")
        entity_type = meta.get("entity_type", "")
        entity_id = meta.get("entity_id", "")
        
        category_counts[category] += 1
        if entity_type:
            entity_types_seen[entity_type] += 1
        
        # Classify URL pattern
        import re
        url_clean = re.sub(r'/\d+/', '/{id}/', source_url)
        url_clean = re.sub(r'/[a-f0-9-]{36}/', '/{uuid}/', url_clean)
        url_patterns[url_clean] += 1
        
        # Track top-level data keys
        if isinstance(data, dict):
            data_keys = sorted(data.keys())
            shape_sig = "|".join(data_keys)
            for k in data_keys:
                all_top_keys[category][k] += 1
            data_shapes[category][shape_sig] += 1
            
            # Deep business data extraction audit
            
            # Fund permission groups
            if "firm_member" in data:
                fm = data["firm_member"]
                for fpg in fm.get("fund_permission_groups", []):
                    fn = fpg.get("fund_name", "")
                    fu = fpg.get("fund_uuid", "")
                    if fn: biz_data["fund_names"].add(fn)
                    if fu: biz_data["fund_uuids"].add(fu)
                if fm.get("firm_name"):
                    biz_data["firm_names"].add(fm["firm_name"])
            
            # Cap table
            if "captable" in data and isinstance(data["captable"], list):
                biz_data["captable_companies"].add(entity_name or entity_id)
                for sh in data["captable"]:
                    if isinstance(sh, dict) and sh.get("name"):
                        biz_data["investor_names"].add(sh["name"])
            
            # Post-money valuations
            if "post_money" in data:
                biz_data["valuation_companies"].add(entity_name or entity_id)
                if data.get("share_class"):
                    biz_data["share_classes"].add(data["share_class"])
            
            # Documents
            if "results" in data and isinstance(data["results"], list):
                for item in data["results"]:
                    if isinstance(item, dict):
                        if "document_name" in item:
                            biz_data["document_types"].add(item.get("document_type", ""))
                            if item.get("fund_name"):
                                biz_data["fund_names"].add(item["fund_name"])
                        if "workflow" in item:
                            wf = item["workflow"]
                            biz_data["workflow_templates"].add(wf.get("template", ""))
                            for wf_fund in wf.get("funds", []):
                                if wf_fund.get("name"):
                                    biz_data["fund_names"].add(wf_fund["name"])
            
            # Holdings / equity grants
            if "rows" in data and isinstance(data["rows"], list):
                biz_data["holding_companies"].add(entity_name or entity_id)
                for row in data["rows"]:
                    if isinstance(row, dict):
                        sn = row.get("security_name") or row.get("name", "")
                        if sn: biz_data["security_names"].add(sn)
            
            # Organization/firm init data
            if "organizationName" in data:
                biz_data["firm_names"].add(data["organizationName"])
            if "firmId" in data:
                biz_data["firm_names"].add(f"firm_id={data['firmId']}")
            
            # Fund-level investor data (LP details)
            if "fund_investors" in data or "investors" in data:
                investors_list = data.get("fund_investors") or data.get("investors", [])
                if isinstance(investors_list, list):
                    for inv in investors_list:
                        if isinstance(inv, dict):
                            name = inv.get("name") or inv.get("investor_name") or inv.get("display_name", "")
                            if name:
                                biz_data["investor_names"].add(name)
            
            # Company-level data
            if "company_name" in data or "companyName" in data:
                cn = data.get("company_name") or data.get("companyName", "")
                if cn: biz_data["company_names"].add(cn)
            
            # Fund overview / performance
            if "fund_name" in data or "fundName" in data:
                fn = data.get("fund_name") or data.get("fundName", "")
                if fn: biz_data["fund_names"].add(fn)
            
            # Check for data we might NOT be capturing
            important_keys = {
                "commitments", "contributions", "distributions", "nav", "irr", "tvpi", "dpi",
                "capital_calls", "capital_accounts", "net_asset_value", "management_fee",
                "carried_interest", "fund_performance", "return_metrics", "portfolio_summary",
                "investment_summary", "fair_market_value", "unrealized_gain", "realized_gain",
                "total_value", "paid_in_capital", "committed_capital", "unfunded_commitment",
                "called_capital", "distributed_capital", "remaining_value",
                "partners", "stakeholders", "limited_partners", "general_partner",
                "k1_data", "tax_documents", "financial_statements",
                "transactions", "wire_instructions", "bank_accounts",
                "notices", "notifications",
                "entity_map", "org_chart", "ownership_structure",
            }
            found_important = set(data_keys) & important_keys
            if found_important:
                biz_data["urls_with_business_data"].append({
                    "url": source_url,
                    "keys": list(found_important),
                    "category": category,
                    "entity": entity_name or entity_id,
                })

        elif isinstance(data, list):
            data_shapes[category]["[list]"] += 1
            # Check list items for business data
            if len(data) > 0 and isinstance(data[0], dict):
                sample_keys = sorted(data[0].keys())
                shape_sig = f"[list of {len(data)}] keys: {','.join(sample_keys[:10])}"
                data_shapes[category][shape_sig] += 1

# ── Print full report ───────────────────────────────────────────────
print(f"\n{'='*80}")
print(f"TOTAL FILES:  {total_files}")
print(f"SKIPPED:      {skipped_files}")
print(f"PROCESSED:    {total_files - skipped_files}")

print(f"\n{'='*80}")
print("FILES BY CATEGORY:")
for cat, cnt in category_counts.most_common():
    print(f"  {cat:20s}  {cnt:4d} files")

print(f"\n{'='*80}")
print("ENTITY TYPES SEEN:")
for et, cnt in entity_types_seen.most_common():
    print(f"  {et:20s}  {cnt:4d}")

print(f"\n{'='*80}")
print("DATA SHAPES PER CATEGORY:")
for cat in sorted(data_shapes):
    print(f"\n  [{cat}]")
    for shape, cnt in sorted(data_shapes[cat].items(), key=lambda x: -x[1]):
        display = shape[:100] + "..." if len(shape) > 100 else shape
        print(f"    {cnt:3d}x  {display}")

print(f"\n{'='*80}")
print("ALL TOP-LEVEL DATA KEYS PER CATEGORY:")
for cat in sorted(all_top_keys):
    print(f"\n  [{cat}]")
    for key, cnt in all_top_keys[cat].most_common():
        print(f"    {key:40s}  {cnt:4d}")

print(f"\n{'='*80}")
print("UNIQUE URL PATTERNS (top 30):")
for url, cnt in sorted(url_patterns.items(), key=lambda x: -x[1])[:30]:
    print(f"  {cnt:3d}x  {url}")

print(f"\n{'='*80}")
print("BUSINESS DATA SUMMARY:")
for key, val in biz_data.items():
    if key == "urls_with_business_data":
        print(f"\n  {key}: {len(val)} URLs with important business keys")
        for item in val[:10]:
            print(f"    {item['entity']:30s}  keys={item['keys']}")
    elif isinstance(val, set):
        print(f"\n  {key}: {len(val)} unique values")
        for v in sorted(val)[:20]:
            print(f"    - {v}")
        if len(val) > 20:
            print(f"    ... and {len(val) - 20} more")

print(f"\n{'='*80}")
print("DONE")
