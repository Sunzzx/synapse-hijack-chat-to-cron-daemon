"""
synapse_hijack.cron_bridge
==========================
Atomic, zero-downtime bridge into Hermes cron infrastructure (~/.hermes/cron/jobs.json).
Enables seamless dynamic registration of tasks parsed from chat without restarting the gateway.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CronJobDefinition:
    name: str
    prompt: str
    schedule_display: str
    minutes: int
    script: Optional[str] = None
    no_agent: bool = True
    enabled: bool = True
    workdir: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_hermes_dict(self) -> Dict[str, Any]:
        now_iso = datetime.datetime.now().astimezone().isoformat()
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "skills": [],
            "skill": None,
            "model": None,
            "provider": None,
            "base_url": None,
            "script": self.script,
            "no_agent": self.no_agent,
            "monitor_script": None,
            "monitor_url": None,
            "monitor_state": None,
            "context_from": None,
            "schedule": {
                "kind": "interval",
                "minutes": self.minutes,
                "display": self.schedule_display,
            },
            "schedule_display": self.schedule_display,
            "repeat": {"times": None, "completed": 0},
            "enabled": self.enabled,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "created_at": now_iso,
            "next_run_at": now_iso,
            "last_run_at": None,
            "last_status": "ok",
            "last_error": None,
            "failure_streak": 0,
            "deliver": "local",
            "origin": {
                "platform": "local",
                "chat_id": "synapse-hijack-auto",
                "chat_name": None,
                "thread_id": None,
                "user_id": "uid:501",
                "scope_id": None,
            },
            "workdir": self.workdir or str(Path.home() / ".hermes"),
        }


class CronBridge:
    """Interacts safely and atomically with ~/.hermes/cron/jobs.json."""

    def __init__(self, jobs_path: Optional[Path | str] = None):
        if jobs_path:
            self.jobs_path = Path(jobs_path)
        else:
            self.jobs_path = Path.home() / ".hermes" / "cron" / "jobs.json"

    def load_jobs(self) -> List[Dict[str, Any]]:
        if not self.jobs_path.exists():
            return []
        try:
            with open(self.jobs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("jobs", [])
        except Exception:
            return []

    def get_job_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        for job in self.load_jobs():
            if job.get("name") == name:
                return job
        return None

    def upsert_job(self, job_def: CronJobDefinition) -> bool:
        """Atomically insert or update a job in jobs.json."""
        self.jobs_path.parent.mkdir(parents=True, exist_ok=True)
        jobs = self.load_jobs()

        existing_index = -1
        for idx, j in enumerate(jobs):
            if j.get("name") == job_def.name:
                existing_index = idx
                break

        hermes_dict = job_def.to_hermes_dict()
        if existing_index >= 0:
            # Preserve historic stats
            hermes_dict["created_at"] = jobs[existing_index].get("created_at", hermes_dict["created_at"])
            hermes_dict["id"] = jobs[existing_index].get("id", hermes_dict["id"])
            hermes_dict["repeat"] = jobs[existing_index].get("repeat", hermes_dict["repeat"])
            jobs[existing_index] = hermes_dict
        else:
            jobs.append(hermes_dict)

        payload = {
            "jobs": jobs,
            "updated_at": datetime.datetime.now().astimezone().isoformat(),
        }

        # Atomic write via tempfile
        try:
            temp_fd, temp_path = tempfile.mkstemp(dir=str(self.jobs_path.parent), prefix="jobs_tmp_", suffix=".json")
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_path, str(self.jobs_path))
            return True
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

    def delete_job(self, name: str) -> bool:
        """Remove a job by name."""
        jobs = self.load_jobs()
        filtered = [j for j in jobs if j.get("name") != name]
        if len(filtered) == len(jobs):
            return False

        payload = {
            "jobs": filtered,
            "updated_at": datetime.datetime.now().astimezone().isoformat(),
        }
        temp_fd, temp_path = tempfile.mkstemp(dir=str(self.jobs_path.parent), prefix="jobs_tmp_", suffix=".json")
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, str(self.jobs_path))
        return True
