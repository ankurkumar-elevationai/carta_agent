import duckdb
import logging
from typing import Optional

log = logging.getLogger(__name__)

class DuckDBAnalytics:
    def __init__(self, db_path: str = "storage/analytics/carta.duckdb"):
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        log.info(f"[DuckDB] Connected to {db_path}")
        
    def query_entities(self, entity_type: Optional[str] = None):
        """Query normalized entities using Polars DataFrames."""
        try:
            import polars as pl
            query = "SELECT * FROM read_parquet('storage/raw/requests/*.parquet')"
            if entity_type:
                query += f" WHERE resource_type = '{entity_type}'"
                
            return self.conn.execute(query).pl()
        except Exception as e:
            log.error(f"[DuckDB] Failed to query entities: {e}")
            return None
            
    def close(self):
        self.conn.close()
