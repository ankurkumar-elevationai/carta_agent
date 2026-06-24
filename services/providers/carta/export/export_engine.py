import os
import time
import uuid
import logging
import httpx
from typing import Optional, Dict, Any, List

from .export_parser import parse_export
from ..models.extraction import ExportArtifact, BusinessDomain
from ..api.url_builder import URLBuilder

log = logging.getLogger(__name__)

def infer_business_domain(url: str, headers: Dict[str, str], params: Optional[Dict[str, str]] = None) -> BusinessDomain:
    url_lower = url.lower()
    if "capital" in url_lower and "call" in url_lower:
        return BusinessDomain.CAPITAL_CALLS
    if "distribution" in url_lower:
        return BusinessDomain.DISTRIBUTIONS
    if "partner" in url_lower:
        return BusinessDomain.PARTNERS
    if "investment" in url_lower:
        return BusinessDomain.INVESTMENTS
    if "valuation" in url_lower or "409a" in url_lower or "fmv" in url_lower:
        return BusinessDomain.VALUATIONS
    if "cap" in url_lower and "table" in url_lower:
        return BusinessDomain.CAP_TABLE
    if "tax" in url_lower:
        return BusinessDomain.TAX
    if "report" in url_lower or "financial" in url_lower:
        return BusinessDomain.FINANCIAL_REPORTING
    return BusinessDomain.UNKNOWN

class ExportReplayEngine:
    """
    Specialized replay engine for handling Export APIs (CSV/XLSX downloads).
    Hooks into the same authentication context as CartaReplayClient but focuses on streaming
    and parsing binary/tabular payloads instead of JSON structures.
    """
    def __init__(self, auth_context, output_dir: str):
        self.auth_context = auth_context
        self.output_dir = output_dir
        self.exports_dir = os.path.join(output_dir, "exports_raw")
        self.parsed_dir = os.path.join(output_dir, "exports_parsed")
        os.makedirs(self.exports_dir, exist_ok=True)
        os.makedirs(self.parsed_dir, exist_ok=True)
        
    async def download_export(self, 
                              path: str, 
                              params: Optional[Dict[str, Any]], 
                              entity_id: str, 
                              organization_id: str) -> Optional[ExportArtifact]:
        absolute_url = URLBuilder.build_api_url(path)
        base_url = URLBuilder.APP_BASE_URL
        
        headers = {
            "User-Agent": self.auth_context.user_agent,
            "Accept": "*/*",
            "X-CSRFToken": self.auth_context.csrf_token,
            "Referer": base_url,
        }
        
        # Cross-Subdomain handling
        from urllib.parse import urlparse
        if urlparse(absolute_url).netloc != urlparse(base_url).netloc:
            headers.pop("X-CSRFToken", None)
            headers.pop("Referer", None)
            headers.pop("Origin", None)
            
        export_id = uuid.uuid4().hex
        business_domain = infer_business_domain(path, headers, params)
        
        log.info(f"[ExportEngine] Starting download for {business_domain.value} (Entity: {entity_id})")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    absolute_url,
                    headers=headers,
                    cookies=self.auth_context.cookies,
                    params=params
                )
                
            if response.status_code != 200:
                log.warning(f"[ExportEngine] Failed to download export: HTTP {response.status_code} on {path}")
                return None
                
            content_type = response.headers.get("content-type", "").lower()
            content_disposition = response.headers.get("content-disposition", "").lower()
            
            # Infer format
            file_format = "json"
            if "csv" in content_type or "csv" in content_disposition or "format=csv" in path.lower() or ".csv" in path.lower():
                file_format = "csv"
            elif "spreadsheet" in content_type or "excel" in content_type or "xlsx" in content_disposition or ".xlsx" in path.lower():
                file_format = "xlsx"
            elif "pdf" in content_type or ".pdf" in path.lower():
                file_format = "pdf"
                
            content_bytes = response.content
            
            # Save Raw
            safe_name = f"{entity_id}_{business_domain.value}_{export_id}.{file_format}"
            raw_path = os.path.join(self.exports_dir, safe_name)
            with open(raw_path, "wb") as f:
                f.write(content_bytes)
                
            # Parse
            parsed_rows = parse_export(content_bytes, file_format)
            
            artifact = ExportArtifact(
                export_id=export_id,
                entity_id=entity_id,
                organization_id=organization_id,
                business_domain=business_domain.value,
                source_url=path,
                file_format=file_format,
                raw_file_path=raw_path,
                row_count=len(parsed_rows),
                parsed_rows=parsed_rows,
                timestamp=time.time()
            )
            
            # Save Parsed
            import json
            parsed_path = os.path.join(self.parsed_dir, f"{safe_name}.json")
            with open(parsed_path, "w", encoding="utf-8") as f:
                # Need to dump msgspec struct or just dict representation
                import msgspec
                f.write(msgspec.json.encode(artifact).decode("utf-8"))
                
            log.info(f"[ExportEngine] Export complete: {file_format.upper()} with {len(parsed_rows)} rows. Saved to {parsed_path}")
            return artifact
            
        except Exception as e:
            log.error(f"[ExportEngine] Exception during download on {path}: {e}")
            return None
