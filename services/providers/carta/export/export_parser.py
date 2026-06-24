import csv
import io
import logging
from typing import List, Dict, Any

log = logging.getLogger(__name__)

def parse_csv(content: bytes) -> List[Dict[str, Any]]:
    """Parse CSV bytes into a list of dictionaries."""
    try:
        text = content.decode('utf-8-sig') # Handle BOM if present
        reader = csv.DictReader(io.StringIO(text))
        return [row for row in reader]
    except Exception as e:
        log.error(f"[ExportParser] Failed to parse CSV: {e}")
        return []

def parse_xlsx(content: bytes) -> List[Dict[str, Any]]:
    """Parse XLSX bytes into a list of dictionaries using openpyxl."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
        sheet = wb.active
        
        rows = list(sheet.rows)
        if not rows:
            return []
            
        # First row is header
        headers = [str(cell.value) if cell.value is not None else f"col_{i}" for i, cell in enumerate(rows[0])]
        
        result = []
        for row in rows[1:]:
            record = {}
            for i, cell in enumerate(row):
                if i < len(headers):
                    record[headers[i]] = cell.value
            # Only append if row isn't entirely empty
            if any(v is not None and v != "" for v in record.values()):
                result.append(record)
                
        return result
    except ImportError:
        log.warning("[ExportParser] openpyxl is not installed. Skipping XLSX parsing.")
        return []
    except Exception as e:
        log.error(f"[ExportParser] Failed to parse XLSX: {e}")
        return []

def parse_export(content: bytes, file_format: str) -> List[Dict[str, Any]]:
    """Parse raw bytes into structured JSON based on file format."""
    if file_format.lower() == "csv":
        return parse_csv(content)
    elif file_format.lower() == "xlsx":
        return parse_xlsx(content)
    elif file_format.lower() == "json":
        try:
            import json
            data = json.loads(content)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            return [data]
        except Exception:
            pass
    return []
