import json

d = json.load(open(r'c:\Users\iaman\Vscode Pycharm\openclaw_carta\frontend\data\business_data.json', 'r'))

# Investments is a dict, not list
investments = d.get('investments', {})
if isinstance(investments, dict):
    first_key = list(investments.keys())[0]
    inv = investments[first_key]
    print(f"Investments: dict with {len(investments)} keys")
    print(f"First key: {first_key}")
    print(f"Investment keys: {list(inv.keys())}")
    print()
    
    # Cap table
    ct = inv.get('cap_table', {})
    if isinstance(ct, dict):
        print(f"Cap table keys: {list(ct.keys())}")
        rows = ct.get('rows', [])
        print(f"Cap table rows: {len(rows)}")
        if rows:
            print(f"Row[0] keys: {list(rows[0].keys())}")
    print()
    
    # Securities
    sec = inv.get('securities', {})
    if isinstance(sec, dict):
        print(f"Securities keys: {list(sec.keys())}")
        sec_rows = sec.get('rows', [])
        print(f"Securities rows: {len(sec_rows)}")
        if sec_rows:
            print(f"Security row keys: {list(sec_rows[0].keys())}")
    elif isinstance(sec, list):
        print(f"Securities: list with {len(sec)} items")
        if sec:
            print(f"Security[0] keys: {list(sec[0].keys())}")
    print()
    
    # Contacts
    contacts = inv.get('contacts', [])
    print(f"Contacts: {type(contacts).__name__} len={len(contacts) if isinstance(contacts, list) else 'N/A'}")
    if isinstance(contacts, list) and contacts:
        print(f"Contact[0] keys: {list(contacts[0].keys())}")
    print()
    
    # Holdings summary
    hs = inv.get('holdings_summary', {})
    print(f"Holdings summary: {json.dumps(hs, indent=2)[:500]}")
    print()
    
    # Valuation
    val = inv.get('valuation', {})
    print(f"Valuation: {json.dumps(val, indent=2)[:500]}")
    print()
    
    # IRR
    irr = inv.get('irr', {})
    print(f"IRR: {json.dumps(irr, indent=2)[:500]}")
    print()
    
    # Profile
    profile = inv.get('profile', {})
    print(f"Profile: {json.dumps(profile, indent=2)[:500]}")
else:
    print(f"Investments: list with {len(investments)} items")

# Top-level securities
print("\n=== Top-level securities ===")
sec = d.get('securities', [])
if isinstance(sec, list) and sec:
    print(f"Count: {len(sec)}")
    print(f"Sample: {json.dumps(sec[0], indent=2)[:500]}")
elif isinstance(sec, dict):
    print(f"Keys: {list(sec.keys())[:5]}")

# Fund sample
print("\n=== Fund sample ===")
funds = d.get('funds', [])
if funds:
    print(json.dumps(funds[0], indent=2)[:500])

# Fund relationships
print("\n=== Fund relationships ===")
fr = d.get('fund_relationships', [])
print(f"Count: {len(fr)}")
if fr:
    print(json.dumps(fr[0], indent=2)[:500])
