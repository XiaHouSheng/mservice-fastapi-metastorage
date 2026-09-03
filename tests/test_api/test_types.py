"""元数据类型管理 API 集成测试。"""

import pytest

from tests.conftest import create_test_token

FORUM_SCHEMA = {
    "fields": {
        "title": {"type": "string", "required": True, "indexed": True},
        "board": {"type": "string", "required": True, "indexed": True},
        "likes": {"type": "integer", "required": False, "indexed": True},
        "is_pinned": {"type": "boolean", "required": False, "indexed": False},
    }
}


def _superuser_headers():
    return {"Authorization": f"Bearer {create_test_token(user_id=999, username='superuser', role='superuser')}"}


def _user_headers(user_id: int = 1, username: str = "testuser"):
    return {"Authorization": f"Bearer {create_test_token(user_id=user_id, username=username, role='user')}"}


@pytest.mark.asyncio
async def test_create_type_superuser(client):
    """测试 superuser 创建元数据类型成功。"""
    response = await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "description": "论坛帖子元数据",
            "schema_json": FORUM_SCHEMA,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type_name"] == "forum_post"
    assert data["service_name"] == "forum"
    assert data["description"] == "论坛帖子元数据"
    assert "fields" in data["schema_json"]
    assert data["schema_json"]["fields"]["title"]["type"] == "string"


