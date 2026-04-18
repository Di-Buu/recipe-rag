"""
推荐历史接口测试

覆盖：历史列表（分页）、历史详情、删除、权限校验
验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_api/test_history.py -v
"""

import pytest
from httpx import AsyncClient

from tests.test_api.conftest import insert_history


@pytest.mark.asyncio
async def test_empty_history(client: AsyncClient, auth_headers: dict):
    """空历史列表"""
    resp = await client.get("/api/history", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_history_list_and_detail(client: AsyncClient, auth_headers: dict, test_db: str):
    """插入记录后查询列表和详情"""
    # 插入测试数据
    await insert_history(test_db, 1, "推荐一道低脂菜", "推荐您试试清蒸鲈鱼", [{"title": "清蒸鲈鱼"}])
    await insert_history(test_db, 1, "高蛋白菜品", "鸡胸肉沙拉是不错的选择", [{"title": "鸡胸肉沙拉"}, {"title": "虾仁炒蛋"}])

    # 查询列表
    resp = await client.get("/api/history", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # 验证两条记录都在
    questions = {item["question"] for item in items}
    assert "推荐一道低脂菜" in questions
    assert "高蛋白菜品" in questions
    # 找到有2个来源的那条
    multi_source = [item for item in items if item["source_count"] == 2][0]
    assert multi_source["question"] == "高蛋白菜品"

    # 查询详情
    detail_resp = await client.get(f"/api/history/{multi_source['id']}", headers=auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["answer"] == "鸡胸肉沙拉是不错的选择"
    assert len(detail["sources"]) == 2


@pytest.mark.asyncio
async def test_history_preview_truncation(client: AsyncClient, auth_headers: dict, test_db: str):
    """answer_preview 截取前100字"""
    long_answer = "这是一段很长的回答，" * 20  # 远超100字
    await insert_history(test_db, 1, "长回答测试", long_answer, [])

    resp = await client.get("/api/history", headers=auth_headers)
    items = resp.json()
    assert len(items[0]["answer_preview"]) <= 100


@pytest.mark.asyncio
async def test_history_pagination(client: AsyncClient, auth_headers: dict, test_db: str):
    """分页功能"""
    for i in range(5):
        await insert_history(test_db, 1, f"问题{i}", f"回答{i}", [])

    # 第一页，每页2条
    resp1 = await client.get("/api/history?page=1&size=2", headers=auth_headers)
    items1 = resp1.json()
    assert len(items1) == 2

    # 第二页
    resp2 = await client.get("/api/history?page=2&size=2", headers=auth_headers)
    items2 = resp2.json()
    assert len(items2) == 2

    # 第三页
    resp3 = await client.get("/api/history?page=3&size=2", headers=auth_headers)
    items3 = resp3.json()
    assert len(items3) == 1


@pytest.mark.asyncio
async def test_delete_history(client: AsyncClient, auth_headers: dict, test_db: str):
    """删除历史记录"""
    await insert_history(test_db, 1, "待删除", "待删除的回答", [])

    resp = await client.get("/api/history", headers=auth_headers)
    item_id = resp.json()[0]["id"]

    # 删除
    del_resp = await client.delete(f"/api/history/{item_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    # 确认已删除
    resp2 = await client.get("/api/history", headers=auth_headers)
    assert len(resp2.json()) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_history(client: AsyncClient, auth_headers: dict):
    """删除不存在的记录"""
    resp = await client.delete("/api/history/99999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_history_detail_not_found(client: AsyncClient, auth_headers: dict):
    """查询不存在的历史详情"""
    resp = await client.get("/api/history/99999", headers=auth_headers)
    assert resp.status_code == 404
