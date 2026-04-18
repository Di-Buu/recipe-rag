"""
数据库初始化与健康检查测试

验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_api/test_database.py -v
"""

import pytest
from httpx import AsyncClient

from src.api.database import get_db


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """健康检查接口（无需认证）"""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_tables_created(client: AsyncClient, test_db: str):
    """数据库初始化后表已创建"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in await cursor.fetchall()]

    assert "users" in tables
    assert "user_preference" in tables
    assert "recommend_history" in tables


@pytest.mark.asyncio
async def test_recommend_returns_503_without_pipeline(client: AsyncClient, auth_headers: dict):
    """Pipeline 未初始化时，recommend 接口返回 503"""
    resp = await client.post(
        "/api/recommend",
        json={"question": "推荐一个简单的家常菜"},
        headers=auth_headers,
    )
    assert resp.status_code == 503, f"Pipeline 未加载时应返回 503，实际返回 {resp.status_code}"
