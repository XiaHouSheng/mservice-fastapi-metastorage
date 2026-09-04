from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import MetaScope, get_meta_scope
from app.repositories.type_repository import TypeRepository
from app.schemas.entry import (
    BatchQueryRequest,
    MetadataEntryCreate,
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
    "service_name",
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
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """创建实体元数据（统一 Scope：普通身份仅本 service，superuser 可指定跨 service）。"""
    entry_service = EntryService(db)
    entry = await entry_service.create_entry(entry_data, meta_scope.user, meta_scope)
    return _entry_to_response(entry, entry_data.type_name)


@router.post(
    "/batch",
    summary="批量查询元数据（按 entity_key 列表）",
)
async def batch_get_entries(
    batch_data: BatchQueryRequest,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """按 [key1, key2, ...] 批量查询实体，返回 {key: obj}；未找到的 key 返回 null。

    统一 Scope 判定：普通身份仅可查自身 service，superuser 可指定跨 service（请求体 service_name）。
    """
    entry_service = EntryService(db)
    entries = await entry_service.batch_get_entries(batch_data, meta_scope)
    entry_map = {e.entity_key: _entry_to_response(e, batch_data.type_name) for e in entries}
    return {key: entry_map.get(key) for key in batch_data.keys}


@router.get(
    "/{type_name}/{entity_key}",
    summary="获取元数据（支持 ?version= 读历史版本）",
)
async def get_entry(
    type_name: str,
    entity_key: str,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    version: int | None = Query(None, ge=1, description="指定历史版本号，默认最新"),
) -> dict[str, Any]:
    """获取实体元数据（支持读取历史版本；统一 Scope 判定，superuser 可跨服务）。"""
    entry_service = EntryService(db)
    entry = await entry_service.get_entry(type_name, entity_key, meta_scope, version)
    return _entry_to_response(entry, type_name)


@router.put(
    "/{type_name}/{entity_key}",
    summary="更新元数据（版本自增）",
)
async def update_entry(
    type_name: str,
    entity_key: str,
    update_data: MetadataEntryUpdate,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """更新实体元数据（部分更新 deep merge，版本自增；统一 Scope 判定，superuser 可跨服务）。"""
    entry_service = EntryService(db)
    entry = await entry_service.update_entry(
        type_name, entity_key, update_data, meta_scope.user, meta_scope
    )
    return _entry_to_response(entry, type_name)


@router.delete(
    "/{type_name}/{entity_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除元数据",
)
async def delete_entry(
    type_name: str,
    entity_key: str,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """软删除实体元数据（统一 Scope 判定，superuser 可跨服务）。"""
    entry_service = EntryService(db)
    await entry_service.delete_entry(type_name, entity_key, meta_scope)


@router.get("", summary="查询元数据（字段过滤 + tags + 分页 + 排序）")
async def query_entries(
    request: Request,
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    type_name: str | None = Query(None, description="按类型名筛选"),
    tags: str | None = Query(None, description="标签交集过滤，逗号分隔"),
    service_name: str | None = Query(None, description="按业务名筛选（跨服务仅 superuser）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向 asc/desc"),
    created_after: datetime | None = Query(None, description="创建时间起"),
    created_before: datetime | None = Query(None, description="创建时间止"),
) -> dict[str, Any]:
    """复杂查询：字段过滤（任意 query param）+ tags 交集 + 时间范围 + 分页 + 排序。

    统一 Scope 判定（resolve_filter）：普通身份仅查询自身 service，superuser 可查询全部/按 service 筛选。
    """
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
        meta_scope,
        service_name=service_name,
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
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100, description="每页条数"),
) -> dict[str, Any]:
    """获取实体的版本历史列表（统一 Scope 判定，superuser 可跨服务）。"""
    entry_service = EntryService(db)
    skip = (page - 1) * page_size
    versions, total = await entry_service.get_versions(
        type_name, entity_key, meta_scope, skip=skip, limit=page_size
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
    meta_scope: Annotated[MetaScope, Depends(get_meta_scope)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """回滚到指定版本（生成新版本，数据取回滚目标；统一 Scope 判定，superuser 可跨服务）。"""
    entry_service = EntryService(db)
    entry = await entry_service.rollback_entry(
        type_name, entity_key, rollback_data.version, meta_scope.user, meta_scope
    )
    return _entry_to_response(entry, type_name)
