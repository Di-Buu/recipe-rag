"""
认证接口测试

覆盖：注册 → 登录 → 修改密码 → JWT 验证
验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_api/test_auth.py -v
"""

import pytest
from httpx import AsyncClient


# =========================================================================
# 注册测试
# =========================================================================

@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """正常注册"""
    resp = await client.post("/api/auth/register", json={
        "username": "newuser",
        "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["is_new_user"] is True
    assert "token" in data


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    """重复注册同一用户名"""
    payload = {"username": "dupuser", "password": "password123"}
    resp1 = await client.post("/api/auth/register", json=payload)
    assert resp1.status_code == 200

    resp2 = await client.post("/api/auth/register", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_short_username(client: AsyncClient):
    """用户名过短"""
    resp = await client.post("/api/auth/register", json={
        "username": "ab",
        "password": "password123",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    """密码过短"""
    resp = await client.post("/api/auth/register", json={
        "username": "validuser",
        "password": "12345",
    })
    assert resp.status_code == 422


# =========================================================================
# 登录测试
# =========================================================================

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """正常登录"""
    await client.post("/api/auth/register", json={
        "username": "loginuser",
        "password": "password123",
    })
    resp = await client.post("/api/auth/login", json={
        "username": "loginuser",
        "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "loginuser"
    assert "token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """密码错误"""
    await client.post("/api/auth/register", json={
        "username": "wrongpwuser",
        "password": "password123",
    })
    resp = await client.post("/api/auth/login", json={
        "username": "wrongpwuser",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """登录不存在的用户"""
    resp = await client.post("/api/auth/login", json={
        "username": "noone",
        "password": "password123",
    })
    assert resp.status_code == 401


# =========================================================================
# 修改密码测试
# =========================================================================

@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient, auth_headers: dict):
    """正常修改密码"""
    resp = await client.put("/api/auth/password", json={
        "old_password": "testpass123",
        "new_password": "newpass456",
    }, headers=auth_headers)
    assert resp.status_code == 200

    # 用新密码登录
    resp2 = await client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "newpass456",
    })
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_old(client: AsyncClient, auth_headers: dict):
    """旧密码错误"""
    resp = await client.put("/api/auth/password", json={
        "old_password": "wrongold",
        "new_password": "newpass456",
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_change_password_no_auth(client: AsyncClient):
    """未认证修改密码"""
    resp = await client.put("/api/auth/password", json={
        "old_password": "testpass123",
        "new_password": "newpass456",
    })
    # HTTPBearer 在缺少 Authorization 头时返回 401
    assert resp.status_code == 401


# =========================================================================
# JWT Token 验证测试
# =========================================================================

@pytest.mark.asyncio
async def test_invalid_token(client: AsyncClient):
    """无效 Token 访问受保护接口"""
    resp = await client.get("/api/preference", headers={
        "Authorization": "Bearer invalid-token-here",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_token(client: AsyncClient):
    """缺少 Token 访问受保护接口"""
    resp = await client.get("/api/preference")
    assert resp.status_code == 401
