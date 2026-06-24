import json, os
path = 'frontend/data/business_data.json'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    nodes = data.get('entity_graph', {}).get('nodes', [])
    unknowns = [n for n in nodes if n.get('name', '').lower() == 'unknown' or not n.get('name')]
    print(f'Total nodes: {len(nodes)}')
    print(f'Unknown nodes: {len(unknowns)}')
    for n in unknowns[:10]:
        print(f"  - {n.get('id')}: {n.get('type')}")
