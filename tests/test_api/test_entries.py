"""元数据实体 API 集成测试。"""

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


def _user_headers(user_id: int = 1, username: str = "alice", service_name: str = "forum"):
    return {
        "Authorization": f"Bearer {create_test_token(user_id=user_id, username=username, service_name=service_name, role='user')}"
    }


async def _create_type(client):
    """辅助：创建 forum_post 类型。"""
    return await client.post(
        "/api/v1/types",
        headers=_superuser_headers(),
        json={
            "type_name": "forum_post",
            "service_name": "forum",
            "description": "论坛帖子",
            "schema_json": FORUM_SCHEMA,
        },
    )


# ── 创建 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_entry_success(client):
    """测试创建实体元数据成功。"""
    await _create_type(client)
    response = await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "测试帖子", "board": "技术", "likes": 10, "is_pinned": True},
            "tags": ["fastapi", "jwt"],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["entity_key"] == "post-001"
    assert data["type_name"] == "forum_post"
    assert data["version"] == 1
    assert data["data"]["title"] == "测试帖子"
    assert data["data"]["likes"] == 10
    assert data["tags"] == ["fastapi", "jwt"]
    assert data["owner_user_id"] == 1
    assert data["service_name"] == "forum"


@pytest.mark.asyncio
async def test_create_entry_missing_required_field_422(client):
    """测试创建时缺少必填字段返回 422。"""
    await _create_type(client)
    response = await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"board": "技术"},  # 缺少 title
            "tags": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_entry_wrong_field_type_422(client):
    """测试创建时字段类型错误返回 422。"""
    await _create_type(client)
    response = await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "测试", "board": "技术", "likes": "不是数字"},  # likes 应为 integer
            "tags": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_entry_duplicate_409(client):
    """测试重复创建同 entity_key 返回 409。"""
    await _create_type(client)
    for _ in range(2):
        response = await client.post(
            "/api/v1/entries",
            headers=_user_headers(),
            json={
                "type_name": "forum_post",
                "entity_key": "post-001",
                "data": {"title": "测试", "board": "技术"},
                "tags": [],
            },
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_entry_type_not_found_404(client):
    """测试创建时类型不存在返回 404。"""
    response = await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "nonexistent",
            "entity_key": "post-001",
            "data": {"title": "测试"},
            "tags": [],
        },
    )
    assert response.status_code == 404


# ── 获取 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entry_success(client):
    """测试获取实体元数据。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "测试帖子", "board": "技术", "likes": 10},
            "tags": ["tag1"],
        },
    )
    response = await client.get("/api/v1/entries/forum_post/post-001", headers=_user_headers())
    assert response.status_code == 200
    assert response.json()["entity_key"] == "post-001"
    assert response.json()["data"]["title"] == "测试帖子"


@pytest.mark.asyncio
async def test_get_entry_not_found(client):
    """测试获取不存在的实体返回 404。"""
    await _create_type(client)
    response = await client.get("/api/v1/entries/forum_post/nonexistent", headers=_user_headers())
    assert response.status_code == 404


# ── 更新与版本 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_entry_version_increment(client):
    """测试更新实体后版本自增。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "原标题", "board": "技术", "likes": 10},
            "tags": ["old"],
        },
    )
    response = await client.put(
        "/api/v1/entries/forum_post/post-001",
        headers=_user_headers(),
        json={"data": {"likes": 25, "is_pinned": True}, "tags": ["new"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
    # deep merge：title 保留，likes 更新，新增 is_pinned
    assert data["data"]["title"] == "原标题"
    assert data["data"]["likes"] == 25
    assert data["data"]["is_pinned"] is True
    assert data["tags"] == ["new"]


@pytest.mark.asyncio
async def test_get_entry_historical_version(client):
    """测试获取历史版本数据。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "v1标题", "board": "技术", "likes": 10},
            "tags": [],
        },
    )
    await client.put(
        "/api/v1/entries/forum_post/post-001",
        headers=_user_headers(),
        json={"data": {"title": "v2标题", "likes": 20}},
    )
    # 获取版本 1
    response = await client.get(
        "/api/v1/entries/forum_post/post-001?version=1", headers=_user_headers()
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert response.json()["data"]["title"] == "v1标题"
    assert response.json()["data"]["likes"] == 10


@pytest.mark.asyncio
async def test_version_history_list(client):
    """测试版本历史列表。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "v1", "board": "技术"},
            "tags": [],
        },
    )
    for i in range(2):
        await client.put(
            "/api/v1/entries/forum_post/post-001",
            headers=_user_headers(),
            json={"data": {"title": f"v{i+2}"}},
        )
    response = await client.get(
        "/api/v1/entries/forum_post/post-001/versions", headers=_user_headers()
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # v1 和 v2 被保存为历史版本（v3 是当前）
    versions = [v["version"] for v in data["items"]]
    assert 1 in versions
    assert 2 in versions


@pytest.mark.asyncio
async def test_rollback_to_version(client):
    """测试回滚到指定版本。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "原始标题", "board": "技术", "likes": 10},
            "tags": ["original"],
        },
    )
    await client.put(
        "/api/v1/entries/forum_post/post-001",
        headers=_user_headers(),
        json={"data": {"title": "修改后标题", "likes": 99}, "tags": ["modified"]},
    )
    # 回滚到版本 1
    response = await client.post(
        "/api/v1/entries/forum_post/post-001/rollback",
        headers=_user_headers(),
        json={"version": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 3  # 回滚生成新版本
    assert data["data"]["title"] == "原始标题"
    assert data["data"]["likes"] == 10
    assert data["tags"] == ["original"]


# ── 删除 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_entry_soft(client):
    """测试软删除实体。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "测试", "board": "技术"},
            "tags": [],
        },
    )
    response = await client.delete("/api/v1/entries/forum_post/post-001", headers=_user_headers())
    assert response.status_code == 204
    # 删除后查询不到
    get_resp = await client.get("/api/v1/entries/forum_post/post-001", headers=_user_headers())
    assert get_resp.status_code == 404


