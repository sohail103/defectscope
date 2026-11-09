"""Background job registry with progress and cancellation."""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="defectscope-job")


@dataclass
class Job:
    id: str
    kind: str
    project_id: Optional[str] = None
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    message: str = ""
    passes: list = field(default_factory=list)
    result: dict = field(default_factory=dict)
    error: Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "project_id": self.project_id, "status": self.status,
            "progress": round(self.progress, 4), "message": self.message,
            "passes": [p.model_dump() if hasattr(p, "model_dump") else p for p in self.passes],
            "result": self.result, "error": self.error,
        }


_jobs: dict[str, Job] = {}


def submit(kind: str, fn: Callable[[Job], dict], project_id: Optional[str] = None) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], kind=kind, project_id=project_id)
    _jobs[job.id] = job

    def runner() -> None:
        job.status = "running"
        try:
            if job.cancel_event.is_set():
                job.status = "cancelled"
                return
            job.result = fn(job) or {}
            job.status = "cancelled" if job.cancel_event.is_set() else "done"
            if job.status == "done":
                job.progress = 1.0
        except Exception as e:  # noqa: BLE001
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            job.message = traceback.format_exc(limit=3)

    _pool.submit(runner)
    return job


def get(job_id: str) -> Job:
    return _jobs[job_id]


def cancel(job_id: str) -> Job:
    job = _jobs[job_id]
    job.cancel_event.set()
    return job
