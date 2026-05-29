import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .session import Base

class CartaEntity(Base):
    __tablename__ = "carta_entities"
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    source_url = Column(String, nullable=False, unique=True)
    canonical_id = Column(String, nullable=True, index=True)
    payload = Column(JSONB, nullable=False)
    discovered_at = Column(DateTime, default=datetime.utcnow)

class CartaRoute(Base):
    __tablename__ = "carta_routes"
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    endpoint = Column(String, nullable=False, unique=True)
    method = Column(String, nullable=False)
    service = Column(String, nullable=True, index=True)
    capability_type = Column(String, nullable=True, index=True)
    schema_hash = Column(String, nullable=True)
    traversal_depth = Column(Integer, default=0)
    discovered_from = Column(String, nullable=True) # Parent URL
    first_seen = Column(DateTime, default=datetime.utcnow)

class CartaCapability(Base):
    __tablename__ = "carta_capabilities"
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    entity_id = Column(String, ForeignKey("carta_entities.id", ondelete="CASCADE"), nullable=False)
    route_id = Column(String, ForeignKey("carta_routes.id", ondelete="CASCADE"), nullable=False)
    payload = Column(JSONB, nullable=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    
    entity = relationship("CartaEntity")
    route = relationship("CartaRoute")

class CartaSchema(Base):
    __tablename__ = "carta_schemas"
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    route_id = Column(String, ForeignKey("carta_routes.id", ondelete="CASCADE"), nullable=False)
    schema_hash = Column(String, nullable=False, index=True)
    structure = Column(JSONB, nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow)

    route = relationship("CartaRoute")

class CartaTraversalJob(Base):
    __tablename__ = "carta_traversal_jobs"
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    url = Column(String, nullable=False, index=True)
    parent_url = Column(String, nullable=True)
    depth = Column(Integer, default=0)
    status = Column(String, default="pending") # pending, processing, completed, failed
    error_msg = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
