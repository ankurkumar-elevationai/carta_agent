import json
from pathlib import Path

root = Path(r"c:\Users\iaman\Vscode Pycharm\openclaw_carta\output\exports\de6d70c8-e044-47b5-81fa-a74ee54e74b0_krakatoa_ventures\extracted")

# Sample one holdings-dashboard file (IRR/performance)
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    data = raw.get("data", {})
    if isinstance(data, dict) and "irr_percentage" in data:
        meta = raw["_meta"]
        print("=== IRR/PERFORMANCE DATA ===")
        print(f"Entity: {meta.get('entity_name')}")
        for k in ["held_since","cash_cost","ownership","irr_percentage","multiple","currency"]:
            print(f"  {k}: {data.get(k)}")
        txns = data.get("transactions", [])
        print(f"  transactions: {len(txns)} items")
        if txns:
            print(f"  sample txn: {json.dumps(txns[0], indent=2)[:300]}")
        break

print()

# Sample one company profile
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    data = raw.get("data", {})
    if isinstance(data, dict) and "legal_name" in data:
        meta = raw["_meta"]
        print("=== COMPANY PROFILE ===")
        print(f"Entity: {meta.get('entity_name')}")
        for k in ["legal_name","date_of_incorporation","address","ceo","website","description"]:
            print(f"  {k}: {data.get(k)}")
        break

print()

# Sample one securities file
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    data = raw.get("data", {})
    meta = raw.get("_meta", {})
    if meta.get("category") == "securities" and isinstance(data, dict) and "name" in data:
        print("=== SECURITIES DATA ===")
        print(f"Entity: {meta.get('entity_name')}")
        for k in ["name","fully_diluted","cost","ownership","committed_fully_diluted","committed_ownership"]:
            print(f"  {k}: {data.get(k)}")
        break

print()

# Sample 409a FMV data
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    meta = raw.get("_meta", {})
    if "409a" in meta.get("source_url", ""):
        print("=== 409A FMV (VALUATION) DATA ===")
        print(f"Entity: {meta.get('entity_name')}")
        data = raw.get("data", {})
        if isinstance(data, dict):
            print(f"  keys: {list(data.keys())[:10]}")
            results = data.get("results", [])
            if results and isinstance(results[0], dict):
                print(f"  sample: {json.dumps(results[0], indent=2)[:400]}")
        elif isinstance(data, list) and len(data) > 0:
            print(f"  list of {len(data)}, sample: {json.dumps(data[0], indent=2)[:400]}")
        break

print()

# Sample post-money-list (historical valuations)
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    meta = raw.get("_meta", {})
    if "post-money-list" in meta.get("source_url", ""):
        print("=== POST-MONEY LIST (HISTORICAL) ===")
        print(f"Entity: {meta.get('entity_name')}")
        data = raw.get("data", {})
        if isinstance(data, list) and len(data) > 0:
            print(f"  {len(data)} rounds found")
            print(f"  sample: {json.dumps(data[0], indent=2)[:400]}")
        break

print()

# Sample option plan
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    meta = raw.get("_meta", {})
    if "option-plan" in meta.get("source_url", ""):
        print("=== OPTION PLAN DATA ===")
        print(f"Entity: {meta.get('entity_name')}")
        data = raw.get("data", {})
        if isinstance(data, dict):
            for k, v in list(data.items())[:8]:
                print(f"  {k}: {v}")
        break

print()

# Firm entity tabs (what tabs are available for each investment)
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    meta = raw.get("_meta", {})
    if "firm_entity_tabs" in meta.get("source_url", ""):
        print("=== FIRM ENTITY TABS ===")
        print(f"Entity: {meta.get('entity_name')}")
        data = raw.get("data", {})
        if isinstance(data, dict):
            print(f"  Available tabs: {list(data.keys())}")
        break

print()

# Company contacts
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    data = raw.get("data", {})
    if isinstance(data, dict) and "contacts" in data and isinstance(data["contacts"], list) and len(data["contacts"]) > 0:
        meta = raw.get("_meta", {})
        print("=== COMPANY CONTACTS ===")
        print(f"Entity: {meta.get('entity_name')}")
        for c in data["contacts"][:3]:
            if isinstance(c, dict):
                print(f"  {json.dumps(c, indent=2)[:200]}")
        break

print()

# Fund admin nav info (fund structure)
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    meta = raw.get("_meta", {})
    if "fund_admin_nav" in meta.get("source_url", ""):
        print("=== FUND ADMIN NAV (FUND STRUCTURE) ===")
        data = raw.get("data", {})
        if isinstance(data, list):
            print(f"  {len(data)} funds listed")
            for item in data[:3]:
                if isinstance(item, dict):
                    print(f"  {json.dumps(item, indent=2)[:300]}")
        break

print()

# list_firm_investments
for f in root.rglob("*.json"):
    raw = json.loads(f.read_text("utf-8"))
    if not isinstance(raw, dict): continue
    meta = raw.get("_meta", {})
    if "list_firm_investments" in meta.get("source_url", ""):
        print("=== FIRM INVESTMENTS LIST ===")
        data = raw.get("data", {})
        if isinstance(data, list):
            print(f"  {len(data)} investments")
            if data:
                print(f"  sample keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'N/A'}")
                print(f"  sample: {json.dumps(data[0], indent=2)[:400]}")
        break
