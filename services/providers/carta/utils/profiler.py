import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any

log = logging.getLogger(__name__)

# Map raw phase names to macro-phases requested by the user
MACRO_PHASE_MAP = {
    "setup_and_auth": "Setup",
    "organization_discovery": "Org discovery",
    "entity_discovery": "Entity discovery",
    "company_navigation": "Traversal",
    "investment_drilldown": "Traversal",
    "api_extraction": "Replay",
    "replay_extraction": "Replay",
    "semantic_clustering": "Persistence",
    "entity_graph_construction": "Persistence",
    "data_export": "Persistence"
}

class PerformanceProfiler:
    def __init__(self, company_name: str, task_id: str, output_dir: str | Path):
        self.company_name = company_name
        self.task_id = task_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.start_time = time.monotonic()
        self.last_ts = time.monotonic()
        
        self.durations: Dict[str, float] = {
            "Setup": 0.0,
            "Org discovery": 0.0,
            "Entity discovery": 0.0,
            "Traversal": 0.0,
            "Replay": 0.0,
            "Persistence": 0.0
        }
        
        # Replay stats
        self.endpoints_discovered = 0
        self.endpoints_replayed = 0
        self.endpoints_skipped = 0
        self.successful_replays = 0
        self.failed_replays = 0
        self.new_entities_found = 0
        
        # ROI yielding metrics: family name -> {"attempts": int, "entities": int}
        self.roi_metrics: Dict[str, Dict[str, int]] = {}

    def log_phase(self, raw_phase_name: str):
        """
        Record the completion of a phase, compute its duration, log it in
        the mandated JSON format, and accumulate the duration in the macro-phase.
        """
        now = time.monotonic()
        duration = now - self.last_ts
        self.last_ts = now
        
        # Log telemetry in the exact user-mandated JSON schema
        log.info(json.dumps({
            "phase": raw_phase_name,
            "duration_sec": round(duration, 3)
        }))
        
        # Map raw phase to macro-phase
        macro = MACRO_PHASE_MAP.get(raw_phase_name, "Setup")
        if macro in self.durations:
            self.durations[macro] += duration
        else:
            self.durations[macro] = duration

    def record_replay_metrics(self, discovered: int, replayed: int, skipped: int, successful: int, failed: int, new_entities: int):
        self.endpoints_discovered = discovered
        self.endpoints_replayed = replayed
        self.endpoints_skipped = skipped
        self.successful_replays = successful
        self.failed_replays = failed
        self.new_entities_found = new_entities

    def record_roi(self, family: str, attempts: int, entities: int):
        if family not in self.roi_metrics:
            self.roi_metrics[family] = {"attempts": 0, "entities": 0}
        self.roi_metrics[family]["attempts"] += attempts
        self.roi_metrics[family]["entities"] += entities

    def write_report(self):
        """Write JSON, Markdown profiles and print the nice table."""
        total_time = time.monotonic() - self.start_time
        
        report_data = {
            "company_name": self.company_name,
            "task_id": self.task_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_duration_sec": round(total_time, 3),
            "macro_phases": {k: round(v, 3) for k, v in self.durations.items()},
            "replay_telemetry": {
                "endpoints_discovered": self.endpoints_discovered,
                "endpoints_replayed": self.endpoints_replayed,
                "endpoints_skipped": self.endpoints_skipped,
                "successful_replays": self.successful_replays,
                "failed_replays": self.failed_replays,
                "new_entities_found": self.new_entities_found
            },
            "replay_roi_metrics": self.roi_metrics
        }
        
        # Write JSON report
        json_path = self.output_dir / "performance_profile.json"
        json_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        
        # Check for missing replay phase logging
        if self.successful_replays > 0 and self.durations.get("Replay", 0.0) == 0.0:
            log.warning("[Profiler] Found successful replays but Replay runtime is 0.0s! The api_extraction phase log may have been bypassed.")
        
        # Build Markdown report content
        md_content = f"""# Performance & ROI Profile Report

* **Company**: {self.company_name}
* **Task ID**: {self.task_id}
* **Generated At**: {report_data['timestamp']}
* **Total Runtime**: {report_data['total_duration_sec']}s

## Phase Runtimes

| Phase | Runtime (sec) |
| :--- | :--- |
| Org discovery | {report_data['macro_phases']['Org discovery']}s |
| Entity discovery | {report_data['macro_phases']['Entity discovery']}s |
| Traversal | {report_data['macro_phases']['Traversal']}s |
| Replay | {report_data['macro_phases']['Replay']}s |
| Persistence | {report_data['macro_phases']['Persistence']}s |
| Setup | {report_data['macro_phases']['Setup']}s |
| **Total** | **{report_data['total_duration_sec']}s** |

## Replay Telemetry

* **Endpoints Discovered**: {self.endpoints_discovered}
* **Endpoints Replayed**: {self.endpoints_replayed}
* **Endpoints Skipped**: {self.endpoints_skipped}
* **Successful Replays**: {self.successful_replays}
* **Failed Replays**: {self.failed_replays}
* **New Entities Discovered (manifest)**: {self.new_entities_found}

## Replay ROI (Business Entities Extracted)

| Endpoint Family | Attempts | Entities Extracted | Yield |
| :--- | :--- | :--- | :--- |
"""
        if self.roi_metrics:
            for family, data in sorted(self.roi_metrics.items(), key=lambda x: x[1].get("entities", 0), reverse=True):
                attempts = data.get("attempts", 0)
                entities = data.get("entities", 0)
                yield_pct = f"{(entities/attempts)*100:.1f}%" if attempts > 0 else "0.0%"
                md_content += f"| {family} | {attempts} | {entities} | {yield_pct} |\n"
        else:
            md_content += "| *None* | 0 | 0 | 0.0% |\n"
            
        md_path = self.output_dir / "performance_profile.md"
        md_path.write_text(md_content, encoding="utf-8")
        
        # Print runtime table in logging/output console
        table_str = "\n" + "="*40 + "\n"
        table_str += "         PERFORMANCE PROFILE REPORT\n"
        table_str += "="*40 + "\n"
        table_str += f"{'Phase':<25} {'Runtime':<15}\n"
        table_str += "-"*40 + "\n"
        table_str += f"{'Org discovery':<25} {report_data['macro_phases']['Org discovery']:.3f}s\n"
        table_str += f"{'Entity discovery':<25} {report_data['macro_phases']['Entity discovery']:.3f}s\n"
        table_str += f"{'Traversal':<25} {report_data['macro_phases']['Traversal']:.3f}s\n"
        table_str += f"{'Replay':<25} {report_data['macro_phases']['Replay']:.3f}s\n"
        table_str += f"{'Persistence':<25} {report_data['macro_phases']['Persistence']:.3f}s\n"
        table_str += "-"*40 + "\n"
        table_str += f"{'Total Runtime':<25} {report_data['total_duration_sec']:.3f}s\n"
        table_str += "="*40 + "\n"
        log.info(table_str)
        print(table_str)
