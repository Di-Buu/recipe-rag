"""
推荐查询路由

核心流程：
1. 接收用户查询 + 筛选条件
2. 调用 RAG Pipeline 执行混合检索 + LLM 生成
3. 将 pipeline 返回结果映射为 API 响应格式
4. 自动保存查询历史
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.api.schemas import (
    QueryRequest,
    QueryResponse,
    QueryFilters,
    RecipeSource,
    DIFFICULTY_MAP,
)
from src.api.database import get_db
from src.api.dependencies import get_current_user, get_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["推荐"])


def _build_source(raw: dict) -> RecipeSource:
    """将 pipeline 返回的原始 source 转换为 RecipeSource schema"""
    meta = raw.get("metadata", {})
    difficulty = meta.get("difficulty", 0)
    return RecipeSource(
        recipe_id=str(raw.get("recipe_id", "")),
        title=meta.get("title", "未知菜谱"),
        relevance=round(raw.get("relevance", 0.0), 4),
        matched_chunks=raw.get("matched_chunks", 0),
        category=meta.get("category", ""),
        difficulty=difficulty,
        difficulty_text=DIFFICULTY_MAP.get(difficulty, ""),
        costtime=meta.get("costtime", ""),
        nutrition_tags=meta.get("nutrition_tags", []),
        thumb=meta.get("thumb", ""),
        viewnum=meta.get("viewnum", 0),
        favnum=meta.get("favnum", 0),
    )


@router.post("/recommend", response_model=QueryResponse)
async def recommend(
    req: QueryRequest,
    current_user: dict = Depends(get_current_user),
    pipeline=Depends(get_pipeline),
):
    """推荐查询接口

    流程：
    1. 校验 Pipeline 可用性
    2. 将筛选条件转为 dict 传给 pipeline
    3. 在线程池中执行同步的 pipeline.query()
    4. 映射结果为 RecipeSource 列表
    5. 保存查询历史到数据库
    """
    # 检查 Pipeline 是否就绪
    if pipeline is None or not pipeline.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="推荐引擎尚未就绪，请稍后重试",
        )

    # 转换筛选条件
    filters_dict = req.filters.model_dump(exclude_none=True) if req.filters else None

    # 在线程池中执行同步 RAG 查询（避免阻塞事件循环）
    try:
        result = await asyncio.to_thread(
            pipeline.query, req.question, filters_dict
        )
    except Exception:
        logger.exception("RAG 查询执行失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="推荐查询失败，请稍后重试",
        )

    # 映射 sources
    sources = [_build_source(s) for s in result.get("sources", [])]

    response = QueryResponse(
        answer=result.get("answer", ""),
        sources=sources,
        query=req.question,
        filters=req.filters,
    )

    # 异步保存查询历史（不阻塞响应）
    try:
        sources_json = json.dumps(
            [s.model_dump() for s in sources], ensure_ascii=False
        )
        filters_json = (
            json.dumps(req.filters.model_dump(), ensure_ascii=False)
            if req.filters
            else None
        )
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO recommend_history (user_id, question, filters, answer, sources)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    current_user["id"],
                    req.question,
                    filters_json,
                    result.get("answer", ""),
                    sources_json,
                ),
            )
            await db.commit()
    except Exception:
        logger.exception("保存查询历史失败（不影响推荐结果返回）")

    return response


@router.post("/recommend/stream")
async def recommend_stream(
    req: QueryRequest,
    current_user: dict = Depends(get_current_user),
    pipeline=Depends(get_pipeline),
):
    """流式推荐查询接口（SSE）

    流式返回检索结果和 LLM 生成内容：
    - event: sources  →  检索来源（JSON）
    - event: token    →  LLM 文本片段
    - event: done     →  生成完成
    - event: error    →  错误信息
    """
    if pipeline is None or not pipeline.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="推荐引擎尚未就绪，请稍后重试",
        )

    filters_dict = req.filters.model_dump(exclude_none=True) if req.filters else None

    async def event_generator() -> AsyncGenerator[str, None]:
        full_answer = ""
        sources_data = []

        try:
            gen = pipeline.query_stream(req.question, filters_dict)
            for chunk in gen:
                if chunk["type"] == "sources":
                    raw_sources = chunk.get("sources", [])
                    mapped = [_build_source(s) for s in raw_sources]
                    sources_data = mapped
                    payload = json.dumps(
                        [s.model_dump() for s in mapped], ensure_ascii=False
                    )
                    yield f"event: sources\ndata: {payload}\n\n"

                elif chunk["type"] == "token":
                    token = chunk["token"]
                    full_answer += token
                    yield f"event: token\ndata: {json.dumps(token, ensure_ascii=False)}\n\n"

                elif chunk["type"] == "done":
                    yield "event: done\ndata: {}\n\n"

        except Exception:
            logger.exception("流式 RAG 查询执行失败")
            yield f'event: error\ndata: {json.dumps("推荐查询失败，请稍后重试", ensure_ascii=False)}\n\n'
            return

        # 保存历史（使用北京时间）
        try:
            from datetime import datetime, timezone, timedelta
            beijing_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            sources_json = json.dumps(
                [s.model_dump() for s in sources_data], ensure_ascii=False
            )
            filters_json = (
                json.dumps(req.filters.model_dump(), ensure_ascii=False)
                if req.filters
                else None
            )
            async with get_db() as db:
                await db.execute(
                    """
                    INSERT INTO recommend_history (user_id, question, filters, answer, sources, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_user["id"],
                        req.question,
                        filters_json,
                        full_answer,
                        sources_json,
                        beijing_now,
                    ),
                )
                await db.commit()
        except Exception:
            logger.exception("保存查询历史失败")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
