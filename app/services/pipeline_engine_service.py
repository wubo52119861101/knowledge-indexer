from __future__ import annotations

import re

from app.core.config import Settings
from app.models.common import PipelineEngineInfo, PipelineEngineType


class PipelineEngineService:
    BUILTIN_ENGINE_NAME = "knowledge-indexer"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve(self, scene: str) -> PipelineEngineInfo:
        return self.resolve_for_request(scene)

    def resolve_for_request(self, scene: str) -> PipelineEngineInfo:
        if self._has_external_configured_engine():
            return PipelineEngineInfo(
                type=PipelineEngineType.EXTERNAL,
                name=self._configured_engine_name(),
                scene=scene,
            )
        return PipelineEngineInfo(
            type=PipelineEngineType.BUILTIN,
            name=self._configured_engine_name(),
            scene=scene,
        )

    def resolve_for_job(self, flow_name: str | None = None) -> PipelineEngineInfo:
        return PipelineEngineInfo(
            type=PipelineEngineType.BUILTIN,
            name=flow_name or self.BUILTIN_ENGINE_NAME,
            scene="sync",
        )

    def resolve_for_health(self) -> PipelineEngineInfo:
        if self._has_external_configured_engine():
            return PipelineEngineInfo(
                type=PipelineEngineType.EXTERNAL,
                name=self._configured_engine_name(),
                scene="service",
            )
        return PipelineEngineInfo(
            type=PipelineEngineType.BUILTIN,
            name=self._configured_engine_name(),
            scene="service",
        )

    def describe_builtin_flow(self, flow: object) -> str:
        flow_name = flow.__class__.__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "-", flow_name).lower()

    def _has_external_configured_engine(self) -> bool:
        return self.settings.pipeline_engine_type is PipelineEngineType.EXTERNAL

    def _configured_engine_name(self) -> str:
        configured_name = self.settings.pipeline_engine_name.strip()
        return configured_name or self.BUILTIN_ENGINE_NAME
