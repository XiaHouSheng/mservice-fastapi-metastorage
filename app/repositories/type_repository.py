from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_entry import MetadataEntry
from app.models.metadata_type import MetadataType


class TypeRepository:
    """元数据类型数据访问层，封装所有 CRUD 操作。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, metadata_type: MetadataType) -> MetadataType:
        """创建元数据类型。"""
        self.db.add(metadata_type)
        await self.db.flush()
        await self.db.refresh(metadata_type)
        return metadata_type

    async def get_by_id(self, type_id: int) -> MetadataType | None:
        """根据 ID 获取元数据类型（含软删除过滤）。"""
        stmt = select(MetadataType).where(
            MetadataType.id == type_id,
            MetadataType.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name_and_service(
        self, type_name: str, service_name: str
    ) -> MetadataType | None:
        """根据 type_name + service_name 获取类型（含软删除过滤）。"""
        stmt = select(MetadataType).where(
            MetadataType.type_name == type_name,
            MetadataType.service_name == service_name,
            MetadataType.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, metadata_type: MetadataType) -> MetadataType:
        """更新元数据类型。"""
        metadata_type.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(metadata_type)
        return metadata_type

    async def soft_delete(self, metadata_type: MetadataType) -> MetadataType:
        """软删除元数据类型。"""
        metadata_type.is_deleted = 1
        metadata_type.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return metadata_type

    async def count_active_entries(self, type_id: int) -> int:
        """统计该类型下未删除的实体数量（用于判断是否允许删除类型）。"""
        stmt = select(func.count()).select_from(MetadataEntry).where(
            MetadataEntry.type_id == type_id,
            MetadataEntry.is_deleted == 0,
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def get_by_ids(self, type_ids: list[int]) -> dict[int, MetadataType]:
        """根据 ID 列表批量获取类型，返回 {id: MetadataType} 映射。"""
        if not type_ids:
            return {}
        stmt = select(MetadataType).where(
            MetadataType.id.in_(type_ids),
            MetadataType.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return {t.id: t for t in result.scalars().all()}

    async def list_types(
        self,
        skip: int = 0,
        limit: int = 20,
        service_name: str | None = None,
    ) -> tuple[list[MetadataType], int]:
        """分页获取元数据类型列表，返回 (类型列表, 总数)。"""
        base_where = [MetadataType.is_deleted == 0]
        if service_name is not None:
            base_where.append(MetadataType.service_name == service_name)

        count_stmt = select(func.count()).select_from(MetadataType).where(*base_where)
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = (
            select(MetadataType)
            .where(*base_where)
            .order_by(MetadataType.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        types = list(result.scalars().all())
        return types, total
