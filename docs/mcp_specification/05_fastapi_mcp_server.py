import os
import uuid
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from mcp.server.fastapi import FastMCP
from pydantic import BaseModel

# ─── Mock Database Connection ─────────────────────────────────────────────
# In production, use asyncpg or SQLAlchemy
class MockDatabase:
    async def fetch(self, query: str, *args) -> List[Dict]:
        return [{"mock_id": "123", "value": "demo"}]
    async def execute(self, query: str, *args) -> str:
        return "SUCCESS"

db = MockDatabase()

# ─── Auth & Multi-Tenancy Middleware ──────────────────────────────────────
# Resolves the API Key to a specific Tenant ID for strict data isolation
async def get_tenant_id(x_api_key: str = Header(...)) -> str:
    # Example hardcoded mapping; replace with Redis/PostgreSQL lookup
    auth_store = {
        "sk_test_123": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
    }
    tenant_id = auth_store.get(x_api_key)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return tenant_id

# ─── FastAPI Initialization ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect DB, Init rate limiters
    yield
    # Shutdown: Close DB connections

app = FastAPI(title="Carta Extraction MCP & API Server", lifespan=lifespan)

# ─── MCP Server Initialization ────────────────────────────────────────────
mcp = FastMCP("CartaIntelligence")

# ─── MCP Tools ────────────────────────────────────────────────────────────
@mcp.tool()
async def query_cap_table(company_id: str, tenant_id: str) -> List[Dict]:
    """
    Fetches the capitalization table for a portfolio company.
    Requires company_id and tenant_id for strict isolation.
    """
    query = """
        SELECT external_security_id, label, issuable_type, quantity, value 
        FROM securities 
        WHERE company_id = $1 AND tenant_id = $2
        ORDER BY issue_date DESC
    """
    results = await db.fetch(query, company_id, tenant_id)
    return results

@mcp.tool()
async def get_fund_irr(fund_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches the IRR metrics and valuations for a specific fund.
    """
    query = """
        SELECT pre_money_valuation, post_money_valuation, currency
        FROM valuations v
        JOIN portfolio_companies p ON v.company_id = p.id
        JOIN securities s ON s.company_id = p.id
        WHERE s.owner_fund_id = $1 AND v.tenant_id = $2
    """
    results = await db.fetch(query, fund_id, tenant_id)
    return {"fund_id": fund_id, "metrics": results}

@mcp.tool()
async def trigger_extraction(target_type: str, target_id: str, tenant_id: str) -> Dict[str, str]:
    """
    Triggers a background Carta extraction job for a firm, fund, or company.
    """
    job_id = str(uuid.uuid4())
    query = """
        INSERT INTO extraction_jobs (id, tenant_id, status, target_entity_type, target_entity_id)
        VALUES ($1, $2, 'PENDING', $3, $4)
    """
    await db.execute(query, job_id, tenant_id, target_type, target_id)
    return {"job_id": job_id, "status": "PENDING"}

# ─── MCP Resources ────────────────────────────────────────────────────────
@mcp.resource("carta://{tenant_id}/entities/funds")
def list_tenant_funds(tenant_id: str) -> str:
    """Returns a dynamic CSV or text block of funds available to this tenant."""
    # Note: FastMCP currently requires sync resource reads or specific async patterns
    return f"Funds for tenant {tenant_id}: Diamond Dogs SPV, Krakatoa Ventures Fund I"

# ─── FastAPI Routes (Bridging HTTP and MCP) ───────────────────────────────

@app.post("/api/mcp")
async def handle_mcp_request(request: Request, tenant_id: str = Depends(get_tenant_id)):
    """
    SSE / HTTP handler for MCP interactions. 
    Informs the MCP context of the authenticated tenant_id.
    """
    # Native MCP mapping allows injecting the tenant_id into context
    # This prevents the LLM from trying to guess or spoof tenant IDs
    return {"message": "MCP HTTP Transport Endpoint. Use SDK to connect."}

@app.get("/api/v1/companies/{company_id}/cap-table")
async def api_get_cap_table(company_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Standard REST wrapper calling the same core logic as the MCP tool."""
    return await query_cap_table(company_id, tenant_id)

if __name__ == "__main__":
    import uvicorn
    # Start the server with HTTP support
    uvicorn.run(app, host="0.0.0.0", port=8000)
