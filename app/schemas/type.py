from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

TYPE_NAME_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]{1,99}$"
SERVICE_NAME_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]{0,49}$"


class FieldDefinition(BaseModel):
    """单个字段的 schema 定义，支持基础类型与复合类型。

    基础类型：string / integer / number / boolean
    复合类型：
    - list：数组，可用 items 声明元素类型（可嵌套复合类型）；
    - dict：键值映射，可用 values 声明值类型（可嵌套复合类型）；
    - object：结构化嵌套对象，可用 fields 声明子字段（递归结构）。
    """

    type: str = Field(
        ...,
        description="字段类型：string / integer / number / boolean / list / dict / object",
    )
    required: bool = Field(False, description="是否必填")
    indexed: bool = Field(False, description="是否可索引（用于查询优化提示）")
    default: object | None = Field(None, description="默认值")
    items: "FieldDefinition | None" = Field(None, description="list 的元素类型定义")
    values: "FieldDefinition | None" = Field(None, description="dict 的值类型定义")
    fields: "dict[str, FieldDefinition] | None" = Field(None, description="object 的子字段定义")


FieldDefinition.model_rebuild()


class SchemaDefinition(BaseModel):
    """元数据类型的 schema 定义。"""

    fields: dict[str, FieldDefinition] = Field(..., description="字段名 → 字段定义")


class MetadataTypeCreate(BaseModel):
    """创建元数据类型请求。"""

    type_name: str = Field(..., min_length=2, max_length=100, pattern=TYPE_NAME_PATTERN)
    service_name: str = Field(..., min_length=1, max_length=50, pattern=SERVICE_NAME_PATTERN)
    description: str | None = Field(None, max_length=500)
    schema_json: SchemaDefinition


class MetadataTypeUpdate(BaseModel):
    """更新元数据类型请求（仅允许新增字段，向后兼容）。"""

    description: str | None = Field(None, max_length=500)
    schema_json: SchemaDefinition | None = None


class MetadataTypeResponse(BaseModel):
    """元数据类型响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type_name: str
    service_name: str
    description: str | None
    schema_json: dict
    created_at: datetime
    updated_at: datetime | None
