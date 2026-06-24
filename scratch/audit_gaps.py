import json, os
from collections import Counter

base = 'output/exports/discovery_task_001_krakatoa_ventures/extracted'

# What data types exist but are NOT surfaced on frontend?
unsurfaced_keys = Counter()
sample_payloads = {}

for root, dirs, files in os.walk(base):
    for f in files:
        if not f.endswith('.json') or f.startswith('_'):
            continue
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                d = json.load(fh)
            meta = d.get('_meta', {})
            p = d.get('data', {})
            if not isinstance(p, dict):
                continue
            # Keys NOT currently processed by export_frontend_data.py:
            # Already processed: firm_member, captable, post_money+share_class, holdings, 
            #   ownership, results.contacts, features+permissions, fmv_data, 
            #   corporation_id lists, header+items lists, irr data, securities
            for k in p.keys():
                if k in ('partners',):
                    if isinstance(p[k], list) and len(p[k]) > 0:
                        unsurfaced_keys['partners_list'] += 1
                        if 'partners_list' not in sample_payloads:
                            sample_payloads['partners_list'] = {
                                'entity': meta.get('entity_name',''),
                                'count': len(p[k]),
                                'sample': p[k][0] if p[k] else None
                            }
                if k in ('relationships',):
                    unsurfaced_keys['relationships'] += 1
                    if 'relationships' not in sample_payloads:
                        sample_payloads['relationships'] = {
                            'entity': meta.get('entity_name',''),
                            'value': p[k][:2] if isinstance(p[k], list) else str(p[k])[:200]
                        }
                if k in ('investments',) and isinstance(p[k], list):
                    unsurfaced_keys['fund_investments_list'] += 1
                if k in ('scenario-modeling',):
                    unsurfaced_keys['scenario_modeling'] += 1
                if k in ('overview',) and isinstance(p[k], dict):
                    unsurfaced_keys['fund_overview'] += 1
                    if 'fund_overview' not in sample_payloads:
                        sample_payloads['fund_overview'] = {
                            'entity': meta.get('entity_name',''),
                            'keys': list(p[k].keys())[:15]
                        }
        except:
            pass

print("=== UNSURFACED DATA IN EXTRACTED JSONs ===")
for k, v in unsurfaced_keys.most_common():
    print(f"  {k}: {v} files")

print("\n=== SAMPLES ===")
for k, v in sample_payloads.items():
    print(f"\n--- {k} ---")
    print(json.dumps(v, indent=2, default=str)[:500])

# Also check: what extraction output files are NOT in business_data.json at all
print("\n\n=== OUTPUT FILES NOT IN FRONTEND ===")
top_files = [
    'performance_profile.json',
    'coverage_report.json',
    'domain_inventory.json',
    'domain_api_map.json',
    'workflow_inventory.json',
    'api_family_inventory.json',
]
root_dir = 'output/exports/discovery_task_001_krakatoa_ventures'
for tf in top_files:
    fp = os.path.join(root_dir, tf)
    if os.path.exists(fp):
        sz = os.path.getsize(fp)
        print(f"  {tf} ({sz} bytes) -> NOT shown in frontend")

# Graph
graph_file = os.path.join(root_dir, 'graph', 'entity_graph.json')
if os.path.exists(graph_file):
    with open(graph_file, 'r', encoding='utf-8') as gf:
        g = json.load(gf)
    print(f"  entity_graph.json ({g['summary']['total_nodes']} nodes, {g['summary']['total_edges']} edges) -> NOT shown in frontend")

# Schema clusters
sc_file = os.path.join(root_dir, 'schemas', 'schema_clusters.json')
if os.path.exists(sc_file):
    with open(sc_file, 'r', encoding='utf-8') as sf:
        sc = json.load(sf)
    print(f"  schema_clusters.json ({sc['summary']['total_clusters']} clusters) -> NOT shown in frontend")
