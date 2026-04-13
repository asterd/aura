from __future__ import annotations

from fastapi import Depends

from aura.services.chat import ChatService
from aura.services.datasource_service import DatasourceService
from aura.services.retrieval import RetrievalService
from aura.services.space_service import SpaceService


def get_retrieval_service() -> RetrievalService:
    return RetrievalService()


def get_space_service() -> SpaceService:
    return SpaceService()


def get_chat_service(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> ChatService:
    return ChatService(retrieval_service=retrieval_service)


def get_datasource_service(
    space_service: SpaceService = Depends(get_space_service),
) -> DatasourceService:
    return DatasourceService(space_service=space_service)
