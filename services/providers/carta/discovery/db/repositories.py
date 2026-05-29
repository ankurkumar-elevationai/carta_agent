from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from typing import Optional, List
from .models import CartaEntity, CartaRoute, CartaCapability, CartaSchema, CartaTraversalJob
from datetime import datetime

class EntityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_or_update(self, source_url: str, payload: dict, canonical_id: Optional[str] = None) -> CartaEntity:
        result = await self.session.execute(select(CartaEntity).where(CartaEntity.source_url == source_url))
        entity = result.scalars().first()
        if not entity:
            entity = CartaEntity(source_url=source_url, payload=payload, canonical_id=canonical_id)
            self.session.add(entity)
        else:
            entity.payload = payload
        await self.session.flush()
        return entity

class RouteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_endpoint(self, endpoint: str) -> Optional[CartaRoute]:
        result = await self.session.execute(select(CartaRoute).where(CartaRoute.endpoint == endpoint))
        return result.scalars().first()

    async def create(self, endpoint: str, method: str, service: str, capability_type: str, depth: int, parent_url: Optional[str] = None) -> CartaRoute:
        route = CartaRoute(
            endpoint=endpoint, 
            method=method, 
            service=service, 
            capability_type=capability_type,
            traversal_depth=depth,
            discovered_from=parent_url
        )
        self.session.add(route)
        await self.session.flush()
        return route

    async def update_schema_hash(self, route_id: str, schema_hash: str):
        await self.session.execute(
            update(CartaRoute).where(CartaRoute.id == route_id).values(schema_hash=schema_hash)
        )

class CapabilityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity_id: str, route_id: str, payload: dict) -> CartaCapability:
        cap = CartaCapability(entity_id=entity_id, route_id=route_id, payload=payload)
        self.session.add(cap)
        await self.session.flush()
        return cap

class SchemaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, route_id: str, schema_hash: str, structure: dict) -> CartaSchema:
        schema = CartaSchema(route_id=route_id, schema_hash=schema_hash, structure=structure)
        self.session.add(schema)
        await self.session.flush()
        return schema

class TraversalJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, url: str, depth: int, parent_url: Optional[str] = None) -> CartaTraversalJob:
        job = CartaTraversalJob(url=url, depth=depth, parent_url=parent_url)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_pending(self) -> Optional[CartaTraversalJob]:
        result = await self.session.execute(
            select(CartaTraversalJob).where(CartaTraversalJob.status == "pending").order_by(CartaTraversalJob.created_at)
        )
        return result.scalars().first()

    async def mark_status(self, job_id: str, status: str, error_msg: Optional[str] = None):
        values = {"status": status, "completed_at": datetime.utcnow() if status in ("completed", "failed") else None}
        if error_msg:
            values["error_msg"] = error_msg
        await self.session.execute(
            update(CartaTraversalJob).where(CartaTraversalJob.id == job_id).values(**values)
        )
