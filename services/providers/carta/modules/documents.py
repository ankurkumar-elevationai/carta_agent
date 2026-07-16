from typing import Dict, Any, Set, Optional
import logging
import re
from .base import ExtractionModule

log = logging.getLogger(__name__)

class DocumentsModule(ExtractionModule):
    @property
    def name(self) -> str:
        return "documents"

    @property
    def dependencies(self) -> Set[str]:
        return {"investment"}

    @property
    def ttl_seconds(self) -> int:
        return 86400  # 24 hours

    async def _resolve_gp_investor_id(self, direct_fetch: Any, firm_id: int) -> Optional[int]:
        try:
            client = await direct_fetch._get_client()
            auth = await direct_fetch.session_manager.get_auth_context()
            
            headers = {
                "User-Agent": auth.user_agent,
                "Accept": "*/*",
                "X-CSRFToken": auth.csrf_token,
                "Referer": "https://app.carta.com",
            }
            
            url = f"https://app.carta.com/api/profiles/landing-page-redirect/o/{firm_id}/"
            response = await client.get(
                url,
                headers=headers,
                cookies=auth.cookies,
                follow_redirects=False
            )
            
            location = response.headers.get("Location") or ""
            match = re.search(r"/individual/(\d+)/", location)
            if match:
                return int(match.group(1))
        except Exception as e:
            log.warning(f"[DocumentsModule] Failed to resolve GP investor ID for firm_id {firm_id}: {e}")
        return None

    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        log.info("[DocumentsModule] Starting extraction...")
        direct_fetch = context["direct_fetch"]
        firm_id = context["firm_id"]
        entity_id = context.get("entity_id")
        
        if not entity_id:
            investments = dependency_data.get("investment")
            if isinstance(investments, dict):
                overview = investments.get("overview", {})
                if isinstance(overview, dict):
                    entity_id = overview.get("entity-id") or overview.get("entity_id")

        # Method A: Try standard LP direct fetch
        log.info(f"[DocumentsModule] Attempting standard fetch (firm_id={firm_id}, entity_id={entity_id})")
        result = await direct_fetch.fetch(
            endpoint_name="get_documents",
            firm_id=firm_id,
            entity_id=entity_id
        )
        
        # If standard fetch fails or is forbidden, try Method B (GP fallback)
        if result.status_code >= 400 or result.error:
            log.info(f"[DocumentsModule] Standard fetch returned {result.status_code}. Attempting GP investor ID resolution...")
            investor_id = await self._resolve_gp_investor_id(direct_fetch, firm_id)
            if investor_id:
                log.info(f"[DocumentsModule] Resolved GP investor ID to {investor_id}. Re-fetching documents...")
                result = await direct_fetch.fetch(
                    endpoint_name="get_documents",
                    firm_id=investor_id,
                    entity_id=entity_id
                )
        
        if result.error and result.status_code >= 400:
            raise RuntimeError(f"Failed to fetch documents: {result.error}")
            
        payload = result.payload
        
        # Download the physical PDFs concurrently
        if isinstance(payload, dict) and "results" in payload:
            results = payload["results"]
            if isinstance(results, list) and len(results) > 0:
                import os
                import shutil
                
                async def _download_doc(doc: dict):
                    doc_url = doc.get("document_url")
                    if not doc_url:
                        return
                        
                    doc_name = doc.get("document_name", "document").replace("/", "-")
                    doc_id = doc.get("id") or doc.get("uuid") or "unknown"
                    base_dir = os.path.join("output", "downloads", "documents", str(firm_id), str(entity_id))
                    output_path = os.path.join(base_dir, f"{doc_name}_{doc_id}.pdf")
                    
                    log.info(f"[DocumentsModule] Downloading document: {doc_name} (ID: {doc_id})")
                    success = await direct_fetch.download_file(doc_url, output_path)
                    
                    if success:
                        doc["local_file_path"] = output_path
                        try:
                            exports_dir = os.path.join("output", "exports", str(entity_id))
                            os.makedirs(exports_dir, exist_ok=True)
                            flat_filename = f"doc_{firm_id}_{entity_id}_{doc_id}.pdf"
                            flat_path = os.path.join(exports_dir, flat_filename)
                            if os.path.exists(flat_path):
                                try:
                                    os.remove(flat_path)
                                except Exception:
                                    pass
                            try:
                                os.link(output_path, flat_path)
                            except OSError:
                                shutil.copy2(output_path, flat_path)
                            doc["download_url"] = f"/files/{entity_id}/{flat_filename}"
                        except Exception as cp_err:
                            log.warning(f"[DocumentsModule] Failed to link/copy to exports: {cp_err}")

                import asyncio
                # HTTPX allows safe parallel downloading. Let's use concurrency = 5.
                semaphore = asyncio.Semaphore(5)
                async def _bounded_download(doc):
                    async with semaphore:
                        await _download_doc(doc)
                        
                tasks = [_bounded_download(doc) for doc in results if isinstance(doc, dict)]
                await asyncio.gather(*tasks)
                log.info(f"[DocumentsModule] Finished downloading {len(tasks)} documents.")

        return payload
