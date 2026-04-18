"""
API 测试公共 fixtures

提供测试用的 FastAPI 客户端、数据库初始化、认证辅助等。

验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_api/ -v
"""

import os
import json

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# 测试前设置环境变量，确保使用固定的测试密钥
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-tests"

from src.api.main import app
from src.api.database import get_db, init_db


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """使用临时数据库文件进行测试，避免污染正式数据"""
    test_db_path = str(tmp_path / "test_recipe_app.db")
    import src.config as config_mod
    original_path = config_mod.APP_DB_PATH
    # 将数据库路径指向临时文件（database.py 运行时读取 config.APP_DB_PATH）
    config_mod.APP_DB_PATH = test_db_path

    await init_db()
    yield test_db_path

    # 恢复原路径
    config_mod.APP_DB_PATH = original_path


@pytest_asyncio.fixture
async def client(test_db):
    """创建测试用 HTTP 客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    """注册一个测试用户并返回 Token"""
    resp = await client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
    })
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str):
    """返回带有认证 Token 的请求头"""
    return {"Authorization": f"Bearer {auth_token}"}


async def insert_history(db_path: str, user_id: int, question: str, answer: str, sources: list):
    """测试辅助：向历史表插入记录"""
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO recommend_history (user_id, question, answer, sources) VALUES (?, ?, ?, ?)",
            (user_id, question, answer, json.dumps(sources, ensure_ascii=False)),
        )
        await db.commit()
