"""
scripts/mcp_server.py
---------------------
Official Anthropic Model Context Protocol (MCP) server for OpenClaw automation.
Exposes generic provider-agnostic tools via Server-Sent Events (SSE) and JSON-RPC.

Active backend: Carta Export API (port 8082)

Tool naming is intentionally generic (download_report, download_batch, get_status)
so the same MCP interface works with any future provider without requiring MCP
client reconfiguration.
"""

import os
import json
import logging
import argparse
import requests
import uvicorn
import asyncio
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
from starlette.requests import Request

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

FASTAPI_URL = "http://127.0.0.1:8082"
# Set via environment variable or default to 'openclaw-dev-key'
API_KEY = os.environ.get("MCP_API_KEY", "openclaw-dev-key")
MCP_POLL_TIMEOUT_SEC = 600  # 10 minutes max polling time

server = Server("openclaw-carta-agent")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="download_report",
            description=(
                "Downloads / exports a structured data report for a company from Carta. "
                "Returns holdings CSV and any available documents. "
                "Submits an async task and polls until completion."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "Name of the company to export data for",
                    }
                },
                "required": ["company_name"],
            },
        ),
        Tool(
            name="download_batch",
            description=(
                "Exports Carta data for a list of companies. "
                "Submits all tasks in parallel and polls until all complete."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "companies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of company names to export",
                    }
                },
                "required": ["companies"],
            },
        ),
        Tool(
            name="get_status",
            description="Checks whether the underlying Carta export service is reachable.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    log.info(f"Tool called: {name} | args: {arguments}")

    # ── get_status ────────────────────────────────────────────────────
    if name == "get_status":
        try:
            requests.get(f"{FASTAPI_URL}/docs", timeout=2)
            agent_ok = True
        except Exception:
            agent_ok = False
        return [TextContent(type="text", text=json.dumps({
            "server": "running",
            "carta_export_service": "reachable" if agent_ok else "unreachable",
        }))]

    # ── download_report ───────────────────────────────────────────────
    elif name == "download_report":
        company_name = arguments.get("company_name")
        if not company_name:
            raise ValueError("company_name is required")

        try:
            resp = await asyncio.to_thread(
                requests.post,
                f"{FASTAPI_URL}/api/download-report",
                json={"company_name": company_name},
                timeout=30,
            )
            resp_data = resp.json()
            if "task_id" not in resp_data:
                return [TextContent(type="text", text=json.dumps(resp_data))]

            task_id = resp_data["task_id"]

            import time
            poll_start = time.time()
            while True:
                if time.time() - poll_start > MCP_POLL_TIMEOUT_SEC:
                    return [TextContent(type="text", text=json.dumps({
                        "error": f"Polling timed out after {MCP_POLL_TIMEOUT_SEC}s",
                        "task_id": task_id,
                    }))]

                status_resp = await asyncio.to_thread(
                    requests.get,
                    f"{FASTAPI_URL}/api/status/{task_id}",
                    timeout=30,
                )
                status_data = status_resp.json()
                if status_data.get("status") in ("completed", "failed", "timeout"):
                    return [TextContent(type="text", text=json.dumps(status_data))]

                await asyncio.sleep(5)

        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    # ── download_batch ────────────────────────────────────────────────
    elif name == "download_batch":
        companies = arguments.get("companies", [])
        if not companies:
            raise ValueError("companies list is required")

        task_ids = {}
        for company in companies:
            try:
                resp = await asyncio.to_thread(
                    requests.post,
                    f"{FASTAPI_URL}/api/download-report",
                    json={"company_name": company},
                    timeout=30,
                )
                resp_data = resp.json()
                if "task_id" in resp_data:
                    task_ids[company] = resp_data["task_id"]
                else:
                    task_ids[company] = {
                        "error": "Failed to get task_id",
                        "resp": resp_data,
                    }
            except Exception as e:
                task_ids[company] = {"error": str(e)}

        pending_tasks = {c: tid for c, tid in task_ids.items() if isinstance(tid, str)}
        completed_results = {
            c: err for c, err in task_ids.items() if not isinstance(err, str)
        }

        import time
        batch_poll_start = time.time()
        while pending_tasks:
            if time.time() - batch_poll_start > MCP_POLL_TIMEOUT_SEC:
                for company in list(pending_tasks.keys()):
                    completed_results[company] = {
                        "error": f"Polling timed out after {MCP_POLL_TIMEOUT_SEC}s",
                        "task_id": pending_tasks[company],
                    }
                break

            for company, task_id in list(pending_tasks.items()):
                try:
                    status_resp = await asyncio.to_thread(
                        requests.get,
                        f"{FASTAPI_URL}/api/status/{task_id}",
                        timeout=30,
                    )
                    status_data = status_resp.json()
                    if status_data.get("status") in ("completed", "failed", "timeout"):
                        completed_results[company] = status_data
                        del pending_tasks[company]
                except Exception as e:
                    completed_results[company] = {"error": str(e)}
                    del pending_tasks[company]

            if pending_tasks:
                await asyncio.sleep(5)

        passed = sum(
            1 for r in completed_results.values()
            if r.get("status") == "completed"
        )
        return [TextContent(type="text", text=json.dumps({
            "total": len(companies),
            "success": passed,
            "failed": len(companies) - passed,
            "results": [
                {"company": c, "response": r}
                for c, r in completed_results.items()
            ],
        }))]

    raise ValueError(f"Unknown tool: {name}")


# ── SSE Transport ─────────────────────────────────────────────────────

sse = SseServerTransport("/mcp/messages/")


def require_auth(request: Request):
    auth_header = request.headers.get("X-API-Key")
    if not auth_header or auth_header != API_KEY:
        log.warning(f"Unauthorized access attempt. Provided key: '{auth_header}'")
        raise ValueError("Unauthorized: Invalid X-API-Key")


async def handle_sse(scope, receive, send):
    request = Request(scope, receive)
    if request.method != "GET":
        response = JSONResponse({"error": "Method Not Allowed"}, status_code=405)
        await response(scope, receive, send)
        return

    try:
        require_auth(request)
    except ValueError as e:
        response = JSONResponse({"error": str(e)}, status_code=401)
        await response(scope, receive, send)
        return

    # Reset root_path so SseServerTransport generates the correct absolute path
    scope["root_path"] = ""

    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def handle_messages(scope, receive, send):
    request = Request(scope, receive)
    if request.method != "POST":
        response = JSONResponse({"error": "Method Not Allowed"}, status_code=405)
        await response(scope, receive, send)
        return

    try:
        require_auth(request)
    except ValueError as e:
        response = JSONResponse({"error": str(e)}, status_code=401)
        await response(scope, receive, send)
        return

    await sse.handle_post_message(scope, receive, send)


app = Starlette(routes=[
    Mount("/mcp/sse", app=handle_sse),
    Mount("/mcp/messages", app=handle_messages),
])


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Carta MCP Server (SSE)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    log.info(f"Starting OpenClaw MCP SSE Server at http://{args.host}:{args.port}/mcp/sse")
    log.info(f"Requiring X-API-Key authentication (Default Key: {API_KEY})")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()