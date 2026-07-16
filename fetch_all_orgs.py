import asyncio
import re
import json
import sys
from playwright.async_api import async_playwright

async def resolve_orgs():
    print("====================================================================")
    print("                 CARTA ORGANIZATION RESOLVER                        ")
    print("====================================================================\n")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        except Exception as e:
            print(f"Error: Could not connect to Chrome debugging session on port 9222: {e}")
            print("Please ensure Chrome is running with remote debugging enabled:")
            print("  chrome.exe --remote-debugging-port=9222")
            return
            
        context = browser.contexts[0]
        page = None
        for p_page in context.pages:
            if "carta.com" in p_page.url:
                page = p_page
                break
                
        if not page:
            print("Error: No active Carta tabs found in Chrome.")
            print("Please open app.carta.com in your browser first.")
            await browser.close()
            return
            
        print(f"Connected to active Carta tab: {page.url}")
        print("Fetching account switcher list...")
        
        # 1. Fetch the list of all accounts dynamically
        js_get_accounts = """
        async () => {
            try {
                const response = await fetch('/api/fe-platform/account-switcher/');
                return await response.json();
            } catch (e) {
                return { error: e.toString() };
            }
        }
        """
        
        res_accounts = await page.evaluate(js_get_accounts)
        if not res_accounts or "error" in res_accounts:
            err = res_accounts.get("error", "Unknown error") if res_accounts else "Empty payload"
            print(f"Error calling account switcher API: {err}")
            await browser.close()
            return
            
        accounts = []
        if isinstance(res_accounts, dict) and "accounts" in res_accounts:
            accounts = res_accounts["accounts"]
        elif isinstance(res_accounts, list):
            accounts = res_accounts
            
        if not accounts:
            print("No accounts found in account switcher response.")
            await browser.close()
            return
            
        print(f"Discovered {len(accounts)} organization(s). Resolving IDs and UUIDs...\n")
        
        results = []
        
        for idx, acct in enumerate(accounts):
            name = acct.get("name")
            raw_url = acct.get("url", "")
            raw_id = acct.get("id", "")
            
            # Extract org_id / primary key
            org_id = None
            if ":" in raw_id:
                org_id = raw_id.split(":")[-1]
            else:
                match = re.search(r'/o/(\d+)/|/c/(\d+)/', raw_url)
                if match:
                    org_id = match.group(1) or match.group(2)
                    
            if not org_id:
                print(f"[{idx+1}/{len(accounts)}] Skipping '{name}' (Could not extract org_id)")
                continue
                
            print(f"[{idx+1}/{len(accounts)}] Resolving '{name}' (Org ID: {org_id})...")
            
            # 2. Get the redirect target URL (to resolve firm_id)
            js_redirect = f"""
            async () => {{
                try {{
                    const res = await fetch('/api/profiles/landing-page-redirect/o/{org_id}/');
                    return res.url;
                }} catch (e) {{
                    return null;
                }}
            }}
            """
            redirect_url = await page.evaluate(js_redirect)
            
            if not redirect_url or "/portfolio/" not in redirect_url:
                print(f"  -> Failed to resolve redirect URL.")
                results.append({"name": name, "org_id": org_id, "error": "Redirect failed"})
                continue
                
            firm_match = re.search(r'/individual/(\d+)', redirect_url)
            firm_id = firm_match.group(1) if firm_match else None
            
            # 3. Fetch investments list JSON to extract entity_id
            js_fetch_investments = f"""
            async () => {{
                const urls = [
                    '/api/investors/portfolio/firm/{org_id}/list_individual_portfolio_investments/{firm_id}/list/',
                    '/api/investors/portfolio/firm/{org_id}/list_firm_investments/'
                ];
                
                for (const url of urls) {{
                    try {{
                        const res = await fetch(url);
                        if (res.status === 200) {{
                            return await res.json();
                        }}
                    }} catch (e) {{
                        // ignore
                    }}
                }}
                return null;
            }}
            """
            
            inv_payload = await page.evaluate(js_fetch_investments)
            
            entity_id = None
            if inv_payload:
                items = []
                if isinstance(inv_payload, list):
                    items = inv_payload
                elif isinstance(inv_payload, dict):
                    for key in ["investments", "results", "data", "items"]:
                        if key in inv_payload and isinstance(inv_payload[key], list):
                            items = inv_payload[key]
                            break
                    if not items:
                        for val in inv_payload.values():
                            if isinstance(val, list):
                                items = val
                                break
                                
                for item in items:
                    if isinstance(item, dict):
                        entity_id = (
                            item.get("corporation_id")
                            or item.get("entity_id")
                            or item.get("entityId")
                            or item.get("portfolio_id")
                            or item.get("portfolioId")
                        )
                        if entity_id:
                            if isinstance(entity_id, str) and ":" in entity_id:
                                entity_id = entity_id.split(":")[-1]
                            break
                            
            if not entity_id:
                print("  -> Could not resolve entity_id from portfolio list.")
                results.append({
                    "name": name,
                    "org_id": org_id,
                    "firm_id": firm_id,
                    "error": "No entity_id found in portfolio"
                })
                continue
                
            # 4. Fetch tabs payload
            tabs_url = f"/api/investors/portfolio/fund/{firm_id}/entity/{entity_id}/tabs/"
            js_tabs = f"""
            async () => {{
                try {{
                    const res = await fetch('{tabs_url}');
                    if (res.status === 200) {{
                        return await res.json();
                    }}
                    
                    const alt_url = '/api/investors/portfolio/firm/{org_id}/company/{entity_id}/firm_entity_tabs';
                    const res_alt = await fetch(alt_url);
                    if (res_alt.status === 200) {{
                        return await res_alt.json();
                    }}
                    return {{ error: "Status " + res.status + " / " + res_alt.status }};
                }} catch (e) {{
                    return {{ error: e.toString() }};
                }}
            }}
            """
            
            tabs_data = await page.evaluate(js_tabs)
            if "error" in tabs_data:
                print(f"  -> Error fetching tabs data: {tabs_data['error']}")
                results.append({
                    "name": name,
                    "org_id": org_id,
                    "firm_id": firm_id,
                    "entity_id": entity_id,
                    "error": tabs_data["error"]
                })
                continue
                
            overview = tabs_data.get("overview", {})
            org_uuid = None
            fund_uuid = None
            partner_uuid = None
            partner_id = None
            
            if isinstance(overview, dict):
                org_uuid = overview.get("organization-uuid") or overview.get("organization_uuid")
                fund_uuid = overview.get("fund-uuid") or overview.get("fund_uuid")
                
            for tab_key in ("capital-account-statements", "wire-instructions", "securities-account", "fund-documents"):
                tab_data = tabs_data.get(tab_key, {})
                if isinstance(tab_data, dict):
                    if not org_uuid:
                        org_uuid = tab_data.get("organization_uuid")
                    if not fund_uuid:
                        fund_uuid = tab_data.get("fund_uuid")
                    if not partner_uuid:
                        partner_uuid = (
                            tab_data.get("partner-uuid") 
                            or tab_data.get("partner_interest_group_uuid") 
                            or tab_data.get("fund_admin_partner_uuid")
                        )
                    if not partner_id:
                        partner_id = (
                            tab_data.get("fund_admin_partner_id") 
                            or tab_data.get("fund-admin-partner-id")
                        )
                        
            if not partner_uuid or not partner_id:
                holdings = tabs_data.get("holdings", {})
                if isinstance(holdings, dict):
                    rows = holdings.get("rows", [])
                    if isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], dict):
                        if not partner_uuid:
                            partner_uuid = rows[0].get("fundadmin_partner_uuid")
                        if not partner_id:
                            partner_id = rows[0].get("fundadmin_partner_id")

            # Try to resolve true partner details via fund-admin API using cross-origin fetch
            if org_uuid and fund_uuid:
                js_partner = f"""
                async () => {{
                    try {{
                        const res = await fetch('https://fund-admin.app.carta.com/v2/partners/organization/{org_uuid}/fund/{fund_uuid}/', {{ credentials: 'include' }});
                        if (res.status === 200) {{
                            const data = await res.json();
                            if (Array.isArray(data) && data.length > 0) {{
                                return data[0];
                            }}
                        }}
                    }} catch (e) {{
                        // ignore
                    }}
                    return null;
                }}
                """
                partner_info = await page.evaluate(js_partner)
                if partner_info:
                    resolved_partner_id = partner_info.get("id")
                    resolved_partner_uuid = partner_info.get("uuid")
                    if resolved_partner_id:
                        partner_id = resolved_partner_id
                    if resolved_partner_uuid:
                        partner_uuid = resolved_partner_uuid
                            
            print(f"  -> Success! [entity_id={entity_id}]")
            
            results.append({
                "name": name,
                "org_id": org_id,
                "firm_id": firm_id,
                "entity_id": entity_id,
                "org_uuid": org_uuid,
                "fund_uuid": fund_uuid,
                "partner_uuid": partner_uuid,
                "partner_id": partner_id
            })
            
        await browser.close()
        
        # Save to JSON
        with open("config/resolved_organizations.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        print("\n====================================================================")
        print("                        RESOLVED MAPPINGS                           ")
        print("====================================================================\n")
        
        # Render markdown table to console
        headers = ["Organization Name", "Org ID", "Firm ID", "Entity ID", "Org UUID", "Fund UUID", "Partner ID", "Partner UUID"]
        col_widths = [max(len(str(r.get(k.lower().replace(" ", "_"), ""))) for r in results) for k in headers]
        col_widths = [max(w, len(h)) for w, h in zip(col_widths, headers)]
        
        # Print headers
        header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
        sep_line = "-+-".join("-" * w for w in col_widths)
        print(header_line)
        print(sep_line)
        
        for r in results:
            row_data = [
                r.get("name", "N/A"),
                r.get("org_id", "N/A"),
                r.get("firm_id", "N/A"),
                r.get("entity_id", "N/A"),
                r.get("org_uuid", "N/A") or "N/A",
                r.get("fund_uuid", "N/A") or "N/A",
                r.get("partner_id", "N/A") or "N/A",
                r.get("partner_uuid", "N/A") or "N/A"
            ]
            row_line = " | ".join(f"{str(val):<{w}}" for val, w in zip(row_data, col_widths))
            print(row_line)
            
        print(f"\nSaved successfully to: config/resolved_organizations.json\n")

if __name__ == "__main__":
    asyncio.run(resolve_orgs())
