from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

ENTITY_KEY_PATTERN = r"^[a-zA-Z0-9_\-\.]{1,255}$"


class MetadataEntryCreate(BaseModel):
    """创建实体元数据请求。"""

    type_name: str = Field(..., min_length=2, max_length=100)
    entity_key: str = Field(..., min_length=1, max_length=255, pattern=ENTITY_KEY_PATTERN)
    data: dict = Field(..., description="元数据 JSON，按类型 schema 校验")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    service_name: str | None = Field(
        None, description="目标业务名（仅 superuser 可指定其他服务，默认当前用户所属服务）"
    )


class MetadataEntryUpdate(BaseModel):
    """更新实体元数据请求（部分更新，deep merge）。"""

    data: dict | None = Field(None, description="待合并的元数据 JSON（与现有 data 深度合并）")
    tags: list[str] | None = Field(None, description="完整替换 tags（非合并）")


class MetadataEntryResponse(BaseModel):
    """实体元数据响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type_name: str
    entity_key: str
    data: dict
    tags: list[str]
    version: int
    owner_user_id: int
    service_name: str
    created_at: datetime
    updated_at: datetime | None


class MetadataVersionResponse(BaseModel):
    """历史版本响应。"""

    model_config = ConfigDict(from_attributes=True)

    version: int
    data: dict
    tags: list[str]
    created_at: datetime
    created_by_user_id: int


class RollbackRequest(BaseModel):
    """回滚到指定版本请求。"""

    version: int = Field(..., ge=1, description="目标版本号")
