import logging
import asyncio
from typing import Optional

from .db.session import init_db, get_session, async_session_maker
from .db.repositories import (
    EntityRepository, RouteRepository, CapabilityRepository, 
    SchemaRepository, TraversalJobRepository
)
from .harvester import URLHarvester
from .service_classifier import ServiceClassifier
from .intelligence import EndpointRegistry

log = logging.getLogger(__name__)

class CapabilityTraversalEngine:
    """
    Orchestrates the recursive discovery of Carta APIs.
    Implements BFS traversal, cycle detection, and concurrency limits.
    """
    
    def __init__(self, replay_client, max_concurrency: int = 5, max_depth: int = 5):
        self.client = replay_client
        self.max_concurrency = max_concurrency
        self.max_depth = max_depth
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.visited = set()

    async def initialize(self):
        await init_db()

    async def run_discovery(self, seed_url: str):
        """Starts discovery from a single capability descriptor payload."""
        if async_session_maker is None:
            log.error("[TraversalEngine] DB not initialized.")
            return

        log.info(f"[TraversalEngine] Starting discovery at seed: {seed_url}")
        
        async with async_session_maker() as session:
            job_repo = TraversalJobRepository(session)
            
            # Queue the seed job
            await job_repo.create(url=seed_url, depth=0)
            await session.commit()
            
            # Start worker loop
            await self._worker_loop()

    async def _worker_loop(self):
        """Pulls jobs from the DB and processes them with concurrency limits."""
        while True:
            async with async_session_maker() as session:
                job_repo = TraversalJobRepository(session)
                
                # Fetch next pending job (BFS ordering by created_at)
                job = await job_repo.get_pending()
                if not job:
                    log.info("[TraversalEngine] Queue empty. Discovery complete.")
                    break
                
                # Mark as processing
                await job_repo.mark_status(job.id, "processing")
                await session.commit()

            # Process the job
            async with self.semaphore:
                await self._process_job(job.id, job.url, job.depth, job.parent_url)

    async def _process_job(self, job_id: str, url: str, depth: int, parent_url: Optional[str]):
        """Executes a single API fetch, extracts schemas, and enqueues children."""
        log.info(f"[TraversalEngine] Processing depth {depth}: {url}")
        
        # Cycle detection
        normalized_url = url.split("?")[0]
        if normalized_url in self.visited:
            await self._mark_job(job_id, "completed", "Cycle detected. Already visited.")
            return
        
        if depth > self.max_depth:
            await self._mark_job(job_id, "completed", "Max depth reached.")
            return

        self.visited.add(normalized_url)

        try:
            # 1. Fetch
            res = await self.client.get(url, tags={"operation": "discovery_traversal"})
            payload = res.payload if hasattr(res, "payload") else {}

            async with async_session_maker() as session:
                entity_repo = EntityRepository(session)
                route_repo = RouteRepository(session)
                cap_repo = CapabilityRepository(session)
                schema_repo = SchemaRepository(session)
                job_repo = TraversalJobRepository(session)
                registry = EndpointRegistry(route_repo, schema_repo)

                # 2. Extract Entity if it's the root (depth 0)
                entity_id = None
                if depth == 0:
                    entity = await entity_repo.create_or_update(source_url=url, payload=payload)
                    entity_id = entity.id

                # 3. Classify & Register Endpoint
                service = ServiceClassifier.infer_service(url)
                cap_type = ServiceClassifier.classify(url)
                
                route = await registry.register(
                    endpoint=normalized_url,
                    method="GET",
                    service=service,
                    capability_type=cap_type.value,
                    depth=depth,
                    payload=payload,
                    parent_url=parent_url
                )

                # 4. Save Capability Link if we have an entity
                if entity_id:
                    await cap_repo.create(entity_id=entity_id, route_id=route.id, payload=payload)

                # 5. Extract Child URLs
                child_urls = URLHarvester.harvest(payload)
                for child_url in child_urls:
                    if child_url.split("?")[0] not in self.visited:
                        await job_repo.create(url=child_url, depth=depth + 1, parent_url=url)
                        log.info(f"[TraversalEngine] Enqueued child: {child_url}")

                # 6. Mark Complete
                await job_repo.mark_status(job_id, "completed")
                await session.commit()

        except Exception as e:
            log.error(f"[TraversalEngine] Failed to process {url}: {e}")
            await self._mark_job(job_id, "failed", str(e))

    async def _mark_job(self, job_id: str, status: str, msg: str = None):
        async with async_session_maker() as session:
            job_repo = TraversalJobRepository(session)
            await job_repo.mark_status(job_id, status, msg)
            await session.commit()
