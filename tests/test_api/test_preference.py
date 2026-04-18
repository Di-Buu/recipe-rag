"""
用户偏好接口测试

覆盖：获取默认偏好、更新偏好、更新后 is_new_user 变化
验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_api/test_preference.py -v
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_default_preference(client: AsyncClient, auth_headers: dict):
    """获取默认偏好（未设置过）"""
    resp = await client.get("/api/preference", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["exclude_ingredients"] == []
    assert data["preferred_categories"] == []
    assert data["nutrition_goals"] == []
    assert data["difficulty_max"] is None
    assert data["costtime_max"] is None


@pytest.mark.asyncio
async def test_update_preference(client: AsyncClient, auth_headers: dict):
    """更新偏好"""
    pref = {
        "exclude_ingredients": ["花生", "虾"],
        "preferred_categories": ["川菜", "粤菜"],
        "nutrition_goals": ["低脂", "高蛋白"],
        "difficulty_max": 3,
        "costtime_max": 60,
    }
    resp = await client.put("/api/preference", json=pref, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["exclude_ingredients"] == ["花生", "虾"]
    assert data["difficulty_max"] == 3

    # 再次获取确认持久化
    resp2 = await client.get("/api/preference", headers=auth_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["preferred_categories"] == ["川菜", "粤菜"]
    assert data2["costtime_max"] == 60


@pytest.mark.asyncio
async def test_update_preference_sets_not_new_user(client: AsyncClient, auth_headers: dict):
    """更新偏好后用户不再是新用户"""
    # 先注册时 is_new_user=True，更新偏好后应变为 False
    pref = {"exclude_ingredients": [], "preferred_categories": [], "nutrition_goals": []}
    await client.put("/api/preference", json=pref, headers=auth_headers)

    # 重新登录验证 is_new_user 状态
    resp = await client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    assert resp.status_code == 200
    assert resp.json()["is_new_user"] is False


@pytest.mark.asyncio
async def test_update_preference_upsert(client: AsyncClient, auth_headers: dict):
    """多次更新偏好（UPSERT 策略）"""
    pref1 = {"exclude_ingredients": ["花生"], "preferred_categories": []}
    await client.put("/api/preference", json=pref1, headers=auth_headers)

    pref2 = {"exclude_ingredients": ["花生", "牛奶"], "preferred_categories": ["湘菜"]}
    resp = await client.put("/api/preference", json=pref2, headers=auth_headers)
    assert resp.status_code == 200

    resp2 = await client.get("/api/preference", headers=auth_headers)
    data = resp2.json()
    assert data["exclude_ingredients"] == ["花生", "牛奶"]
    assert data["preferred_categories"] == ["湘菜"]
