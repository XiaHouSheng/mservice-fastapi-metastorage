from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import MetaScope, get_meta_scope
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
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建元数据类型（平台级管理操作，仅 superuser / GLOBAL scope 可调用）。"""
    meta_scope.require_global(action="创建元数据类型")
    type_service = TypeService(db)
    return await type_service.create_type(type_data)


@router.get("", summary="元数据类型列表（登录用户）")
async def list_types(
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    service_name: str | None = Query(None, description="按业务名筛选（跨服务需 superuser）"),
) -> dict[str, object]:
    """分页获取元数据类型列表（统一 Scope：普通身份仅自身 service，superuser 可见全部）。"""
    target_service = meta_scope.resolve_filter(service_name, action="查看类型")
    type_service = TypeService(db)
    types, total = await type_service.list_types(
        skip=skip, limit=limit, service_name=target_service
    )
    return {"total": total, "items": [MetadataTypeResponse.model_validate(t) for t in types]}


@router.get(
    "/{type_name}",
    response_model=MetadataTypeResponse,
    summary="获取类型详情（登录用户）",
)
async def get_type(
    type_name: str,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service_name: str | None = Query(None, description="业务名（跨服务查询需 superuser）"),
):
    """根据 type_name 获取类型详情（含 schema，统一 Scope 判定）。"""
    target_service = meta_scope.resolve_target(service_name, action="查询类型")
    type_service = TypeService(db)
    return await type_service.get_type_by_name(type_name, target_service)


@router.put(
    "/{type_name}",
    response_model=MetadataTypeResponse,
    summary="更新类型 schema（仅 superuser）",
)
async def update_type(
    type_name: str,
    update_data: MetadataTypeUpdate,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service_name: str | None = Query(None, description="业务名（默认当前用户所属服务）"),
):
    """更新元数据类型（仅允许新增字段，向后兼容；仅 superuser / GLOBAL scope）。"""
    meta_scope.require_global(action="更新元数据类型")
    target_service = meta_scope.resolve_target(service_name, action="更新元数据类型")
    type_service = TypeService(db)
    return await type_service.update_type(type_name, target_service, update_data)


@router.delete(
    "/{type_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除类型（仅 superuser）",
)
async def delete_type(
    type_name: str,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service_name: str | None = Query(None, description="业务名（默认当前用户所属服务）"),
):
    """软删除元数据类型（已有实体数据的类型禁止删除；仅 superuser / GLOBAL scope）。"""
    meta_scope.require_global(action="删除元数据类型")
    target_service = meta_scope.resolve_target(service_name, action="删除元数据类型")
    type_service = TypeService(db)
    await type_service.delete_type(type_name, target_service)
