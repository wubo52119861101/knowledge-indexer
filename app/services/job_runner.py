from __future__ import annotations

from collections.abc import Callable
from threading import Lock, Thread

from app.core.config import Settings
from app.models.common import JobRunnerMode
from app.models.job import IndexJob


class JobRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.resolved_job_runner_mode
        self._threads: dict[str, Thread] = {}
        self._lock = Lock()

    def is_inline(self) -> bool:
        return self.mode is JobRunnerMode.INLINE

    def submit(self, job: IndexJob, run: Callable[[], IndexJob]) -> IndexJob:
        if self.is_inline():
            return run()

        thread = Thread(target=self._run_and_release, args=(job.id, run), daemon=True, name=f"job-runner-{job.id}")
        with self._lock:
            self._threads[job.id] = thread
        thread.start()
        return job

    def has_active_run(self, job_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(job_id)
        return thread.is_alive() if thread else False

    def wait(self, job_id: str, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._threads.get(job_id)
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run_and_release(self, job_id: str, run: Callable[[], IndexJob]) -> None:
        try:
            run()
        finally:
            with self._lock:
                self._threads.pop(job_id, None)
