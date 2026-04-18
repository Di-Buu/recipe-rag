"""
推荐历史路由

提供历史记录的列表查询、详情查看和删除接口。
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemas import HistoryItem, HistoryDetail
from src.api.database import get_db
from src.api.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["历史"])


@router.get("/history", response_model=list[HistoryItem])
async def list_history(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: dict = Depends(get_current_user),
):
    """分页获取推荐历史列表

    answer 字段截取前100字作为预览。
    """
    offset = (page - 1) * size
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, question, filters, answer, sources, created_at
            FROM recommend_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (current_user["id"], size, offset),
        )
        rows = await cursor.fetchall()

    items = []
    for row in rows:
        sources = json.loads(row["sources"]) if row["sources"] else []
        filters = json.loads(row["filters"]) if row["filters"] else None
        answer = row["answer"] or ""
        items.append(HistoryItem(
            id=row["id"],
            question=row["question"],
            filters=filters,
            answer_preview=answer[:100],
            source_count=len(sources),
            created_at=row["created_at"],
        ))
    return items


@router.get("/history/{history_id}", response_model=HistoryDetail)
async def get_history(
    history_id: int,
    current_user: dict = Depends(get_current_user),
):
    """获取单条推荐历史详情"""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, question, filters, answer, sources, created_at
            FROM recommend_history
            WHERE id = ? AND user_id = ?
            """,
            (history_id, current_user["id"]),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="历史记录不存在",
        )

    return HistoryDetail(
        id=row["id"],
        question=row["question"],
        filters=json.loads(row["filters"]) if row["filters"] else None,
        answer=row["answer"],
        sources=json.loads(row["sources"]) if row["sources"] else [],
        created_at=row["created_at"],
    )


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    current_user: dict = Depends(get_current_user),
):
    """删除单条推荐历史

    只能删除属于当前用户的记录。
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM recommend_history WHERE id = ? AND user_id = ?",
            (history_id, current_user["id"]),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="历史记录不存在",
            )

        await db.execute(
            "DELETE FROM recommend_history WHERE id = ? AND user_id = ?",
            (history_id, current_user["id"]),
        )
        await db.commit()

    return {"message": "删除成功"}
