from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user, require_superuser
from app.schemas.type import MetadataTypeCreate, MetadataTypeResponse, MetadataTypeUpdate
from app.services.type_service import TypeService

router = APIRouter(prefix="/types", tags=["元数据类型管理"])


@router.post(
    "",
    response_model=MetadataTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建元数据类型（仅 superuser）",
)
async def create_type(
    type_data: MetadataTypeCreate,
    current_user: Annotated[CurrentUser, Depends(require_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建元数据类型（平台级管理操作，仅 superuser 可调用）。"""
    type_service = TypeService(db)
    return await type_service.create_type(type_data)


@router.get("", summary="元数据类型列表（登录用户）")
async def list_types(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    service_name: str | None = Query(None, description="按业务名筛选"),
) -> dict[str, object]:
    """分页获取元数据类型列表。"""
    type_service = TypeService(db)
    types, total = await type_service.list_types(
        skip=skip, limit=limit, service_name=service_name
    )
    return {"total": total, "items": [MetadataTypeResponse.model_validate(t) for t in types]}


@router.get(
    "/{type_name}",
    response_model=MetadataTypeResponse,
    summary="获取类型详情（登录用户）",
)
async def get_type(
    type_name: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """根据 type_name 获取类型详情（含 schema）。"""
    type_service = TypeService(db)
    return await type_service.get_type_by_name(type_name, current_user.service_name)


@router.put(
    "/{type_name}",
    response_model=MetadataTypeResponse,
    summary="更新类型 schema（仅 superuser）",
)
async def update_type(
    type_name: str,
    update_data: MetadataTypeUpdate,
    current_user: Annotated[CurrentUser, Depends(require_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新元数据类型（仅允许新增字段，向后兼容）。"""
    type_service = TypeService(db)
    return await type_service.update_type(type_name, current_user.service_name, update_data)


@router.delete(
    "/{type_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除类型（仅 superuser）",
)
async def delete_type(
    type_name: str,
    current_user: Annotated[CurrentUser, Depends(require_superuser)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """软删除元数据类型（已有实体数据的类型禁止删除）。"""
    type_service = TypeService(db)
    await type_service.delete_type(type_name, current_user.service_name)
