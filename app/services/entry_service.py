"""元数据实体业务逻辑层：写读查 / 版本 / 回滚 / 可见性隔离。"""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.models.metadata_entry import MetadataEntry, MetadataVersion
from app.proxy.log_proxy import LogProxy
from app.repositories.entry_repository import EntryRepository
from app.schemas.entry import MetadataEntryCreate, MetadataEntryUpdate
from app.services.type_service import TypeService, validate_data_against_schema


def _deep_merge(base: dict, update: dict) -> dict:
    """深度合并两个字典：update 中的值覆盖 base，嵌套字典递归合并。"""
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _check_visibility(entry: MetadataEntry, user: CurrentUser) -> None:
    """检查当前用户是否有权访问该实体（owner 或同 service_name），越权返回 403。"""
    if entry.owner_user_id == user.user_id:
        return
    if entry.service_name == user.service_name:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="无权访问此元数据",
    )


def _validate_tags(tags: list[str]) -> None:
    """校验 tags 数量与单 tag 长度。"""
    if len(tags) > settings.MAX_TAGS_PER_ENTRY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"tags 数量超过上限 {settings.MAX_TAGS_PER_ENTRY}",
        )
    for tag in tags:
        if len(tag) > settings.MAX_TAG_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"tag 长度超过上限 {settings.MAX_TAG_LENGTH}: {tag[:20]}...",
            )


class EntryService:
    """元数据实体业务逻辑层。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo: EntryRepository = LogProxy(EntryRepository(db))  # type: ignore[assignment]
        self.type_service = TypeService(db)

    async def _find_entry(
        self, type_name: str, entity_key: str, current_user: CurrentUser
    ) -> MetadataEntry:
        """联表查找实体并校验可见性，不存在返回 404，越权返回 403。"""
        entry = await self.repo.get_by_type_name_and_key(type_name, entity_key)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"实体 {entity_key} 不存在",
            )
        _check_visibility(entry, current_user)
        return entry

    async def create_entry(
        self, entry_data: MetadataEntryCreate, current_user: CurrentUser
    ) -> MetadataEntry:
        """创建实体元数据。"""
        # 校验类型存在（仅本 service 的类型可用于创建）
        metadata_type = await self.type_service.get_type_by_name(
            entry_data.type_name, current_user.service_name
        )
        # 校验 tags
        _validate_tags(entry_data.tags)
        # 按 schema 动态校验 data
        validated_data = validate_data_against_schema(metadata_type.schema_json, entry_data.data)
        # 检查 (type_id, entity_key) 唯一性
        existing = await self.repo.get_by_type_and_key(metadata_type.id, entry_data.entity_key)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"实体 {entry_data.entity_key} 在类型 {entry_data.type_name} 下已存在",
            )

        entry = MetadataEntry(
            type_id=metadata_type.id,
            entity_key=entry_data.entity_key,
            data=validated_data,
            tags=entry_data.tags,
            version=1,
            service_name=current_user.service_name,
            owner_user_id=current_user.user_id,
        )
        return await self.repo.create(entry)

    async def get_entry(
        self, type_name: str, entity_key: str, current_user: CurrentUser, version: int | None = None
    ) -> MetadataEntry:
        """获取实体元数据（支持指定历史版本）。"""
        entry = await self._find_entry(type_name, entity_key, current_user)

        if version is not None:
            if version == entry.version:
                return entry
            historical = await self.repo.get_version_by_number(entry.id, version)
            if historical is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"版本 {version} 不存在",
                )
            entry.data = historical.data
            entry.tags = historical.tags
            entry.version = historical.version
            entry.updated_at = historical.created_at
        return entry

    async def update_entry(
        self,
        type_name: str,
        entity_key: str,
        update_data: MetadataEntryUpdate,
        current_user: CurrentUser,
    ) -> MetadataEntry:
        """更新实体元数据（部分更新 deep merge，版本自增，保留历史版本）。"""
        entry = await self._find_entry(type_name, entity_key, current_user)

        # 通过 entry.type_id 获取类型定义（用于 schema 校验）
        metadata_type = await self.type_service.get_type_by_id(entry.type_id)

        # 保存当前版本到历史版本表
        historical = MetadataVersion(
            entry_id=entry.id,
            version=entry.version,
            data=entry.data,
            tags=entry.tags,
            created_by_user_id=current_user.user_id,
        )
        await self.repo.create_version(historical)

        # 深度合并 data
        new_data = entry.data
        if update_data.data is not None:
            new_data = _deep_merge(entry.data, update_data.data)
            new_data = validate_data_against_schema(metadata_type.schema_json, new_data)

        # 替换 tags（非合并）
        new_tags = entry.tags
        if update_data.tags is not None:
            _validate_tags(update_data.tags)
            new_tags = update_data.tags

        entry.data = new_data
        entry.tags = new_tags
        entry.version = entry.version + 1
        entry.updated_at = datetime.now(timezone.utc)

        result = await self.repo.update(entry)
        await self.repo.delete_old_versions(entry.id, settings.MAX_VERSION_KEPT)
        return result

    async def delete_entry(
        self, type_name: str, entity_key: str, current_user: CurrentUser
    ) -> None:
        """软删除实体元数据。"""
        entry = await self._find_entry(type_name, entity_key, current_user)
        await self.repo.soft_delete(entry)

    async def query_entries(
        self,
        current_user: CurrentUser,
        *,
        type_name: str | None = None,
        field_filters: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[MetadataEntry], int]:
        """复杂查询：字段过滤 + tags 交集 + 时间范围 + 分页 + 排序 + 可见性隔离。"""
        return await self.repo.query_entries(
            type_name=type_name,
            field_filters=field_filters,
            tags=tags,
            created_after=created_after,
            created_before=created_before,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            visible_service_names=[current_user.service_name],
            visible_user_id=current_user.user_id,
        )

    async def get_versions(
        self,
        type_name: str,
        entity_key: str,
        current_user: CurrentUser,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[MetadataVersion], int]:
        """获取实体的版本历史列表。"""
        entry = await self._find_entry(type_name, entity_key, current_user)
        return await self.repo.get_versions(entry.id, skip=skip, limit=limit)

    async def rollback_entry(
        self,
        type_name: str,
        entity_key: str,
        target_version: int,
        current_user: CurrentUser,
    ) -> MetadataEntry:
        """回滚到指定版本（生成新版本，数据取回滚目标，不删除中间版本）。"""
        entry = await self._find_entry(type_name, entity_key, current_user)

        if target_version == entry.version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标版本与当前版本相同，无需回滚",
            )

        historical = await self.repo.get_version_by_number(entry.id, target_version)
        if historical is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"版本 {target_version} 不存在",
            )

        # 保存当前版本到历史
        current_historical = MetadataVersion(
            entry_id=entry.id,
            version=entry.version,
            data=entry.data,
            tags=entry.tags,
            created_by_user_id=current_user.user_id,
        )
        await self.repo.create_version(current_historical)

        entry.data = historical.data
        entry.tags = historical.tags
        entry.version = entry.version + 1
        entry.updated_at = datetime.now(timezone.utc)

        result = await self.repo.update(entry)
        await self.repo.delete_old_versions(entry.id, settings.MAX_VERSION_KEPT)
        return result
