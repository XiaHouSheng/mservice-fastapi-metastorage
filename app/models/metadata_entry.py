from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetadataEntry(Base):
    """元数据实体表：某类型下具体实体的描述性元数据（含版本号）。"""

    __tablename__ = "metadata_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_id: Mapped[int] = mapped_column(Integer, ForeignKey("metadata_types.id"), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    service_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        # 软删除下保证 (type_id, entity_key) 唯一（仅未删除行参与唯一约束）
        Index(
            "uq_type_entity_active",
            "type_id",
            "entity_key",
            unique=True,
            sqlite_where=text("is_deleted = 0"),
        ),
    )


class MetadataVersion(Base):
    """元数据历史版本表：每次更新时保存旧版本，支持回滚。"""

    __tablename__ = "metadata_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("metadata_entries.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
