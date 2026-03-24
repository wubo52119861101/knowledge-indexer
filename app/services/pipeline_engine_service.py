from __future__ import annotations

from app.core.config import Settings
from app.models.common import PipelineEngineInfo


class PipelineEngineService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve(self, scene: str) -> PipelineEngineInfo:
        return PipelineEngineInfo(
            type=self.settings.pipeline_engine_type,
            name=self.settings.pipeline_engine_name,
            scene=scene,
        )
