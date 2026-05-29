"""
services/providers/base.py
--------------------------
Abstract base class for all OpenClaw automation providers.

Every provider (Carta, OpenClaw, Crunchbase, Affinity, DealRoom, …)
must implement this interface so that the API server, worker pipeline,
and MCP server can be provider-agnostic.

Architecture contract
---------------------
- `run(company_name, task_id)` is the ONLY public entry point.
- It must return a dict matching the ExportResult schema below.
- All browser lifecycle management (lock, shield, teardown) lives
  inside the concrete implementation, NOT in the calling code.
- The caller (download_worker) never touches the browser directly.

ExportResult schema
-------------------
{
    "status": "success",
    "company": "<str>",
    "exports": [
        {
            "type": "<holdings_csv | document | pdf | screenshot>",
            "path": "<absolute local file path>"
        },
        ...
    ]
}

On failure, raise an exception. The worker handles all error states.
"""

from abc import ABC, abstractmethod


class ProviderAgent(ABC):
    """
    Platform-agnostic interface for browser automation providers.

    Infrastructure (PlaywrightManager, browser lock, SQLite queue,
    MCP, retry orchestration, watchdog) lives OUTSIDE this class and
    is provider-agnostic. Only the navigation/export logic is here.
    """

    @abstractmethod
    async def run(self, company_name: str, task_id: str) -> dict:
        """
        Execute the full automation workflow for a single company.

        Parameters
        ----------
        company_name : str
            The target company to look up / export data for.
        task_id : str
            UUID string used to name output files and prevent
            filename collisions across concurrent tasks.

        Returns
        -------
        dict
            ExportResult — see module docstring for schema.

        Raises
        ------
        Exception
            Any exception signals failure to the download worker,
            which records it as a 'failed' task in SQLite.
        """
        ...
