from app.core.config import Settings
from app.core.container import ServiceContainer
from app.models.common import JobRunnerMode, PipelineEngineInfo, PipelineEngineType, SourceType, SyncMode
from app.models.source import Source
from app.repositories.job_repo import InMemoryJobRepository
from app.services.job_service import JobService
from app.services.pipeline_engine_service import PipelineEngineService


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


def test_pipeline_engine_service_resolves_request_and_health_from_configuration() -> None:
    service = PipelineEngineService(Settings(PIPELINE_ENGINE_TYPE="external", PIPELINE_ENGINE_NAME="cocoindex"))

    ask_engine = service.resolve_for_request("ask")
    health_engine = service.resolve_for_health()

    assert ask_engine.type is PipelineEngineType.EXTERNAL
    assert ask_engine.name == "cocoindex"
    assert ask_engine.scene == "ask"
    assert health_engine.type is PipelineEngineType.EXTERNAL
    assert health_engine.name == "cocoindex"
    assert health_engine.scene == "service"


def test_trigger_sync_records_builtin_flow_as_job_pipeline_engine() -> None:
    container = ServiceContainer(Settings(PIPELINE_ENGINE_TYPE="external", PIPELINE_ENGINE_NAME="cocoindex"))
    container.source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.FULL,
        )
    )
    container.job_runner.submit = lambda job, task: job

    job = container.trigger_sync(source_id="src_1", mode=SyncMode.FULL, operator="tester")

    assert job.pipeline_engine is not None
    assert job.pipeline_engine.type is PipelineEngineType.BUILTIN
    assert job.pipeline_engine.name == "file-index-flow"
    assert job.pipeline_engine.scene == "sync"
