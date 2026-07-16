import sys
import json
import os

def parse_and_save(cookie_str):
    cookies = []
    pairs = cookie_str.split(";")
    for p in pairs:
        p = p.strip()
        if not p or "=" not in p:
            continue
        parts = p.split("=", 1)
        name = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        
        cookies.append({
            "name": name,
            "value": val,
            "domain": ".carta.com",
            "path": "/"
        })
        
    output_path = os.path.join(os.getcwd(), "config", "session_cookies.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
        
    print(f"[OK] Successfully parsed {len(cookies)} cookies and saved to session_cookies.json!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_raw_cookie.py \"cookie_string\"")
        sys.exit(1)
    parse_and_save(sys.argv[1])
