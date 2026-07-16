"""
Export Frontend Data — v2 (Complete)
====================================
Scans every JSON file inside the latest output/exports/<run>/extracted/,
    extracts ALL business data and writes output/business_data.json.
"""
import sys, os, json, re
from pathlib import Path
from collections import defaultdict

def compile_extracted_data(latest_dir: Path, target_company: str = None) -> dict:
    """
    Scans the extracted files inside the given export run directory
    and compiles it into a single, canonical business data structure.
    """
    extracted_dir = latest_dir / "extracted"
    
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
        
    # First-pass scan to build ID to Name mapping dynamically
    id_to_name = {}
    if extracted_dir.exists():
        for root, _, files in os.walk(extracted_dir):
            for fname in files:
                if not fname.endswith(".json") or fname.startswith("_"):
                    continue
                fpath = Path(root) / fname
                try:
                    raw = json.loads(fpath.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(raw, dict) or "data" not in raw:
                    continue
                data = raw["data"]
                
                # Check for source_url to map UUIDs
                source_url = raw.get("_meta", {}).get("source_url", "")
                if source_url:
                    # Prioritize investment UUIDs first
                    uuid_match = re.search(r"/(portfolio|entity|corporation|fund)/([a-f0-9\-]{36})", source_url)
                    if not uuid_match:
                        uuid_match = re.search(r"/(org|organization|partners)/([a-f0-9\-]{36})", source_url)
                    if uuid_match:
                        uuid_val = uuid_match.group(2)
                        # Try to find name in data
                        f_name = None
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    f_name = item.get("legal_name") or item.get("partner", {}).get("fund_name")
                                    if f_name:
                                        break
                        elif isinstance(data, dict):
                            f_name = data.get("legal_name") or data.get("partner", {}).get("fund_name")
                        if f_name:
                            id_to_name[uuid_val] = f_name

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            cid = item.get("corporation_id")
                            cname = item.get("legal_name")
                            if cid and cname:
                                id_to_name[str(cid)] = cname
                            
                            partner = item.get("partner")
                            if isinstance(partner, dict):
                                cid = partner.get("fund_carta_id")
                                cname = partner.get("fund_name")
                                if cid and cname:
                                    id_to_name[str(cid)] = cname
                elif isinstance(data, dict):
                    partner = data.get("partner")
                    if isinstance(partner, dict):
                        cid = partner.get("fund_carta_id")
                        cname = partner.get("fund_name")
                        if cid and cname:
                            id_to_name[str(cid)] = cname
                    results = data.get("results")
                    if isinstance(results, list):
                        for item in results:
                            if isinstance(item, dict):
                                cid = item.get("fund_id") or item.get("corporation_id")
                                cname = item.get("fund_name") or item.get("legal_name")
                                if cid and cname:
                                    id_to_name[str(cid)] = cname
                                doc_id = item.get("fund_id")
                                doc_name = item.get("fund_name")
                                if doc_id and doc_name:
                                    id_to_name[str(doc_id)] = doc_name

    file_count = 0
    if extracted_dir.exists():
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
                entity_name = meta.get("entity_name", "")
                entity_id = meta.get("entity_id", "")

                # Try to extract entity ID or UUID from URL if not present
                if not entity_id and source_url:
                    entity_id_match = re.search(r"/(portfolio|entity|corporation|fund)/(\d+)(?:/|$)", source_url)
                    if entity_id_match:
                        entity_id = entity_id_match.group(2)
                    else:
                        uuid_match = re.search(r"/(portfolio|entity|corporation|fund)/([a-f0-9\-]{36})", source_url)
                        if not uuid_match:
                            uuid_match = re.search(r"/(org|organization|partners)/([a-f0-9\-]{36})", source_url)
                        if uuid_match:
                            entity_id = uuid_match.group(2)

                # Resolve company name
                if entity_id and str(entity_id) in id_to_name:
                    entity_name = id_to_name[str(entity_id)]
                elif (not entity_name or entity_name == "unknown") and entity_id and str(entity_id) in id_to_name:
                    entity_name = id_to_name[str(entity_id)]

                company = entity_name or entity_id or "unknown"

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

                # ── Handle list-based endpoints before restricting to dict ──
                if isinstance(data, list):
                    # ── 7b. LP Metrics (v2 partners metrics) ───────────────────
                    if "v2/partners" in source_url and "metrics" in source_url:
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            partner = item.get("partner", {})
                            m = item.get("metrics", {})
                            if not partner or not m:
                                continue
                            
                            f_name = partner.get("fund_name")
                            f_id = partner.get("fund_carta_id")
                            comp_key = f_name or f_id or company
                            
                            if comp_key not in holdings_dashboard:
                                holdings_dashboard[comp_key] = {}
                            
                            commitment = float(m.get("commitment", 0) or 0)
                            called_capital = float(m.get("called_capital", 0) or 0)
                            nav = float(m.get("net_asset_value", 0) or 0)
                            distributions = float(m.get("distributions", 0) or 0)
                            multiple = (nav / called_capital) if called_capital > 0 else 0.0
                            
                            holdings_dashboard[comp_key].update({
                                "commitment": commitment,
                                "called_capital": called_capital,
                                "net_asset_value": nav,
                                "distributions": distributions,
                                "cash_cost": called_capital,
                                "value": nav,
                                "multiple": multiple,
                                "currency": partner.get("fund_currency", "USD"),
                                "held_since": f"{m.get('vintage_year', '—')}",
                            })
                            
                            # Also update valuations
                            if comp_key not in valuations:
                                valuations[comp_key] = {}
                            valuations[comp_key].update({
                                "post_money": nav,
                                "funds_raised": commitment,
                                "share_class": "LP Interest",
                                "currency": partner.get("fund_currency", "$"),
                            })

                    # ── 10b. LP Primary Contacts ───────────────────────────────
                    if "list-primary-partner-contacts" in source_url:
                        if company not in contacts:
                            contacts[company] = []
                        for c in data:
                            if isinstance(c, dict):
                                email = c.get("primary_contact_email", "")
                                name = email.split("@")[0].replace(".", " ").title() if email else "Primary Contact"
                                if not any(x.get("email") == email for x in contacts[company]):
                                    contacts[company].append({
                                        "name": name,
                                        "email": email,
                                        "is_primary": True,
                                        "title": "Primary Contact",
                                    })
                    continue

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
                        "valuation_date": data.get("date") or data.get("valuation_date") or data.get("as_of_date") or data.get("effectiveDate") or data.get("effective_date"),
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
                elif "holdings" in data and isinstance(data["holdings"], dict):
                    h_rows = data["holdings"].get("rows", [])
                    if isinstance(h_rows, list) and len(h_rows) > 0:
                        row = h_rows[0]
                        if isinstance(row, dict):
                            nav_cents = row.get("net_asset_value")
                            contrib_cents = row.get("contributed_paid") or row.get("contributed") or row.get("capital_called")
                            
                            nav = round(float(nav_cents) / 100.0, 2) if nav_cents is not None else 0.0
                            cost = round(float(contrib_cents) / 100.0, 2) if contrib_cents is not None else 0.0
                            
                            holdings_dashboard[company] = {
                                "investing_spv": row.get("fund_name"),
                                "held_since": str(row.get("vintage_year", "")).replace(".0", ""),
                                "cash_cost": cost,
                                "net_asset_value": nav,
                                "multiple": round((nav / cost), 2) if cost > 0 else 0.0,
                                "currency": row.get("fund_currency", "USD")
                            }
                            
                            # Also update valuations so that canonical store has a valuation registered for this fund investment
                            if company not in valuations:
                                valuations[company] = {}
                            valuations[company].update({
                                "post_money": nav,
                                "funds_raised": row.get("committed", 0.0) / 100.0 if row.get("committed") is not None else 0.0,
                                "share_class": "LP Interest",
                                "currency": row.get("fund_currency", "USD"),
                                "valuation_date": row.get("lp_sharing_date"),
                            })



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

                # ── 9b. LP Transactions & Performance ───────────────────────
                if "transactions" in source_url and isinstance(data, dict) and "results" in data:
                    results = data["results"]
                    txs = []
                    total_debit = 0.0
                    total_credit = 0.0
                    for tx in results:
                         if not isinstance(tx, dict):
                             continue
                         t_type = tx.get("transaction_type", "")
                         t_date = tx.get("transaction_date", "")
                         t_amount = float(tx.get("amount", 0) or 0)
                         
                         is_outflow = any(x in t_type.lower() for x in ["contribution", "payment", "call", "debit"])
                         is_inflow = any(x in t_type.lower() for x in ["distribution", "credit", "return"])
                         
                         debit = t_amount if is_outflow else 0.0
                         credit = t_amount if is_inflow else 0.0
                         
                         if not is_outflow and not is_inflow:
                             if "distribution" in t_type.lower():
                                 credit = t_amount
                             else:
                                 debit = t_amount
                                 
                         total_debit += debit
                         total_credit += credit
                         
                         txs.append({
                             "id": tx.get("id"),
                             "date": t_date,
                             "type": t_type,
                             "amount": t_amount,
                             "debit": debit,
                             "credit": credit,
                             "notes": tx.get("notes"),
                         })
                    
                    if company not in irr_performance:
                        irr_performance[company] = {}
                    
                    existing_mult = irr_performance[company].get("multiple") or holdings_dashboard.get(company, {}).get("multiple")
                    irr_performance[company].update({
                        "irr_percentage": irr_performance[company].get("irr_percentage") or holdings_dashboard.get(company, {}).get("irr_percentage"),
                        "multiple": existing_mult or (total_credit / total_debit if total_debit > 0 else 0.0),
                        "transactions_count": len(txs),
                        "transactions": txs,
                    })

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

    # ── Handle 409A FMV data (top-level list responses) ─────────────────
    if extracted_dir.exists():
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
                    if str(company) in investments_list:
                        company = investments_list[str(company)].get("legal_name") or company
                    
                    if company not in fmv_409a:
                        fmv_409a[company] = []
                        
                    for item in data:
                        if isinstance(item, dict):
                            if "fmvs" in item and isinstance(item["fmvs"], list):
                                # Global format: list of companies containing fmvs
                                portco_id = str(item.get("portco", {}).get("id", ""))
                                matched_company = company
                                if portco_id in investments_list:
                                    matched_company = investments_list[portco_id].get("legal_name") or company
                                if matched_company not in fmv_409a:
                                    fmv_409a[matched_company] = []
                                for fmv_item in item["fmvs"]:
                                    p_data = fmv_item.get("price", {})
                                    fmv_id = fmv_item.get("id")
                                    eff_date = fmv_item.get("effectiveDate")
                                    sc_id = fmv_item.get("shareClassId")
                                    
                                    # Deduplicate
                                    exists = False
                                    for x in fmv_409a[matched_company]:
                                        if fmv_id is not None and x.get("id") == fmv_id:
                                            exists = True
                                            break
                                        if fmv_id is None and x.get("effective_date") == eff_date and x.get("share_class_id") == sc_id:
                                            exists = True
                                            break
                                            
                                    if not exists:
                                        fmv_409a[matched_company].append({
                                            "id": fmv_id,
                                            "price": p_data.get("amount") if isinstance(p_data, dict) else None,
                                            "currency": p_data.get("currencyCode") if isinstance(p_data, dict) else None,
                                            "effective_date": eff_date,
                                            "share_class_id": sc_id,
                                            "is_common": fmv_item.get("isCommon"),
                                            "is_primary": fmv_item.get("isPrimary"),
                                        })
                            else:
                                # Company-specific format: list of fmvs directly
                                price_data = item.get("price", {})
                                fmv_id = item.get("id")
                                eff_date = item.get("effectiveDate")
                                sc_id = item.get("shareClassId")
                                
                                # Deduplicate
                                exists = False
                                for x in fmv_409a[company]:
                                    if fmv_id is not None and x.get("id") == fmv_id:
                                        exists = True
                                        break
                                    if fmv_id is None and x.get("effective_date") == eff_date and x.get("share_class_id") == sc_id:
                                        exists = True
                                        break
                                        
                                if not exists:
                                    fmv_409a[company].append({
                                        "id": fmv_id,
                                        "price": price_data.get("amount") if isinstance(price_data, dict) else None,
                                        "currency": price_data.get("currencyCode") if isinstance(price_data, dict) else None,
                                        "effective_date": eff_date,
                                        "share_class_id": sc_id,
                                        "is_common": item.get("isCommon"),
                                        "is_primary": item.get("isPrimary"),
                                    })

    # ── Deduplicate investors ───────────────────────────────────────────
    for name, inv in investors_map.items():
        inv["investments"] = list(set(inv["investments"]))
        inv["total_ownership_pct"] = round(inv["total_ownership_pct"], 4)

    # ── Merge investment data from all sources ──────────────────────────
    merged_investments = []
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
    inventory_path = latest_dir / "export_inventory.json"
    if inventory_path.exists():
        try:
            export_records = json.loads(inventory_path.read_text(encoding="utf-8"))
        except Exception:
            export_records = []

    # ── Extract Entity Graph ────────────────────────────────────────────
    entity_graph = {"nodes": [], "edges": [], "summary": {}}
    graph_path = latest_dir / "graph" / "entity_graph.json"
    if graph_path.exists():
        try:
            entity_graph = json.loads(graph_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Extract Performance Profile ─────────────────────────────────────
    performance_profile = {}
    perf_path = latest_dir / "performance_profile.json"
    if perf_path.exists():
        try:
            performance_profile = json.loads(perf_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Extract Coverage Report ─────────────────────────────────────────
    coverage_report = {}
    cov_path = latest_dir / "coverage_report.json"
    if cov_path.exists():
        try:
            coverage_report = json.loads(cov_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Extract Domain Inventory ────────────────────────────────────────
    domain_inventory = []
    dom_path = latest_dir / "domain_inventory.json"
    if dom_path.exists():
        try:
            domain_inventory = json.loads(dom_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Extract Fund Relationships ──────────────────────────────────────
    fund_relationships = []
    if extracted_dir.exists():
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
    sc_path = latest_dir / "schemas" / "schema_clusters.json"
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

    # ── Target Company Filtering ────────────────────────────────────────
    if target_company:
        def local_normalize(name: str) -> str:
            if not name: return ""
            name = name.lower()
            name = re.sub(r"\(.*?\)", "", name)
            name = re.sub(r"[^a-z0-9\s]", " ", name)
            name = re.sub(r"\s+", " ", name)
            return name.strip()
            
        norm_target = local_normalize(target_company)
        has_match = False
        for inv in merged_investments:
            company_name = inv.get("company", "")
            if local_normalize(company_name) == norm_target or norm_target in local_normalize(company_name) or local_normalize(company_name) in norm_target:
                has_match = True
                break
                
        if has_match:
            filtered_investments = []
            for inv in merged_investments:
                company_name = inv.get("company", "")
                if local_normalize(company_name) == norm_target:
                    filtered_investments.append(inv)
            if not filtered_investments:
                for inv in merged_investments:
                    company_name = inv.get("company", "")
                    if norm_target in local_normalize(company_name) or local_normalize(company_name) in norm_target:
                        filtered_investments.append(inv)
            merged_investments = filtered_investments
            
            # Keep only related cap tables, profiles, securities, etc.
            remaining_companies = {inv.get("company", "") for inv in merged_investments}
            cap_tables = {k: v for k, v in cap_tables.items() if k in remaining_companies}
            company_profiles = {k: v for k, v in company_profiles.items() if k in remaining_companies}
            holdings_dashboard = {k: v for k, v in holdings_dashboard.items() if k in remaining_companies}
            securities = {k: v for k, v in securities.items() if k in remaining_companies}
            fmv_409a = {k: v for k, v in fmv_409a.items() if k in remaining_companies}
            irr_performance = {k: v for k, v in irr_performance.items() if k in remaining_companies}
            contacts = {k: v for k, v in contacts.items() if k in remaining_companies}
            entity_tabs = {k: v for k, v in entity_tabs.items() if k in remaining_companies}

    # ── Ingest Validation Runs & Replay Metrics ────────────────────────
    validation_runs = []
    project_root = latest_dir.parent.parent
    val_runs_path = project_root / "output" / "carta" / "validation_runs.jsonl"
    if val_runs_path.exists():
        try:
            with open(val_runs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        validation_runs.append(json.loads(line))
        except Exception as e:
            print(f"[export] Error reading validation runs: {e}")

    replay_metrics = []
    replay_path = project_root / "output" / "carta" / "replay_metrics.jsonl"
    if replay_path.exists():
        try:
            with open(replay_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        replay_metrics.append(json.loads(line))
        except Exception as e:
            print(f"[export] Error reading replay metrics: {e}")

    # ── Ingest Crawl Runs ───────────────────────────────────────────────
    crawl_runs = []
    exports_root = project_root / "output" / "exports"
    if exports_root.exists():
        for d in exports_root.iterdir():
            if d.is_dir() and d.name != "test_direct_orch_run_mangocart_inc":
                perf_path = d / "performance_profile.json"
                perf_prof = {}
                if perf_path.exists():
                    try:
                        perf_prof = json.loads(perf_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                
                # count JSON files in extracted
                extracted_subdir = d / "extracted"
                json_count = 0
                if extracted_subdir.exists():
                    json_count = len([f for f in extracted_subdir.iterdir() if f.suffix == ".json"])
                
                # Get directory modification time as timestamp
                mtime = d.stat().st_mtime
                import datetime
                dt = datetime.datetime.fromtimestamp(mtime)
                
                crawl_runs.append({
                    "run_id": d.name,
                    "timestamp": dt.isoformat(),
                    "file_count": json_count,
                    "performance_profile": perf_prof,
                    "success": json_count > 0
                })
        
        # Sort crawl runs by timestamp descending
        crawl_runs.sort(key=lambda x: x["timestamp"], reverse=True)

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
        "validation_runs": validation_runs,
        "replay_metrics": replay_metrics,
        "crawl_runs": crawl_runs
    }
    return output

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    exports_root = project_root / "output" / "exports"
    if len(sys.argv) > 1:
        latest = Path(sys.argv[1])
        if not latest.is_absolute():
            latest = exports_root / latest
    else:
        dirs = sorted(
            [d for d in exports_root.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime, reverse=True,
        )
        latest = dirs[0]
        
    print(f"[export] scanning {latest.name}")
    output = compile_extracted_data(latest)
    
    out_dir = project_root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "business_data.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    
    # Copy to frontend folder
    frontend_dir = project_root / "frontend" / "data"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    frontend_path = frontend_dir / "business_data.json"
    frontend_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    
    print(f"[export] Done!")
    print(f"  Firm:              {output['firm'].get('name', 'N/A')}")
    print(f"  Funds:             {output['summary']['total_funds']}")
    print(f"  SPVs:              {output['summary']['total_spvs']}")
    print(f"  Investments:       {output['summary']['total_investments']}")
    print(f"  Investors:         {output['summary']['total_investors']}")
    print(f"  Output:            {out_path}")
    print(f"  Frontend Output:   {frontend_path}")
    print(f"  Output size:       {out_path.stat().st_size / 1024:.0f} KB")
