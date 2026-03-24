from app.core.config import Settings
from app.models.common import JobRunnerMode, PipelineEngineInfo, PipelineEngineType, SyncMode
from app.repositories.job_repo import InMemoryJobRepository
from app.services.job_service import JobService


def test_settings_resolved_job_runner_mode_uses_sync_run_inline_compatibility() -> None:
    inline_settings = Settings(SYNC_RUN_INLINE=True)
    background_settings = Settings(SYNC_RUN_INLINE=False)
    explicit_settings = Settings(SYNC_RUN_INLINE=True, JOB_RUNNER_MODE="background")

    assert inline_settings.resolved_job_runner_mode is JobRunnerMode.INLINE
    assert background_settings.resolved_job_runner_mode is JobRunnerMode.BACKGROUND
    assert explicit_settings.resolved_job_runner_mode is JobRunnerMode.BACKGROUND


def test_job_service_create_job_accepts_pipeline_engine() -> None:
    service = JobService(InMemoryJobRepository())
    pipeline_engine = PipelineEngineInfo(
        type=PipelineEngineType.BUILTIN,
        name="knowledge-indexer",
        scene="sync",
    )

    job = service.create_job(
        source_id="src_123",
        mode=SyncMode.FULL,
        triggered_by="tester",
        pipeline_engine=pipeline_engine,
    )

    assert job.pipeline_engine == pipeline_engine
    assert job.cancel_requested_at is None
    assert job.cancel_requested_by is None
    assert job.cancel_reason is None