# ── 查询 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_entries_pagination(client):
    """测试查询分页。"""
    await _create_type(client)
    for i in range(5):
        await client.post(
            "/api/v1/entries",
            headers=_user_headers(),
            json={
                "type_name": "forum_post",
                "entity_key": f"post-{i:03d}",
                "data": {"title": f"帖子{i}", "board": "技术", "likes": i * 10},
                "tags": ["common"],
            },
        )
    response = await client.get(
        "/api/v1/entries?type_name=forum_post&page=1&page_size=2", headers=_user_headers()
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_query_entries_by_field_filter(client):
    """测试按字段值过滤查询。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-tech",
            "data": {"title": "技术帖", "board": "技术", "likes": 100},
            "tags": [],
        },
    )
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-life",
            "data": {"title": "生活帖", "board": "生活", "likes": 5},
            "tags": [],
        },
    )
    # 按 board=技术 过滤
    response = await client.get(
        "/api/v1/entries?type_name=forum_post&board=%E6%8A%80%E6%9C%AF", headers=_user_headers()
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["entity_key"] == "post-tech"


@pytest.mark.asyncio
async def test_query_entries_by_tags(client):
    """测试按 tags 交集过滤查询。"""
    await _create_type(client)
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-a",
            "data": {"title": "A", "board": "技术"},
            "tags": ["fastapi", "python"],
        },
    )
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-b",
            "data": {"title": "B", "board": "技术"},
            "tags": ["fastapi", "jwt"],
        },
    )
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(),
        json={
            "type_name": "forum_post",
            "entity_key": "post-c",
            "data": {"title": "C", "board": "技术"},
            "tags": ["java"],
        },
    )
    # 查同时包含 fastapi 和 python 的
    response = await client.get(
        "/api/v1/entries?type_name=forum_post&tags=fastapi,python", headers=_user_headers()
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["entity_key"] == "post-a"


# ── 权限与可见性 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_visibility_other_user_forbidden(client):
    """测试非同 service_name 且非 owner 的用户访问返回 403。"""
    await _create_type(client)
    # alice (forum) 创建实体
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(user_id=1, username="alice", service_name="forum"),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "alice的帖子", "board": "技术"},
            "tags": [],
        },
    )
    # bob (shop) 尝试访问
    response = await client.get(
        "/api/v1/entries/forum_post/post-001",
        headers=_user_headers(user_id=2, username="bob", service_name="shop"),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_entry_visibility_same_service_allowed(client):
    """测试同 service_name 的用户可访问彼此的实体。"""
    await _create_type(client)
    # alice (forum) 创建实体
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(user_id=1, username="alice", service_name="forum"),
        json={
            "type_name": "forum_post",
            "entity_key": "post-001",
            "data": {"title": "alice的帖子", "board": "技术"},
            "tags": [],
        },
    )
    # charlie (forum) 可以访问
    response = await client.get(
        "/api/v1/entries/forum_post/post-001",
        headers=_user_headers(user_id=3, username="charlie", service_name="forum"),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_query_visibility_isolation(client):
    """测试列表查询仅返回当前用户可见的数据。"""
    await _create_type(client)
    # alice (forum) 创建
    await client.post(
        "/api/v1/entries",
        headers=_user_headers(user_id=1, username="alice", service_name="forum"),
        json={
            "type_name": "forum_post",
            "entity_key": "forum-post",
            "data": {"title": "论坛帖", "board": "技术"},
            "tags": [],
        },
    )
    # bob (shop) 创建（但类型是 forum 的，service_name 不同）
    # 注意：bob 的 service_name 是 shop，但类型 forum_post 属于 forum
    # bob 无法创建 forum_post 类型的实体，因为 get_type_by_name 用 current_user.service_name 查
    # 所以这里只验证 alice 能看到自己的
    response = await client.get(
        "/api/v1/entries?type_name=forum_post",
        headers=_user_headers(user_id=1, username="alice", service_name="forum"),
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.asyncio
async def test_no_token_unauthorized(client):
    """测试无 token 访问 entries 返回 401。"""
    response = await client.get("/api/v1/entries")
    assert response.status_code == 401
