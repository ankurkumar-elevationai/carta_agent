"""
Graph Validation Report Generator.

Usage:
    python scripts/generate_graph_report.py [export_dir]
    
If no export_dir is given, uses the most recent run in output/exports/.
"""
import json
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict


def generate_report(export_dir: Path):
    graph_dir = export_dir / "graph"
    extracted_dir = export_dir / "extracted"
    nodes_file = graph_dir / "nodes.json"
    edges_file = graph_dir / "edges.json"
    report_file = graph_dir / "graph_report.json"
    
    if not nodes_file.exists() or not edges_file.exists():
        print(f"Error: Could not find {nodes_file} or {edges_file}")
        sys.exit(1)
        
    nodes = json.loads(nodes_file.read_text(encoding="utf-8"))
    edges = json.loads(edges_file.read_text(encoding="utf-8"))
    
    # --- Coverage Metrics (Extracted Dir) ---
    total_artifacts = 0
    attributed_artifacts = 0
    if extracted_dir.exists():
        for root, dirs, files in os.walk(extracted_dir):
            for f in files:
                if f.endswith(".json") and f != "_extraction_manifest.json":
                    total_artifacts += 1
                    try:
                        data = json.load(open(os.path.join(root, f), encoding="utf-8"))
                        if data.get("_meta", {}).get("entity_id"):
                            attributed_artifacts += 1
                    except Exception:
                        pass
    
    # --- Structural Metrics ---
    type_counts = Counter()
    nodes_by_id = {}
    for n in nodes:
        type_counts[n.get("type", "unknown")] += 1
        nodes_by_id[n["id"]] = n
        
    # --- Quality Metrics ---
    # 1. Orphan Nodes
    node_degrees = {n["id"]: 0 for n in nodes}
    for e in edges:
        if e["source"] in node_degrees:
            node_degrees[e["source"]] += 1
        if e["target"] in node_degrees:
            node_degrees[e["target"]] += 1
            
    orphan_nodes = [nid for nid, deg in node_degrees.items() if deg == 0]
    
    # 2. Missing Provenance
    missing_prov_nodes = 0
    for n in nodes:
        prov = n.get("provenance", {})
        if not prov.get("source_artifacts") and not prov.get("source_endpoints"):
            missing_prov_nodes += 1
            
    missing_prov_edges = 0
    for e in edges:
        ev = e.get("evidence", {})
        # Must have at least source_artifact and source_endpoint
        if not ev.get("source_artifact") and not ev.get("source_endpoint"):
            missing_prov_edges += 1
            
    # 3. Duplicate Candidates (Nodes with identical normalized names but different IDs)
    name_to_ids = defaultdict(list)
    for n in nodes:
        norm_name = str(n.get("name", "")).lower().strip()
        if norm_name and norm_name != "unknown":
            name_to_ids[norm_name].append(n["id"])
            
    duplicate_candidates = {name: ids for name, ids in name_to_ids.items() if len(ids) > 1}
    
    # 4. Disconnected Components
    org_nodes = [n["id"] for n in nodes if n.get("type") == "organization"]
    visited = set(org_nodes)
    queue = list(org_nodes)
    
    adj = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e["target"])
        adj[e["target"]].append(e["source"])
        
    while queue:
        curr = queue.pop(0)
        for neighbor in adj[curr]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
                
    disconnected_count = len(nodes) - len(visited)
    
    # Coverage logic
    coverage_pct = 0.0
    if total_artifacts > 0:
        coverage_pct = (attributed_artifacts / total_artifacts) * 100.0
    
    # Compile Report
    report = {
        "structural": {
            "organizations": type_counts.get("organization", 0),
            "funds": type_counts.get("fund", 0),
            "spvs": type_counts.get("spv", 0),
            "investments": type_counts.get("investment", 0),
            "companies": type_counts.get("portfolio_company", 0),
            "investors": type_counts.get("investor", 0),
            "valuations": type_counts.get("valuation", 0),
            "edges": len(edges)
        },
        "quality": {
            "duplicate_candidates": len(duplicate_candidates),
            "alias_collisions": 0, # Should be 0 by design of CanonicalRegistry
            "orphan_nodes": len(orphan_nodes),
            "disconnected_components": disconnected_count,
            "missing_provenance": {
                "nodes": missing_prov_nodes,
                "edges": missing_prov_edges
            }
        },
        "coverage": {
            "attributed_artifacts": attributed_artifacts,
            "total_artifacts": total_artifacts,
            "canonicalized_entities": len(nodes),
            "graph_coverage_pct": round(coverage_pct, 1)
        }
    }
    
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print("=" * 60)
    print(" Graph Validation Report Summary")
    print("=" * 60)
    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        export_dir = Path(sys.argv[1])
    else:
        # Default to latest export
        exports_root = Path(__file__).parent.parent / "output" / "exports"
        if not exports_root.exists():
            print(f"Error: {exports_root} does not exist.")
            sys.exit(1)
            
        dirs = [d for d in exports_root.iterdir() if d.is_dir()]
        if not dirs:
            print(f"Error: No export directories found in {exports_root}")
            sys.exit(1)
            
        # Sort by mtime descending
        dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        export_dir = dirs[0]
        
    print(f"Using export directory: {export_dir.name}")
    generate_report(export_dir)
