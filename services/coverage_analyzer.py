import datetime
from typing import Dict, Any, List
from pydantic import BaseModel
from .platform_mapper import PlatformSchemaMapper
from .platform_schema import PlatformBaseModel

class CoverageAnalyzer:
    """Generates field population statistics for the Platform Schema."""

    def __init__(self, mapper: PlatformSchemaMapper):
        self.mapper = mapper
        
    def analyze(self) -> Dict[str, Any]:
        """Run all mappers and build coverage stats."""
        
        # Mappers corresponding to the 19 tables
        table_mappers = {
            "inv_investment": self.mapper.map_inv_investment,
            "inv_asset_extra_info": self.mapper.map_inv_asset_extra_info,
            "inv_asset_team": self.mapper.map_inv_asset_team,
            "inv_asset_valuation": self.mapper.map_inv_asset_valuation,
            "inv_cap_call": self.mapper.map_inv_cap_call,
            "investment_log": self.mapper.map_investment_log,
            "inv_investment_transaction": self.mapper.map_inv_investment_transaction,
            "inv_investment_firm": self.mapper.map_inv_investment_firm,
            "inv_investment_focus": self.mapper.map_inv_investment_focus,
            "inv_investment_sector": self.mapper.map_inv_investment_sector,
            "inv_investment_certificate": self.mapper.map_inv_investment_certificate,
            "inv_investment_distribution_history": self.mapper.map_inv_investment_distribution_history,
            "inv_liquidity_distribution": self.mapper.map_inv_liquidity_distribution,
            "inv_investment_expense": self.mapper.map_inv_investment_expense,
            "inv_investment_interest": self.mapper.map_inv_investment_interest,
            "inv_investment_service": self.mapper.map_inv_investment_service,
            "inv_asset_usage_log": self.mapper.map_inv_asset_usage_log,
            "extra_info_recent_development": self.mapper.map_extra_info_recent_development,
            "research_growing_traction": self.mapper.map_research_growing_traction,
        }

        stats = {
            "schema_version": "v1",
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "provider": "carta", # Currently hardcoded to carta context
            "tables": {},
            "summary": {
                "total_tables": 19,
                "tables_with_data": 0,
                "tables_empty": 0,
                "overall_field_coverage_pct": 0.0
            }
        }

        total_fields_all = 0
        populated_fields_all = 0

        for table_name, func in table_mappers.items():
            records: List[PlatformBaseModel] = func()
            
            if not records:
                stats["tables"][table_name] = {
                    "total_fields": 0,
                    "populated": 0,
                    "coverage_pct": 0.0,
                    "status": "EMPTY"
                }
                stats["summary"]["tables_empty"] += 1
                continue
                
            stats["summary"]["tables_with_data"] += 1
            
            # Use the first record to get the schema fields
            sample = records[0]
            fields = sample.model_fields
            
            table_total = len(fields)
            table_populated = 0
            
            field_stats = {}
            for field_name in fields.keys():
                # Count how many records have this field populated (not None)
                populated_count = sum(1 for r in records if getattr(r, field_name) is not None)
                is_populated = populated_count > 0
                
                if is_populated:
                    table_populated += 1
                    
                field_stats[field_name] = {
                    "populated": is_populated,
                    "populated_pct": round((populated_count / len(records)) * 100, 1)
                }

            total_fields_all += table_total
            populated_fields_all += table_populated

            stats["tables"][table_name] = {
                "total_fields": table_total,
                "populated": table_populated,
                "coverage_pct": round((table_populated / table_total) * 100, 1) if table_total else 0.0,
                "record_count": len(records),
                "fields": field_stats
            }

        if total_fields_all > 0:
            stats["summary"]["overall_field_coverage_pct"] = round((populated_fields_all / total_fields_all) * 100, 1)

        return stats
