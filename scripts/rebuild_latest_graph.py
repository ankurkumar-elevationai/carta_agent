import sys
import os
import json
import shutil
from pathlib import Path

# Add project root to sys.path so we can import services
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.providers.carta.intelligence.graph_builder import EntityGraphBuilder
from services.providers.carta.models.extraction import DiscoveredEntity

def rebuild_latest_graph():
    exports_root = project_root / "output" / "exports"
    if not exports_root.exists():
        print(f"Error: {exports_root} does not exist.")
        sys.exit(1)
        
    dirs = [d for d in exports_root.iterdir() if d.is_dir()]
    if not dirs:
        print(f"Error: No export directories found in {exports_root}")
        sys.exit(1)
        
    # Sort by mtime descending
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    latest_export = dirs[0]
    
    print(f"Using export directory: {latest_export.name}")
    
    extracted_dir = latest_export / "extracted"
    graph_out_dir = latest_export / "graph"
    
    if not extracted_dir.exists():
        print(f"Error: Could not find extracted directory at {extracted_dir}")
        sys.exit(1)
        
    # Reconstruct DiscoveredEntity objects from extracted files
    entities = {}
    for root, _, files in os.walk(extracted_dir):
        for f in files:
            if f.endswith(".json") and f != "_extraction_manifest.json":
                try:
                    path = Path(root) / f
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        
                    if not isinstance(data, dict):
                        continue
                        
                    meta = data.get("_meta", {})
                    ent_id = meta.get("entity_id")
                    
                    if ent_id and ent_id not in entities:
                        entities[ent_id] = DiscoveredEntity(
                            entity_id=ent_id,
                            name=meta.get("entity_name", "unknown"),
                            entity_type=meta.get("entity_type", "unknown"),
                            detail_url=meta.get("source_url", ""),
                            parent_org_pk=meta.get("org_pk")
                        )
                except Exception as e:
                    print(f"Error loading entity from {f}: {e}")
            
    entity_list = list(entities.values())
    
    # Try to extract firm info from the name if possible
    firm_name = latest_export.name.split("_", 1)[1].replace("_", " ").title()
    
    # Dynamically resolve firm_id from extracted entities
    firm_id = 0
    for ent in entity_list:
        if ent.parent_org_pk:
            firm_id = int(ent.parent_org_pk)
            break
            
    print(f"Loaded {len(entity_list)} unique entities from extraction payloads.")
    print("Building canonical graph...")
    
    builder = EntityGraphBuilder(
        extracted_dir=extracted_dir,
        output_dir=graph_out_dir,
        entity_manifest=entity_list,
        firm_id=firm_id,
        firm_name=firm_name
    )
    
    graph = builder.build()
    
    print(f"Graph built successfully: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
    
    # Copy to frontend
    frontend_data_dir = project_root / "frontend" / "data"
    frontend_data_dir.mkdir(parents=True, exist_ok=True)
    
    shutil.copy2(graph_out_dir / "nodes.json", frontend_data_dir / "nodes.json")
    shutil.copy2(graph_out_dir / "edges.json", frontend_data_dir / "edges.json")
    
    print(f"Graph data copied to {frontend_data_dir}")
    print("Refresh your browser to see the canonicalized data!")

if __name__ == "__main__":
    rebuild_latest_graph()