@pytest.mark.asyncio
async def test_create_type_normal_user_forbidden(client):
    """测试普通用户创建元数据类型返回 403。"""
    response = await client.post(
        "/api/v1/types",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "description": "测试",
            "schema_json": FORUM_SCHEMA,
        },
    )
    assert response.status_code == 403
    assert "仅超级用户" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_type_duplicate_conflict(client):
    """测试重复创建同类型返回 409。"""
    for _ in range(2):
        response = await client.post(
            "/api/v1/types",
            headers=_superuser_headers(),
            json={
                "type_name": "forum_post",
                "service_name": "forum",
                "description": "测试",
                "schema_json": FORUM_SCHEMA,
            },
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_type_invalid_schema_422(client):
    """测试创建类型时 schema 字段类型不支持返回 422。"""
    bad_schema = {
        "fields": {
            "title": {"type": "datetime", "required": True},
        }
    }
    response = await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "bad_type",
            "service_name": "forum",
            "schema_json": bad_schema,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_types(client):
    """测试获取类型列表。"""
    # 创建两个类型
    for name in ["type_a", "type_b"]:
        await client.post(
            "/api/v1/types",
            headers=_superuser_headers(),
            json={
                "type_name": name,
                "service_name": "forum",
                "schema_json": FORUM_SCHEMA,
            },
        )
    response = await client.get("/api/v1/types?skip=0&limit=10", headers=_user_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_type_by_name(client):
    """测试按名称获取类型详情。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "description": "论坛帖子",
            "schema_json": FORUM_SCHEMA,
        },
    )
    response = await client.get("/api/v1/types/forum_post", headers=_user_headers())
    assert response.status_code == 200
    assert response.json()["type_name"] == "forum_post"
    assert response.json()["description"] == "论坛帖子"


@pytest.mark.asyncio
async def test_get_type_not_found(client):
    """测试获取不存在的类型返回 404。"""
    response = await client.get("/api/v1/types/nonexistent", headers=_user_headers())
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_type_add_field_superuser(client):
    """测试 superuser 更新类型 schema（仅新增字段）成功。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    # 新增一个字段
    updated_schema = {
        "fields": {
            **FORUM_SCHEMA["fields"],
            "views": {"type": "integer", "required": False, "indexed": True},
        }
    }
    response = await client.put(
        "/api/v1/types/forum_post",
        headers=_superuser_headers(),
        json={"schema_json": updated_schema},
    )
    assert response.status_code == 200
    assert "views" in response.json()["schema_json"]["fields"]


@pytest.mark.asyncio
async def test_update_type_normal_user_forbidden(client):
    """测试普通用户更新类型返回 403。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    response = await client.put(
        "/api/v1/types/forum_post",
        headers=_user_headers(),
        json={"description": "新描述"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_type_remove_field_422(client):
    """测试更新类型时移除字段返回 422（不允许）。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    # 移除 title 字段
    bad_schema = {"fields": {k: v for k, v in FORUM_SCHEMA["fields"].items() if k != "title"}}
    response = await client.put(
        "/api/v1/types/forum_post",
        headers=_superuser_headers(),
        json={"schema_json": bad_schema},
    )
    assert response.status_code == 422
    assert "不允许移除字段" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_type_change_field_type_422(client):
    """测试更新类型时修改字段类型返回 422（不允许）。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    # 将 likes 从 integer 改为 string
    bad_schema = {
        "fields": {
            **FORUM_SCHEMA["fields"],
            "likes": {"type": "string", "required": False, "indexed": True},
        }
    }
    response = await client.put(
        "/api/v1/types/forum_post",
        headers=_superuser_headers(),
        json={"schema_json": bad_schema},
    )
    assert response.status_code == 422
    assert "不允许修改字段" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_type_superuser(client):
    """测试 superuser 软删除类型成功。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    response = await client.delete("/api/v1/types/forum_post", headers=_superuser_headers())
    assert response.status_code == 204
    # 删除后查询不到
    get_resp = await client.get("/api/v1/types/forum_post", headers=_user_headers())
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_type_with_entries_conflict(client):
    """测试删除有实体数据的类型返回 409。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    # 创建一条实体数据
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "测试帖子", "board": "技术", "likes": 10},
            "tags": ["test"],
        },
    )
    # 删除类型应失败
    response = await client.delete("/api/v1/types/forum_post", headers=_superuser_headers())
    assert response.status_code == 409
    assert "仍有" in response.json()["detail"]


@pytest.mark.asyncio
async def test_no_token_unauthorized(client):
    """测试无 token 访问返回 401。"""
    response = await client.get("/api/v1/types")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_unauthorized(client):
    """测试伪造 token 访问返回 401。"""
    response = await client.get(
        "/api/v1/types",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


# ── 三重 AND 校验安全测试 ──────────────────────────────


@pytest.mark.asyncio
async def test_superuser_role_but_wrong_username_403(client):
    """测试 role=superuser 但 username 不在白名单 → 403。"""
    headers = {
        "Authorization": f"Bearer {create_test_token(user_id=999, username='hacker', role='superuser')}"
    }
    response = await client.post(
        "/api/v1/types",
        headers=headers,
        json={
            "type_name": "evil_type",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_superuser_role_but_wrong_user_id_403(client):
    """测试 role=superuser + username 匹配 但 user_id 不在白名单 → 403。"""
    headers = {
        "Authorization": f"Bearer {create_test_token(user_id=1, username='superuser', role='superuser')}"
    }
    response = await client.post(
        "/api/v1/types",
        headers=headers,
        json={
            "type_name": "evil_type",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_correct_identity_but_role_user_403(client):
    """测试 username + user_id 都匹配白名单 但 role=user → 403。"""
    headers = {
        "Authorization": f"Bearer {create_test_token(user_id=999, username='superuser', role='user')}"
    }
    response = await client.post(
        "/api/v1/types",
        headers=headers,
        json={
            "type_name": "evil_type",
            "service_name": "forum",
            "schema_json": FORUM_SCHEMA,
        },
    )
    assert response.status_code == 403


# ── 跨服务访问权限（仅 superuser 可跨服务查看/操作）────────


def _headers_for(service_name: str, *, user_id: int = 2, username: str = "normal", role: str = "user"):
    return {
        "Authorization": f"Bearer {create_test_token(user_id=user_id, username=username, role=role, service_name=service_name)}"
    }


@pytest.mark.asyncio
async def test_get_type_cross_service_normal_user_forbidden(client):
    """测试普通用户显式跨服务查询类型详情返回 403。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={"type_name": "forum_post", "service_name": "forum", "schema_json": FORUM_SCHEMA},
    )
    response = await client.get(
        "/api/v1/types/forum_post?service_name=forum",
        headers=_headers_for("default"),
    )
    assert response.status_code == 403
    assert "仅超级用户可跨服务" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_type_cross_service_superuser_ok(client):
    """测试 superuser 显式跨服务查询类型详情成功。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={"type_name": "forum_post", "service_name": "forum", "schema_json": FORUM_SCHEMA},
    )
    response = await client.get(
        "/api/v1/types/forum_post?service_name=forum",
        headers=_headers_for("default", user_id=999, username="superuser", role="superuser"),
    )
    assert response.status_code == 200
    assert response.json()["service_name"] == "forum"


@pytest.mark.asyncio
async def test_get_type_defaults_to_own_service(client):
    """测试未指定 service_name 时按当前用户所属服务查询。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={"type_name": "forum_post", "service_name": "forum", "schema_json": FORUM_SCHEMA},
    )
    # 普通用户属于 default 服务，不带 service_name 查询 forum 下的类型 → 404
    response = await client.get(
        "/api/v1/types/forum_post",
        headers=_headers_for("default"),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_types_normal_user_only_own_service(client):
    """测试普通用户列表不传 service_name 时仅返回自己服务的类型。"""
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={"type_name": "forum_post", "service_name": "forum", "schema_json": FORUM_SCHEMA},
    )
    await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={"type_name": "default_post", "service_name": "default", "schema_json": FORUM_SCHEMA},
    )
    response = await client.get("/api/v1/types", headers=_headers_for("default"))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["type_name"] == "default_post"


@pytest.mark.asyncio
async def test_list_types_cross_service_normal_user_forbidden(client):
    """测试普通用户列表显式跨服务筛选返回 403。"""
    response = await client.get(
        "/api/v1/types?service_name=forum",
        headers=_headers_for("default"),
    )
    assert response.status_code == 403
    assert "仅超级用户可跨服务" in response.json()["detail"]
