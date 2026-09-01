from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user
from app.repositories.type_repository import TypeRepository
from app.schemas.entry import (
    MetadataEntryCreate,
    MetadataEntryResponse,
    MetadataEntryUpdate,
    MetadataVersionResponse,
    RollbackRequest,
)
from app.services.entry_service import EntryService

router = APIRouter(prefix="/entries", tags=["元数据实体管理"])

# 查询端点中已知的非字段过滤参数（用于从任意 query params 中提取字段过滤器）
_KNOWN_QUERY_PARAMS = {
    "type_name",
    "tags",
    "page",
    "page_size",
    "sort_by",
    "sort_order",
    "created_after",
    "created_before",
}


def _entry_to_response(entry, type_name: str) -> dict[str, Any]:
    """将 MetadataEntry 转为响应字典（补充 type_name）。"""
    return {
        "id": entry.id,
        "type_name": type_name,
        "entity_key": entry.entity_key,
        "data": entry.data,
        "tags": entry.tags,
        "version": entry.version,
        "owner_user_id": entry.owner_user_id,
        "service_name": entry.service_name,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="创建实体元数据（登录用户）",
)
async def create_entry(
    entry_data: MetadataEntryCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """创建实体元数据。"""
    entry_service = EntryService(db)
    entry = await entry_service.create_entry(entry_data, current_user)
    return _entry_to_response(entry, entry_data.type_name)


@router.get(
    "/{type_name}/{entity_key}",
    summary="获取元数据（支持 ?version= 读历史版本）",
)
async def get_entry(
    type_name: str,
    entity_key: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    version: int | None = Query(None, ge=1, description="指定历史版本号，默认最新"),
) -> dict[str, Any]:
    """获取实体元数据（支持读取历史版本）。"""
    entry_service = EntryService(db)
    entry = await entry_service.get_entry(type_name, entity_key, current_user, version)
    return _entry_to_response(entry, type_name)


@router.put(
    "/{type_name}/{entity_key}",
    summary="更新元数据（版本自增）",
)
async def update_entry(
    type_name: str,
    entity_key: str,
    update_data: MetadataEntryUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """更新实体元数据（部分更新 deep merge，版本自增，保留历史版本）。"""
    entry_service = EntryService(db)
    entry = await entry_service.update_entry(type_name, entity_key, update_data, current_user)
    return _entry_to_response(entry, type_name)


@router.delete(
    "/{type_name}/{entity_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除元数据",
)
async def delete_entry(
    type_name: str,
    entity_key: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """软删除实体元数据。"""
    entry_service = EntryService(db)
    await entry_service.delete_entry(type_name, entity_key, current_user)


@router.get("", summary="查询元数据（字段过滤 + tags + 分页 + 排序）")
async def query_entries(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    type_name: str | None = Query(None, description="按类型名筛选"),
    tags: str | None = Query(None, description="标签交集过滤，逗号分隔"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向 asc/desc"),
    created_after: datetime | None = Query(None, description="创建时间起"),
    created_before: datetime | None = Query(None, description="创建时间止"),
) -> dict[str, Any]:
    """复杂查询：字段过滤（任意 query param）+ tags 交集 + 时间范围 + 分页 + 排序。"""
    # 从任意 query params 中提取字段过滤器（排除已知参数）
    field_filters: dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        if key not in _KNOWN_QUERY_PARAMS:
            field_filters[key] = value

    # 解析 tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    entry_service = EntryService(db)
    skip = (page - 1) * page_size
    entries, total = await entry_service.query_entries(
        current_user,
        type_name=type_name,
        field_filters=field_filters if field_filters else None,
        tags=tag_list,
        created_after=created_after,
        created_before=created_before,
        skip=skip,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # 批量解析 type_name
    type_ids = list({e.type_id for e in entries})
    type_repo = TypeRepository(db)
    type_map = await type_repo.get_by_ids(type_ids)

    items = [
        _entry_to_response(e, type_map.get(e.type_id).type_name if type_map.get(e.type_id) else "")
        for e in entries
    ]
    return {"total": total, "items": items}


@router.get(
    "/{type_name}/{entity_key}/versions",
    summary="版本历史列表",
)
async def list_versions(
    type_name: str,
    entity_key: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100, description="每页条数"),
) -> dict[str, Any]:
    """获取实体的版本历史列表。"""
    entry_service = EntryService(db)
    skip = (page - 1) * page_size
    versions, total = await entry_service.get_versions(
        type_name, entity_key, current_user, skip=skip, limit=page_size
    )
    return {
        "total": total,
        "items": [MetadataVersionResponse.model_validate(v) for v in versions],
    }


@router.post(
    "/{type_name}/{entity_key}/rollback",
    summary="回滚到指定版本",
)
async def rollback_entry(
    type_name: str,
    entity_key: str,
    rollback_data: RollbackRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """回滚到指定版本（生成新版本，数据取回滚目标）。"""
    entry_service = EntryService(db)
    entry = await entry_service.rollback_entry(
        type_name, entity_key, rollback_data.version, current_user
    )
    return _entry_to_response(entry, type_name)
