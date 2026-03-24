from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.models.common import JobRunnerMode
from app.models.job import IndexJob


class JobRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.resolved_job_runner_mode

    def is_inline(self) -> bool:
        return self.mode is JobRunnerMode.INLINE

    def submit(self, run: Callable[[], IndexJob]) -> IndexJob:
        return run()
