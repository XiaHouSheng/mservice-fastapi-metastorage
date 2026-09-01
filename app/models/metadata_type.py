from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetadataType(Base):
    """元数据类型定义表：业务方登记一种"元数据类型"及其字段 schema。"""

    __tablename__ = "metadata_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    service_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        # 软删除下保证 (type_name, service_name) 唯一（仅未删除行参与唯一约束）
        Index(
            "uq_type_name_service_active",
            "type_name",
            "service_name",
            unique=True,
            sqlite_where=text("is_deleted = 0"),
        ),
    )
