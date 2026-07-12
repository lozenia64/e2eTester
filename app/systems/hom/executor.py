"""HOM(PC) 워크플로 실행기 팩토리.

워크플로 로직은 대표홈페이지 공용 시나리오 실행기
(`app.scenarios.rep_homepage.executor.RepHomepageExecutor`)에 단 한 번만 존재한다.
이 모듈은 PC 채널 프로파일(`PC_CHANNEL`)을 주입해 실행기를 만드는 얇은 팩토리다.
시스템 로더(`app.systems.loader`)가 `create_executor` 를 호출한다.
"""

from __future__ import annotations

from app.platform.artifact_manager import ArtifactManager
from app.scenarios.rep_homepage.executor import RepHomepageExecutor
from app.systems.hom.channel import PC_CHANNEL

__all__ = ["create_executor"]


def create_executor(artifact_manager: ArtifactManager) -> RepHomepageExecutor:
    return RepHomepageExecutor(artifact_manager, PC_CHANNEL)
